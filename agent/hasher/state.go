package hasher

import (
	"errors"
	"os"
	"strings"
)

var ErrHashStateInvalid = errors.New("hash state invalid or missing")

type State struct {
	Path string
}

// LoadLastHash reads the last hash from disk
func (s *State) LoadLastHash() (string, error) {
	data, err := os.ReadFile(s.Path)
	if err != nil {
		return "", ErrHashStateInvalid
	}
	h := strings.TrimSpace(string(data))
	if h == "" {
		return "", ErrHashStateInvalid
	}
	return h, nil
}

// SaveLastHash overwrites the hash state on disk
func (s *State) SaveLastHash(hash string) error {
	return os.WriteFile(s.Path, []byte(hash+"\n"), 0640)
}