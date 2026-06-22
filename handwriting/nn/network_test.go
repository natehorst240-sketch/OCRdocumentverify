package nn

import (
	"math"
	"math/rand"
	"testing"
)

// TestForwardSoftmax checks the output is a valid probability distribution.
func TestForwardSoftmax(t *testing.T) {
	net := New([]int{4, 5, 3}, rand.New(rand.NewSource(1)))
	p := net.Predict([]float64{0.1, 0.2, 0.3, 0.4})
	if len(p) != 3 {
		t.Fatalf("got %d outputs, want 3", len(p))
	}
	var sum float64
	for _, v := range p {
		if v < 0 || v > 1 {
			t.Fatalf("probability out of range: %v", v)
		}
		sum += v
	}
	if math.Abs(sum-1) > 1e-9 {
		t.Fatalf("softmax sums to %v, want 1", sum)
	}
}

// TestLearnsXOR is the classic non-linear sanity check: a net with one hidden
// layer must learn XOR, which a linear model cannot. If backprop is wired up
// correctly this converges to 100% accuracy.
func TestLearnsXOR(t *testing.T) {
	inputs := [][]float64{{0, 0}, {0, 1}, {1, 0}, {1, 1}}
	// class 0 = XOR false, class 1 = XOR true
	labels := []int{0, 1, 1, 0}
	targets := [][]float64{{1, 0}, {0, 1}, {0, 1}, {1, 0}}

	net := New([]int{2, 8, 2}, rand.New(rand.NewSource(42)))
	cfg := Config{
		Layers: []int{2, 8, 2}, Epochs: 2000, BatchSize: 4,
		LearningRate: 0.1, Momentum: 0.9, Seed: 42,
	}
	if err := net.Train(cfg, inputs, targets, nil); err != nil {
		t.Fatal(err)
	}
	if acc := net.Evaluate(inputs, labels); acc < 1.0 {
		t.Fatalf("XOR accuracy %.2f, want 1.00 — backprop likely broken", acc)
	}
}

// TestGradientNumeric verifies analytic gradients against finite differences on
// a tiny network, which catches sign/transpose errors in backprop.
func TestGradientNumeric(t *testing.T) {
	rng := rand.New(rand.NewSource(7))
	net := New([]int{3, 4, 2}, rng)
	x := NewMatrix(3, 1)
	for i := range x.Data {
		x.Data[i] = rng.Float64()
	}
	y := NewMatrix(2, 1)
	y.Data[1] = 1 // one-hot target

	_, dW, _ := net.backprop(x, y)

	const eps = 1e-5
	w := net.Weights[0]
	g := dW[0]
	for idx := 0; idx < len(w.Data); idx += 3 { // spot-check a third of entries
		orig := w.Data[idx]
		w.Data[idx] = orig + eps
		_, aPlus := net.forward(x)
		lossPlus := crossEntropy(aPlus[len(aPlus)-1], y)
		w.Data[idx] = orig - eps
		_, aMinus := net.forward(x)
		lossMinus := crossEntropy(aMinus[len(aMinus)-1], y)
		w.Data[idx] = orig

		numeric := (lossPlus - lossMinus) / (2 * eps)
		if diff := math.Abs(numeric - g.Data[idx]); diff > 1e-4 {
			t.Fatalf("gradient mismatch at %d: analytic %.6f numeric %.6f", idx, g.Data[idx], numeric)
		}
	}
}
