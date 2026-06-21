package nn

import (
	"fmt"
	"math"
	"math/rand"
)

// Config describes the network shape and training hyper-parameters. It mirrors
// the tutorial's neuralNetConfig but supports any number of hidden layers and
// mini-batch training.
type Config struct {
	// Layers is the full topology including input and output, e.g.
	// {784, 128, 10} for MNIST: 784 pixels in, one 128-unit hidden layer,
	// 10 class scores out.
	Layers []int

	Epochs       int
	BatchSize    int
	LearningRate float64
	Momentum     float64
	L2           float64 // weight-decay coefficient (0 disables)
	Seed         int64
}

// DefaultConfig returns sane hyper-parameters for 28×28 glyph classification.
func DefaultConfig(numClasses int) Config {
	return Config{
		Layers:       []int{28 * 28, 128, numClasses},
		Epochs:       20,
		BatchSize:    32,
		LearningRate: 0.05,
		Momentum:     0.9,
		L2:           1e-4,
		Seed:         1,
	}
}

// Network is a trained (or trainable) feed-forward classifier. Exported fields
// are gob-serialisable so a model round-trips through model.Save/Load.
type Network struct {
	Layers  []int
	Weights []*Matrix // Weights[l]: Layers[l+1] × Layers[l]
	Biases  []*Matrix // Biases[l]:  Layers[l+1] × 1

	// velocity terms for SGD-with-momentum (not serialised; reset per train run)
	vWeights []*Matrix
	vBiases  []*Matrix
}

// New builds a network with He-initialised weights for the given topology.
func New(layers []int, rng *rand.Rand) *Network {
	if len(layers) < 2 {
		panic("nn: need at least an input and an output layer")
	}
	n := &Network{Layers: append([]int(nil), layers...)}
	for l := 0; l+1 < len(layers); l++ {
		in, out := layers[l], layers[l+1]
		n.Weights = append(n.Weights, randMatrix(out, in, rng, heInit(in)))
		n.Biases = append(n.Biases, NewMatrix(out, 1))
	}
	return n
}

// forward runs a batch (each column of x is one sample) through the network and
// returns, for every layer, the pre-activations z and activations a. The output
// layer uses softmax; hidden layers use ReLU.
func (n *Network) forward(x *Matrix) (zs, as []*Matrix) {
	a := x
	as = append(as, a)
	for l := range n.Weights {
		z := Dot(n.Weights[l], a)
		z.AddBias(n.Biases[l])
		zs = append(zs, z)
		if l == len(n.Weights)-1 {
			a = softmaxColumns(z)
		} else {
			a = relu(z)
		}
		as = append(as, a)
	}
	return zs, as
}

// Predict returns the class-probability vector for a single input.
func (n *Network) Predict(input []float64) []float64 {
	_, as := n.forward(ColumnVector(input))
	out := as[len(as)-1]
	return append([]float64(nil), out.Data...)
}

// Classify returns the arg-max class and its probability for a single input.
func (n *Network) Classify(input []float64) (class int, prob float64) {
	p := n.Predict(input)
	for i, v := range p {
		if v > prob {
			prob, class = v, i
		}
	}
	return class, prob
}

// backprop computes the loss and gradients for one mini-batch. x holds inputs
// as columns; y holds the matching one-hot targets as columns.
func (n *Network) backprop(x, y *Matrix) (loss float64, dW, dB []*Matrix) {
	zs, as := n.forward(x)
	L := len(n.Weights)
	dW = make([]*Matrix, L)
	dB = make([]*Matrix, L)
	batch := float64(x.Cols)

	// Output layer: softmax + cross-entropy gives the clean delta = a - y.
	out := as[len(as)-1]
	loss = crossEntropy(out, y) / batch
	delta := sub(out, y)

	for l := L - 1; l >= 0; l-- {
		aPrev := as[l]
		dW[l] = scale(DotTransposeA2(delta, aPrev), 1/batch)
		dB[l] = scale(rowSums(delta), 1/batch)
		if l > 0 {
			// propagate: delta = (Wᵀ·delta) ⊙ relu'(z_prev)
			delta = hadamard(DotTransposeA(n.Weights[l], delta), reluPrime(zs[l-1]))
		}
	}
	return loss, dW, dB
}

