package pipeline

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"sync/atomic"
	"time"

	"agent/batcher"
	"agent/buffer"
	"agent/features"
	"agent/hasher"
	"agent/monitor"
	"agent/parser"
	"agent/sender"
	"agent/types"
)

/* ================= PIPELINE ================= */

type Pipeline struct {
	monitors []*monitor.FileMonitor
}

/* ================= SEND QUEUE ITEM ================= */

type SendItem struct {
	Kind string // "events" | "heartbeat" | "replay"
	Data []sender.EventEnvelope
}

/* ================= CONSTRUCTOR ================= */

func New() *Pipeline {
	return &Pipeline{
		monitors: []*monitor.FileMonitor{
			{Path: "/tmp/auth.log", Category: "auth"},
			{Path: "/tmp/sys.log", Category: "system"},
			{Path: "/tmp/kern.log", Category: "kernel"},
			{Path: "/tmp/app.log", Category: "app"},
		},
	}
}

/* ================= START ================= */

func (p *Pipeline) Start(ctx context.Context, agentInfo types.AgentInfo) {
	log.Println("pipeline started")

	startTime := time.Now()
	heartbeatInterval := 10 * time.Second

	/* ---------- METRICS ---------- */

	var (
		totalHeartbeats   uint64
		totalEventBatches uint64
		totalEvents       uint64
		kafkaHealthy      atomic.Bool
	)

	kafkaHealthy.Store(true)

	/* ---------- CHANNELS ---------- */

	rawEvents := make(chan types.RawEvent, 200)
	enriched := make(chan any, 200)
	batches := make(chan batcher.Batch, 10)
	sendQueue := make(chan SendItem, 20)

	/* ---------- FEATURE EXTRACTOR ---------- */

	extractor := features.New()

	/* ---------- BATCHER ---------- */

	b := batcher.New(batcher.Config{
		MaxEvents:   5,
		MaxInterval: 5 * time.Second,
	})
	b.Run(ctx, enriched, batches)

	/* ---------- HASH CHAIN ---------- */

	hashPath := os.Getenv("HASH_STATE_PATH")
	if hashPath == "" {
		hashPath = "./data/agent.hash"
	}

	hashState := &hasher.State{Path: hashPath}
	prevHash := ""
	trustOK := true

	if h, err := hashState.LoadLastHash(); err == nil {
		prevHash = h
	} else {
		log.Println("WARNING: hash state missing, agent marked untrusted")
		trustOK = false
	}

	/* ---------- TRANSPORT ---------- */

	var outSender sender.Sender

	switch os.Getenv("TRANSPORT") {
	case "kafka":
		outSender = sender.NewKafkaSender()
		log.Println("transport=kafka")
	default:
		endpoint := os.Getenv("CS_ENDPOINT")
		if endpoint == "" {
			endpoint = "http://localhost:8000/ingest"
		}
		outSender = sender.New(endpoint)
		log.Println("transport=http")
	}

	/* ---------- DISK BUFFER ---------- */

	disk := buffer.New("./data/send-buffer.jsonl")

	// Replay buffered batches on startup
	go func() {
		recs, err := disk.ReadAll()
		if err != nil || len(recs) == 0 {
			return
		}

		log.Printf("replaying %d buffered batches", len(recs))

		for _, raw := range recs {
			var batch []sender.EventEnvelope
			if err := json.Unmarshal(raw, &batch); err == nil {
				sendQueue <- SendItem{Kind: "replay", Data: batch}
			}
		}

		_ = disk.Clear()
	}()

	/* ---------- RETRY WORKER ---------- */

	go func() {
		for {
			select {
			case <-ctx.Done():
				return

			case item := <-sendQueue:
				backoff := 500 * time.Millisecond
				delivered := false

				for attempt := 1; attempt <= 5; attempt++ {
					err := outSender.Send(item.Data)
					if err == nil {
						kafkaHealthy.Store(true)

						switch item.Kind {
						case "heartbeat":
							h := atomic.AddUint64(&totalHeartbeats, 1)
							log.Printf(
								"heartbeat delivered (total=%d kafka_healthy=%v)",
								h,
								kafkaHealthy.Load(),
							)

						case "events":
							b := atomic.AddUint64(&totalEventBatches, 1)
							e := atomic.AddUint64(&totalEvents, uint64(len(item.Data)))
							log.Printf(
								"events delivered (batches=%d events=%d)",
								b,
								e,
							)

						case "replay":
							log.Printf(
								"replayed batch delivered (events=%d)",
								len(item.Data),
							)
						}

						delivered = true
						break
					}

					kafkaHealthy.Store(false)
					log.Printf(
						"%s send failed (attempt %d): %v",
						item.Kind,
						attempt,
						err,
					)

					time.Sleep(backoff)
					backoff *= 2
				}

				if !delivered {
					trustOK = false
					log.Printf("%s persisted to disk", item.Kind)
					_ = disk.Append(item.Data)
				}
			}
		}
	}()

	/* ---------- HEARTBEAT ---------- */

	go func() {
		ticker := time.NewTicker(heartbeatInterval)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return

			case <-ticker.C:
				hb := []sender.EventEnvelope{
					{
						EventID:         "heartbeat",
						Timestamp:       time.Now().UTC().Format(time.RFC3339),
						IngestTimestamp: time.Now().UTC().Format(time.RFC3339),

						Agent: sender.AgentBlock{
							AgentID:      agentInfo.AgentID,
							AgentType:    agentInfo.AgentType,
							AgentVersion: agentInfo.AgentVersion,
							TrustScore:   map[bool]float64{true: 1, false: 0}[trustOK],
						},

						Event: sender.EventBlock{
							Category: "agent",
							Type:     "heartbeat",
							Action:   "alive",
							Outcome:  "success",
							Severity: "info",
						},

						Integrity: sender.IntegrityBlock{
							Hash:     prevHash,
							PrevHash: prevHash,
							ChainID:  agentInfo.AgentID,
						},

						RawEvent: sender.RawBlock{
							Format: "meta",
							Data:   "uptime=" + time.Since(startTime).String(),
						},
					},
				}

				select {
				case sendQueue <- SendItem{Kind: "heartbeat", Data: hb}:
					log.Println("heartbeat enqueued")
				default:
					log.Println("heartbeat dropped (queue full)")
				}
			}
		}
	}()

	/* ---------- START MONITORS ---------- */

	for _, m := range p.monitors {
		m.Start(ctx, rawEvents)
	}

	/* ---------- PARSE LOOP ---------- */

	go func() {
		for {
			select {
			case <-ctx.Done():
				return

			case raw := <-rawEvents:
				n := parser.Parse(raw, agentInfo)
				extractor.Update(n)
				enriched <- map[string]any{"normalized": n}
			}
		}
	}()

	/* ---------- BATCH → HASH → QUEUE ---------- */

	for {
		select {
		case <-ctx.Done():
			log.Println("pipeline stopping")
			return

		case batch := <-batches:
			newHash, err := hasher.ComputeHash(prevHash, batch.Events)
			if err != nil {
				trustOK = false
				log.Printf("hash computation failed: %v", err)
				continue
			}

			_ = hashState.SaveLastHash(newHash)

			var out []sender.EventEnvelope
			for _, item := range batch.Events {
				n := item.(map[string]any)["normalized"].(types.NormalizedEvent)

				out = append(out, sender.EventEnvelope{
					EventID:         n.EventID,
					Timestamp:       n.Timestamp.UTC().Format(time.RFC3339),
					IngestTimestamp: n.IngestTimestamp.UTC().Format(time.RFC3339),
					Agent: sender.AgentBlock{
						AgentID:      agentInfo.AgentID,
						AgentType:    agentInfo.AgentType,
						AgentVersion: agentInfo.AgentVersion,
						TrustScore:   map[bool]float64{true: 1, false: 0}[trustOK],
					},
					Event: sender.EventBlock{
						Category: n.EventCategory,
						Type:     n.EventType,
						Action:   n.Action,
						Outcome:  n.Outcome,
						Severity: n.Severity,
					},
					Integrity: sender.IntegrityBlock{
						Hash:     newHash,
						PrevHash: prevHash,
						ChainID:  agentInfo.AgentID,
					},
					RawEvent: sender.RawBlock{
						Format: "text",
						Data:   n.Raw.Line,
					},
				})
			}

			select {
			case sendQueue <- SendItem{Kind: "events", Data: out}:
				log.Printf("events enqueued: id=%s count=%d", batch.ID, batch.Count)
			default:
				trustOK = false
				log.Printf("event batch persisted: id=%s", batch.ID)
				_ = disk.Append(out)
			}

			prevHash = newHash
		}
	}
}
