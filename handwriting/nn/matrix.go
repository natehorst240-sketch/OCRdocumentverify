// Package nn implements a small feed-forward neural network from scratch
// using only the Go standard library.
//
// The design follows the spirit of the classic "neural net from scratch in Go"
// tutorial (datadan.io/blog/neural-net-with-go) — a forward pass, a loss, and
// backpropagation by hand — but generalises it for handwriting recognition:
//
//   - arbitrarily many hidden layers (not just one),
//   - ReLU hidden activations with He initialisation (trains deeper nets well),
//   - a softmax output with cross-entropy loss (the right choice for
//     multi-class classification such as 0-9 digits or A-Z letters),
//   - mini-batch stochastic gradient descent with momentum, and
//   - no third-party dependencies (the tutorial uses gonum; we stay stdlib-only
//     so the model can be vendored anywhere with zero install).
package nn

import (
	"fmt"
	"math"
	"math/rand"
)

// Matrix is a dense, row-major 2-D array of float64. Vectors are represented as
// single-column matrices (Cols == 1). Keeping a single concrete type keeps the
// forward/backward code readable without pulling in a linear-algebra library.
type Matrix struct {
	Rows, Cols int
	Data       []float64
}

// NewMatrix allocates a rows×cols zero matrix.
func NewMatrix(rows, cols int) *Matrix {
	return &Matrix{Rows: rows, Cols: cols, Data: make([]float64, rows*cols)}
}

// At returns the element at (r, c).
func (m *Matrix) At(r, c int) float64 { return m.Data[r*m.Cols+c] }

// Set writes v at (r, c).
func (m *Matrix) Set(r, c int, v float64) { m.Data[r*m.Cols+c] = v }

// ColumnVector wraps a slice as an n×1 matrix without copying.
func ColumnVector(v []float64) *Matrix {
	return &Matrix{Rows: len(v), Cols: 1, Data: v}
}

// Dot returns m·n (matrix product). It panics on a dimension mismatch, which
// only ever indicates a programming error in the network wiring.
func Dot(m, n *Matrix) *Matrix {
	if m.Cols != n.Rows {
		panic(fmt.Sprintf("nn: dimension mismatch %dx%d · %dx%d", m.Rows, m.Cols, n.Rows, n.Cols))
	}
	out := NewMatrix(m.Rows, n.Cols)
	for i := 0; i < m.Rows; i++ {
		for k := 0; k < m.Cols; k++ {
			a := m.Data[i*m.Cols+k]
			if a == 0 {
				continue // sparse-ish fast path; common after ReLU
			}
			for j := 0; j < n.Cols; j++ {
				out.Data[i*out.Cols+j] += a * n.Data[k*n.Cols+j]
			}
		}
	}
	return out
}

// DotTransposeA returns mᵀ·n without materialising the transpose.
func DotTransposeA(m, n *Matrix) *Matrix {
	if m.Rows != n.Rows {
		panic(fmt.Sprintf("nn: dimension mismatch %dx%dᵀ · %dx%d", m.Rows, m.Cols, n.Rows, n.Cols))
	}
	out := NewMatrix(m.Cols, n.Cols)
	for k := 0; k < m.Rows; k++ {
		for i := 0; i < m.Cols; i++ {
			a := m.Data[k*m.Cols+i]
			if a == 0 {
				continue
			}
			for j := 0; j < n.Cols; j++ {
				out.Data[i*out.Cols+j] += a * n.Data[k*n.Cols+j]
			}
		}
	}
	return out
}

// AddBias adds the column vector b (Rows×1) to every column of m in place.
func (m *Matrix) AddBias(b *Matrix) {
	for i := 0; i < m.Rows; i++ {
		bi := b.Data[i]
		for j := 0; j < m.Cols; j++ {
			m.Data[i*m.Cols+j] += bi
		}
	}
}

// randMatrix returns a matrix filled from f(r).
func randMatrix(rows, cols int, rng *rand.Rand, f func(*rand.Rand) float64) *Matrix {
	m := NewMatrix(rows, cols)
	for i := range m.Data {
		m.Data[i] = f(rng)
	}
	return m
}

// heInit returns a weight initialiser scaled for ReLU layers: N(0, 2/fanIn).
// He initialisation keeps activation variance stable through deep ReLU stacks,
// which is what lets the network train without careful manual tuning.
func heInit(fanIn int) func(*rand.Rand) float64 {
	std := math.Sqrt(2.0 / float64(fanIn))
	return func(r *rand.Rand) float64 { return r.NormFloat64() * std }
}
