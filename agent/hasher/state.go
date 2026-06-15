package hasher

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
)

var ErrHashStateInvalid = errors.New("hash state invalid or missing")

type State struct {
	Path string
}

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

func (s *State) SaveLastHash(hash string) error {

	dir := filepath.Dir(s.Path)

	if err := os.MkdirAll(dir, 0755); err != nil {
		return err
	}

	return os.WriteFile(
		s.Path,
		[]byte(hash+"\n"),
		0640,
	)
}