// Train runs mini-batch SGD with momentum and optional L2 weight decay. The
// optional onEpoch callback receives the mean training loss after each epoch,
// which the CLI uses to print a progress curve.
func (n *Network) Train(cfg Config, inputs [][]float64, targets [][]float64, onEpoch func(epoch int, loss float64)) error {
	if len(inputs) != len(targets) {
		return fmt.Errorf("nn: %d inputs but %d targets", len(inputs), len(targets))
	}
	if len(inputs) == 0 {
		return fmt.Errorf("nn: no training samples")
	}
	if cfg.BatchSize <= 0 {
		return fmt.Errorf("nn: batch size must be > 0 (got %d)", cfg.BatchSize)
	}
	numClasses := n.Layers[len(n.Layers)-1]
	inDim := n.Layers[0]
	for i := range inputs {
		if len(inputs[i]) != inDim {
			return fmt.Errorf("nn: input[%d] has len %d, want %d", i, len(inputs[i]), inDim)
		}
		if len(targets[i]) != numClasses {
			return fmt.Errorf("nn: target[%d] has len %d, want %d", i, len(targets[i]), numClasses)
		}
	}
	rng := rand.New(rand.NewSource(cfg.Seed))

	// fresh momentum buffers
	n.vWeights = make([]*Matrix, len(n.Weights))
	n.vBiases = make([]*Matrix, len(n.Biases))
	for l := range n.Weights {
		n.vWeights[l] = NewMatrix(n.Weights[l].Rows, n.Weights[l].Cols)
		n.vBiases[l] = NewMatrix(n.Biases[l].Rows, n.Biases[l].Cols)
	}

	order := make([]int, len(inputs))
	for i := range order {
		order[i] = i
	}

	for epoch := 1; epoch <= cfg.Epochs; epoch++ {
		rng.Shuffle(len(order), func(i, j int) { order[i], order[j] = order[j], order[i] })
		var epochLoss float64
		var batches int

		for start := 0; start < len(order); start += cfg.BatchSize {
			end := start + cfg.BatchSize
			if end > len(order) {
				end = len(order)
			}
			x, y := n.packBatch(order[start:end], inputs, targets, numClasses)
			loss, dW, dB := n.backprop(x, y)
			n.applyGradients(cfg, dW, dB)
			epochLoss += loss
			batches++
		}
		if onEpoch != nil {
			onEpoch(epoch, epochLoss/float64(batches))
		}
	}
	return nil
}

// packBatch assembles selected samples into column-major input/target matrices.
func (n *Network) packBatch(idx []int, inputs, targets [][]float64, numClasses int) (x, y *Matrix) {
	in := n.Layers[0]
	x = NewMatrix(in, len(idx))
	y = NewMatrix(numClasses, len(idx))
	for col, sample := range idx {
		for r := 0; r < in; r++ {
			x.Set(r, col, inputs[sample][r])
		}
		for r, v := range targets[sample] {
			y.Set(r, col, v)
		}
	}
	return x, y
}

// applyGradients performs the momentum + L2 update on every weight and bias.
func (n *Network) applyGradients(cfg Config, dW, dB []*Matrix) {
	for l := range n.Weights {
		w, vw := n.Weights[l], n.vWeights[l]
		for i := range w.Data {
			g := dW[l].Data[i] + cfg.L2*w.Data[i]
			vw.Data[i] = cfg.Momentum*vw.Data[i] - cfg.LearningRate*g
			w.Data[i] += vw.Data[i]
		}
		b, vb := n.Biases[l], n.vBiases[l]
		for i := range b.Data {
			vb.Data[i] = cfg.Momentum*vb.Data[i] - cfg.LearningRate*dB[l].Data[i]
			b.Data[i] += vb.Data[i]
		}
	}
}

