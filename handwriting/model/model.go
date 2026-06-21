// Package model persists a trained network together with the metadata needed to
// turn raw class indices back into human-readable characters.
package model

import (
	"encoding/gob"
	"fmt"
	"io"
	"os"

	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/nn"
)

// Model bundles the network with its label alphabet and the dataset it was
// trained on, so a saved file is self-describing.
//
// When Quant is non-nil the float weights in Net are dropped on disk and the
// network is reconstructed from the compact int8 payload at load time. This is
// what lets a quantised model ship as a small blob embedded in the binary.
type Model struct {
	Net      *nn.Network
	Labels   []string // Labels[class] -> printable glyph, e.g. "0".."9" or "A".."Z"
	Dataset  string   // free-form provenance, e.g. "mnist" or "emnist-letters"
	Accuracy float64  // held-out accuracy at save time (for reporting)
	Quant    *Quantization
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

// Quantized reports whether the model is stored in int8 form.
func (m *Model) Quantized() bool { return m.Quant != nil }

// Write gob-encodes the model to w.
func (m *Model) Write(w io.Writer) error {
	if err := gob.NewEncoder(w).Encode(m); err != nil {
		return fmt.Errorf("model: encode: %w", err)
	}
	return nil
}

// Save gob-encodes the model to path.
func (m *Model) Save(path string) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	return m.Write(f)
}

// maxModelBytes caps how much a model file can decode into, so a corrupt or
// malicious gob payload can't exhaust memory (encoding/gob is not hardened
// against untrusted input). Real models are well under a megabyte.
const maxModelBytes = 64 << 20

// Read decodes a model from r, reconstructing float weights if it was quantised.
func Read(r io.Reader) (*Model, error) {
	var m Model
	if err := gob.NewDecoder(io.LimitReader(r, maxModelBytes)).Decode(&m); err != nil {
		return nil, fmt.Errorf("model: decode: %w", err)
	}
	if m.Quant != nil {
		if err := m.Quant.materialize(m.Net); err != nil {
			return nil, err
		}
	}
	return &m, nil
}

// Load reads a model previously written by Save.
func Load(path string) (*Model, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	m, err := Read(f)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return m, nil
}
