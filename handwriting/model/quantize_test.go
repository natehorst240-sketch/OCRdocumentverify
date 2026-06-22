package model

import (
	"bytes"
	"math/rand"
	"testing"

	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/nn"
)

// TestQuantizeRoundTrip checks that an int8-quantised model (a) survives a
// save/load cycle and (b) produces predictions very close to the float model.
func TestQuantizeRoundTrip(t *testing.T) {
	rng := rand.New(rand.NewSource(3))
	net := nn.New([]int{12, 16, 4}, rng)

	input := make([]float64, 12)
	for i := range input {
		input[i] = rng.Float64()
	}
	want := net.Predict(input)

	m := &Model{Net: net, Labels: []string{"a", "b", "c", "d"}, Dataset: "test"}
	m.Quantize()
	if m.Net.Weights != nil {
		t.Fatal("float weights should be dropped after Quantize")
	}

	var buf bytes.Buffer
	if err := m.Write(&buf); err != nil {
		t.Fatal(err)
	}
	loaded, err := Read(&buf)
	if err != nil {
		t.Fatal(err)
	}
	if !loaded.Quantized() {
		t.Fatal("loaded model should report Quantized() == true")
	}
	if loaded.Net.Weights == nil {
		t.Fatal("weights not materialised on load")
	}

	got := loaded.Net.Predict(input)
	// argmax must match and probabilities should be within quantisation noise.
	if argmax(got) != argmax(want) {
		t.Fatalf("quantised argmax %d != float argmax %d", argmax(got), argmax(want))
	}
	for i := range want {
		if d := abs(got[i] - want[i]); d > 0.05 {
			t.Fatalf("class %d prob drifted %.4f (float %.4f int8 %.4f)", i, d, want[i], got[i])
		}
	}
}

func argmax(v []float64) int {
	best, bi := v[0], 0
	for i, x := range v {
		if x > best {
			best, bi = x, i
		}
	}
	return bi
}

func abs(x float64) float64 {
	if x < 0 {
		return -x
	}
	return x
}
