package parser

import (
	"strings"
	"time"

	"agent/types"
	"github.com/google/uuid"
)

func Parse(raw types.RawEvent, agent types.AgentInfo) types.NormalizedEvent {
	event := types.NormalizedEvent{
		EventID:         uuid.New().String(),
		Timestamp:       raw.Timestamp,
		IngestTimestamp: time.Now().UTC(),
		Agent:           agent,
		EventCategory:   raw.Category,
		EventType:       "unknown",
		Action:          "detected",
		Outcome:         "unknown",
		Severity:        "info",
		SourceEntity:    map[string]string{},
		TargetEntity:    map[string]string{},
		HostContext:     map[string]string{},
		Raw:             raw,
	}

	line := strings.ToLower(raw.Line)

	// VERY BASIC auth logic (placeholder)
	if raw.Category == "auth" {
		if strings.Contains(line, "failed") {
			event.EventType = "authentication"
			event.Action = "failed"
			event.Outcome = "failure"
			event.Severity = "medium"
		}
		if strings.Contains(line, "success") {
			event.EventType = "authentication"
			event.Action = "allowed"
			event.Outcome = "success"
			event.Severity = "info"
		}
	}

	return event
}