// Evaluate returns top-1 accuracy over a labelled set.
func (n *Network) Evaluate(inputs [][]float64, labels []int) float64 {
	if len(inputs) == 0 {
		return 0
	}
	correct := 0
	for i, in := range inputs {
		if c, _ := n.Classify(in); c == labels[i] {
			correct++
		}
	}
	return float64(correct) / float64(len(inputs))
}

// --- activations and elementwise helpers ---

func relu(m *Matrix) *Matrix {
	out := NewMatrix(m.Rows, m.Cols)
	for i, v := range m.Data {
		if v > 0 {
			out.Data[i] = v
		}
	}
	return out
}

func reluPrime(m *Matrix) *Matrix {
	out := NewMatrix(m.Rows, m.Cols)
	for i, v := range m.Data {
		if v > 0 {
			out.Data[i] = 1
		}
	}
	return out
}

// softmaxColumns applies a numerically-stable softmax to each column.
func softmaxColumns(m *Matrix) *Matrix {
	out := NewMatrix(m.Rows, m.Cols)
	for c := 0; c < m.Cols; c++ {
		max := math.Inf(-1)
		for r := 0; r < m.Rows; r++ {
			if v := m.At(r, c); v > max {
				max = v
			}
		}
		var sum float64
		for r := 0; r < m.Rows; r++ {
			e := math.Exp(m.At(r, c) - max)
			out.Set(r, c, e)
			sum += e
		}
		for r := 0; r < m.Rows; r++ {
			out.Set(r, c, out.At(r, c)/sum)
		}
	}
	return out
}

// crossEntropy returns the summed -Σ y·log(p) over a batch (columns).
func crossEntropy(pred, target *Matrix) float64 {
	const eps = 1e-12
	var loss float64
	for i, t := range target.Data {
		if t != 0 {
			loss -= t * math.Log(pred.Data[i]+eps)
		}
	}
	return loss
}

func sub(a, b *Matrix) *Matrix {
	out := NewMatrix(a.Rows, a.Cols)
	for i := range a.Data {
		out.Data[i] = a.Data[i] - b.Data[i]
	}
	return out
}

func hadamard(a, b *Matrix) *Matrix {
	out := NewMatrix(a.Rows, a.Cols)
	for i := range a.Data {
		out.Data[i] = a.Data[i] * b.Data[i]
	}
	return out
}

func scale(a *Matrix, s float64) *Matrix {
	out := NewMatrix(a.Rows, a.Cols)
	for i := range a.Data {
		out.Data[i] = a.Data[i] * s
	}
	return out
}

// rowSums collapses a batch matrix to a column vector of per-row sums (used to
// turn per-sample bias gradients into one gradient for the batch).
func rowSums(m *Matrix) *Matrix {
	out := NewMatrix(m.Rows, 1)
	for r := 0; r < m.Rows; r++ {
		var s float64
		for c := 0; c < m.Cols; c++ {
			s += m.At(r, c)
		}
		out.Data[r] = s
	}
	return out
}

// DotTransposeA2 returns a·bᵀ (delta · activationsᵀ) used for weight gradients.
func DotTransposeA2(a, b *Matrix) *Matrix {
	if a.Cols != b.Cols {
		panic(fmt.Sprintf("nn: dimension mismatch %dx%d · %dx%dᵀ", a.Rows, a.Cols, b.Rows, b.Cols))
	}
	out := NewMatrix(a.Rows, b.Rows)
	for i := 0; i < a.Rows; i++ {
		for k := 0; k < a.Cols; k++ {
			av := a.Data[i*a.Cols+k]
			if av == 0 {
				continue
			}
			for j := 0; j < b.Rows; j++ {
				out.Data[i*out.Cols+j] += av * b.Data[j*b.Cols+k]
			}
		}
	}
	return out
}
