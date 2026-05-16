package monitor

import (
	"bufio"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"log"
	"os"
	"strings"
	"time"

	"agent/types"
)

// FileMonitor tails a log file and emits RawEvents
type FileMonitor struct {
	Path     string
	Category string
}

func (fm *FileMonitor) Start(
	ctx context.Context,
	out chan<- types.RawEvent,
) {

	go func() {

		file, err := os.Open(fm.Path)

		if err != nil {

			log.Printf(
				"monitor error opening %s: %v",
				fm.Path,
				err,
			)

			return
		}

		defer file.Close()

		// =====================================================
		// START FROM END OF FILE
		// =====================================================

		_, err = file.Seek(0, os.SEEK_END)

		if err != nil {

			log.Printf(
				"seek error on %s: %v",
				fm.Path,
				err,
			)

			return
		}

		reader := bufio.NewReader(file)

		log.Printf(
			"monitor started: %s",
			fm.Path,
		)

		// =====================================================
		// TAIL LOOP
		// =====================================================

		for {

			select {

			case <-ctx.Done():

				log.Printf(
					"monitor stopped: %s",
					fm.Path,
				)

				return

			default:

				line, err := reader.ReadString('\n')

				if err != nil {

					time.Sleep(
						500 * time.Millisecond,
					)

					continue
				}

				// =============================================
				// CLEAN LINE
				// =============================================

				cleanLine := strings.TrimSpace(line)

				if cleanLine == "" {
					continue
				}

				// =============================================
				// HASH
				// =============================================

				hash := sha256.Sum256(
					[]byte(cleanLine),
				)

				hashHex := hex.EncodeToString(
					hash[:],
				)

				// =============================================
				// EVENT
				// =============================================

				event := types.RawEvent{

					Timestamp: time.Now().UTC(),

					Category: fm.Category,

					Source: fm.Path,

					Line: cleanLine,

					Hash: hashHex,
				}

				// =============================================
				// OUTPUT
				// =============================================

				out <- event

				log.Printf(
					"[MONITOR] %s | HASH=%s",
					cleanLine,
					hashHex[:12],
				)
			}
		}
	}()
}
