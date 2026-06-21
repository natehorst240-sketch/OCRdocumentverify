package data

import (
	"math/rand"

	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/imageprep"
)

// Renormalize re-runs every sample through the same imageprep normalisation the
// recognizer applies to real images, so the training distribution matches what
// the model sees at inference. This is essential for datasets like EMNIST whose
// native framing differs from imageprep's MNIST-style 20px-in-28px centring;
// without it a model scores well on the raw test set but poorly on real scans.
func (d *Dataset) Renormalize() {
	for i := range d.Samples {
		g := &imageprep.Grid{W: d.Cols, H: d.Rows, Data: d.Samples[i].Pixels}
		d.Samples[i].Pixels = g.Normalize()
		d.Samples[i].Rows = imageprep.Side
		d.Samples[i].Cols = imageprep.Side
	}
	d.Rows, d.Cols = imageprep.Side, imageprep.Side
}

// Inputs returns the pixel vectors as a slice ready for nn.Network.Train.
func (d *Dataset) Inputs() [][]float64 {
	out := make([][]float64, len(d.Samples))
	for i, s := range d.Samples {
		out[i] = s.Pixels
	}
	return out
}

// Labels returns the integer labels parallel to Inputs.
func (d *Dataset) Labels() []int {
	out := make([]int, len(d.Samples))
	for i, s := range d.Samples {
		out[i] = s.Label
	}
	return out
}

// OneHot returns the labels as one-hot target vectors of width numClasses.
func (d *Dataset) OneHot(numClasses int) [][]float64 {
	out := make([][]float64, len(d.Samples))
	for i, s := range d.Samples {
		vec := make([]float64, numClasses)
		if s.Label >= 0 && s.Label < numClasses {
			vec[s.Label] = 1
		}
		out[i] = vec
	}
	return out
}

// Shuffle randomises sample order in place using the given source.
func (d *Dataset) Shuffle(rng *rand.Rand) {
	rng.Shuffle(len(d.Samples), func(i, j int) {
		d.Samples[i], d.Samples[j] = d.Samples[j], d.Samples[i]
	})
}

// Split returns the first frac of the samples and the remainder, useful for
// carving a quick validation set out of the training data.
func (d *Dataset) Split(frac float64) (*Dataset, *Dataset) {
	// Clamp to [0,1] so an out-of-range fraction can't produce invalid slice
	// bounds and panic.
	if frac < 0 {
		frac = 0
	} else if frac > 1 {
		frac = 1
	}
	cut := int(float64(len(d.Samples)) * frac)
	a := &Dataset{Rows: d.Rows, Cols: d.Cols, Samples: d.Samples[:cut]}
	b := &Dataset{Rows: d.Rows, Cols: d.Cols, Samples: d.Samples[cut:]}
	return a, b
}

// Limit returns at most n samples (handy for fast smoke runs on a laptop).
func (d *Dataset) Limit(n int) *Dataset {
	if n <= 0 || n >= len(d.Samples) {
		return d
	}
	return &Dataset{Rows: d.Rows, Cols: d.Cols, Samples: d.Samples[:n]}
}
