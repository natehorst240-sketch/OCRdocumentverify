// Package model persists a trained network together with the metadata needed to
// turn raw class indices back into human-readable characters.
package model

import (
	"encoding/gob"
	"fmt"
	"os"

	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/nn"
)

// Model bundles the network with its label alphabet and the dataset it was
// trained on, so a saved file is self-describing.
type Model struct {
	Net      *nn.Network
	Labels   []string // Labels[class] -> printable glyph, e.g. "0".."9" or "A".."Z"
	Dataset  string   // free-form provenance, e.g. "mnist" or "emnist-letters"
	Accuracy float64  // held-out accuracy at save time (for reporting)
}

// DigitLabels returns "0".."9" for an MNIST model.
func DigitLabels() []string {
	out := make([]string, 10)
	for i := 0; i < 10; i++ {
		out[i] = string(rune('0' + i))
	}
	return out
}

// LetterLabels returns "A".."Z" for an EMNIST-letters model (26 classes).
func LetterLabels() []string {
	out := make([]string, 26)
	for i := 0; i < 26; i++ {
		out[i] = string(rune('A' + i))
	}
	return out
}

// Label maps a class index to its glyph, or "?" if out of range.
func (m *Model) Label(class int) string {
	if class < 0 || class >= len(m.Labels) {
		return "?"
	}
	return m.Labels[class]
}

// Save gob-encodes the model to path.
func (m *Model) Save(path string) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	if err := gob.NewEncoder(f).Encode(m); err != nil {
		return fmt.Errorf("model: encode: %w", err)
	}
	return nil
}

// Load reads a model previously written by Save.
func Load(path string) (*Model, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	var m Model
	if err := gob.NewDecoder(f).Decode(&m); err != nil {
		return nil, fmt.Errorf("model: decode %s: %w", path, err)
	}
	return &m, nil
}
