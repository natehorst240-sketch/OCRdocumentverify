package model

import (
	"math"

	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/nn"
)

// Quantization holds a network's weight matrices compressed to symmetric int8.
//
// Each weight matrix is stored as int8 values plus a single float64 scale, so
// the original weight is reconstructed as w ≈ q * scale. Symmetric per-tensor
// quantisation is the simplest scheme that preserves accuracy for small MLPs:
// the error per weight is at most half a quantisation step, which a softmax
// classifier shrugs off.
//
// Biases stay in full precision (they are tiny — one value per neuron — so
// quantising them saves nothing and only costs accuracy).
type Quantization struct {
	Shapes [][2]int  // [rows, cols] per weight layer
	QData  [][]int8  // flattened int8 weights per layer
	Scales []float64 // dequant scale per layer
}

// Quantize converts a Model's float network to int8 in place: it fills m.Quant
// and drops the float weights so the on-disk/embedded form is ~8× smaller.
// The float Biases and topology are kept; weights are reconstructed on Load.
func (m *Model) Quantize() {
	net := m.Net
	q := &Quantization{
		Shapes: make([][2]int, len(net.Weights)),
		QData:  make([][]int8, len(net.Weights)),
		Scales: make([]float64, len(net.Weights)),
	}
	for l, w := range net.Weights {
		q.Shapes[l] = [2]int{w.Rows, w.Cols}
		qd, scale := quantizeMatrix(w)
		q.QData[l] = qd
		q.Scales[l] = scale
	}
	net.Weights = nil // dropped on disk; rebuilt by materialize()
	m.Quant = q
}

// quantizeMatrix returns the int8 codes and scale for one weight matrix.
func quantizeMatrix(w *nn.Matrix) ([]int8, float64) {
	var max float64
	for _, v := range w.Data {
		if a := math.Abs(v); a > max {
			max = a
		}
	}
	scale := max / 127.0
	out := make([]int8, len(w.Data))
	if scale == 0 {
		return out, 0 // all-zero matrix
	}
	for i, v := range w.Data {
		q := math.Round(v / scale)
		if q > 127 {
			q = 127
		} else if q < -127 {
			q = -127
		}
		out[i] = int8(q)
	}
	return out, scale
}

// materialize rebuilds float weight matrices from the int8 payload back into net.
func (q *Quantization) materialize(net *nn.Network) {
	net.Weights = make([]*nn.Matrix, len(q.QData))
	for l, codes := range q.QData {
		rows, cols := q.Shapes[l][0], q.Shapes[l][1]
		w := nn.NewMatrix(rows, cols)
		scale := q.Scales[l]
		for i, c := range codes {
			w.Data[i] = float64(c) * scale
		}
		net.Weights[l] = w
	}
}
