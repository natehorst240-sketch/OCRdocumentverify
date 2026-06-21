package data

import "math/rand"

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
