package types

import "time"

type AgentInfo struct {
	AgentID      string `json:"agent_id"`
	AgentType    string `json:"agent_type"`
	AgentVersion string `json:"agent_version"`
}

type RawEvent struct {
	Timestamp time.Time `json:"timestamp"`

	Category string `json:"category"`

	Source string `json:"source"`

	Line string `json:"raw"`

	Hash string `json:"hash"`
}

type NormalizedEvent struct {
	EventID         string    `json:"event_id"`
	Timestamp       time.Time `json:"timestamp"`
	IngestTimestamp time.Time `json:"ingest_timestamp"`

	Agent AgentInfo `json:"agent"`

	EventCategory string `json:"event_category"`
	EventType     string `json:"event_type"`
	Action        string `json:"action"`
	Outcome       string `json:"outcome"`
	Severity      string `json:"severity"`

	SourceEntity map[string]string `json:"source_entity"`
	TargetEntity map[string]string `json:"target_entity"`

	HostContext map[string]string `json:"host_context"`

	Raw RawEvent `json:"raw_event"`
}