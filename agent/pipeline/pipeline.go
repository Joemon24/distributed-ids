package pipeline

import (
	"context"
	"log"
	"os"
	"time"

	"agent/batcher"
	"agent/features"
	"agent/hasher"
	"agent/monitor"
	"agent/parser"
	"agent/sender"
	"agent/types"
)

type Pipeline struct {
	monitors []*monitor.FileMonitor
}

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

func (p *Pipeline) Start(ctx context.Context, agentInfo types.AgentInfo) {
	log.Println("pipeline started")

	// channels
	rawEvents := make(chan types.RawEvent, 200)
	enriched := make(chan any, 200)
	batches := make(chan batcher.Batch, 10)

	// feature extractor
	extractor := features.New()

	// batcher
	b := batcher.New(batcher.Config{
		MaxEvents:   5,
		MaxInterval: 5 * time.Second,
	})
	b.Run(ctx, enriched, batches)

	// ---- HASH CHAIN INIT ----

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
		log.Println("WARNING: hash state missing or invalid, agent marked untrusted")
		trustOK = false
	}

	// ---- SENDER INIT ----

	endpoint := os.Getenv("CS_ENDPOINT")
	if endpoint == "" {
		endpoint = "http://localhost:8000/ingest"
	}
	httpSender := sender.New(endpoint)
	chainID := agentInfo.AgentID

	// start monitors
	for _, m := range p.monitors {
		m.Start(ctx, rawEvents)
	}

	// parse + feature loop
	go func() {
		for {
			select {
			case <-ctx.Done():
				return

			case raw := <-rawEvents:
				normalized := parser.Parse(raw, agentInfo)
				hostFeatures := extractor.Update(normalized)

				enriched <- map[string]any{
					"normalized": normalized,
					"host_feats": hostFeatures,
				}
			}
		}
	}()

	// batch → hash → schema → send
	for {
		select {
		case <-ctx.Done():
			log.Println("pipeline stopping")
			return

		case batch := <-batches:
			newHash, err := hasher.ComputeHash(prevHash, batch.Events)
			if err != nil {
				log.Printf("ERROR: hash computation failed: %v", err)
				trustOK = false
				continue
			}

			if err := hashState.SaveLastHash(newHash); err != nil {
				log.Printf("ERROR: failed to persist hash state: %v", err)
				trustOK = false
			}

			var out []sender.EventEnvelope

			for _, item := range batch.Events {
				m := item.(map[string]any)
				n := m["normalized"].(types.NormalizedEvent)

				out = append(out, sender.EventEnvelope{
					EventID:         n.EventID,
					Timestamp:       n.Timestamp.Format(time.RFC3339),
					IngestTimestamp: n.IngestTimestamp.Format(time.RFC3339),

					Agent: sender.AgentBlock{
						AgentID:      agentInfo.AgentID,
						AgentType:    agentInfo.AgentType,
						AgentVersion: agentInfo.AgentVersion,
						TrustScore: func() float64 {
							if trustOK {
								return 1.0
							}
							return 0.0
						}(),
					},

					Event: sender.EventBlock{
						Category: n.EventCategory,
						Type:     n.EventType,
						Action:   n.Action,
						Outcome:  n.Outcome,
						Severity: n.Severity,
					},

					Risk: sender.RiskBlock{
						Score:        0,
						Confidence:   0,
						AnomalyScore: 0,
					},

					Integrity: sender.IntegrityBlock{
						Hash:     newHash,
						PrevHash: prevHash,
						ChainID:  chainID,
					},

					RawEvent: sender.RawBlock{
						Format: "text",
						Data:   n.Raw.Line,
					},
				})
			}

			if err := httpSender.SendBatch(out); err != nil {
				log.Printf("ERROR: failed to send batch: %v", err)
			}

			log.Printf(
				"batch sent: id=%s count=%d hash=%s prev=%s trusted=%v",
				batch.ID,
				batch.Count,
				newHash[:12],
				func() string {
					if prevHash == "" {
						return "nil"
					}
					return prevHash[:12]
				}(),
				trustOK,
			)

			prevHash = newHash
		}
	}
}
