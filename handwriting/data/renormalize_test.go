package data

import (
	"testing"

	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/imageprep"
)

// TestRenormalizeProducesInferenceFraming checks that Renormalize rewrites each
// sample to the 28×28 imageprep frame, so training data matches what the
// recognizer sees on real images. (Without this, a model can score well on a
// dataset's own framing yet poorly on scans — see the EMNIST case.)
func TestRenormalizeProducesInferenceFraming(t *testing.T) {
	// One sample: a small off-centre block in a 28×28 frame.
	pixels := make([]float64, 28*28)
	for y := 2; y < 8; y++ {
		for x := 2; x < 8; x++ {
			pixels[y*28+x] = 1
		}
	}
	ds := &Dataset{
		Rows: 28, Cols: 28,
		Samples: []Sample{{Pixels: pixels, Label: 0, Rows: 28, Cols: 28}},
	}
	ds.Renormalize()

	if ds.Rows != imageprep.Side || ds.Cols != imageprep.Side {
		t.Fatalf("geometry = %dx%d, want %dx%d", ds.Rows, ds.Cols, imageprep.Side, imageprep.Side)
	}
	if ds.Samples[0].Rows != imageprep.Side || ds.Samples[0].Cols != imageprep.Side {
		t.Fatalf("per-sample geometry = %dx%d, want %dx%d",
			ds.Samples[0].Rows, ds.Samples[0].Cols, imageprep.Side, imageprep.Side)
	}
	got := ds.Samples[0].Pixels
	if len(got) != imageprep.Side*imageprep.Side {
		t.Fatalf("vector len = %d, want %d", len(got), imageprep.Side*imageprep.Side)
	}

	// The ink should now be centred near the middle of the frame.
	var mass, mx, my float64
	for y := 0; y < imageprep.Side; y++ {
		for x := 0; x < imageprep.Side; x++ {
			v := got[y*imageprep.Side+x]
			mass += v
			mx += v * float64(x)
			my += v * float64(y)
		}
	}
	if mass == 0 {
		t.Fatal("no ink after renormalisation")
	}
	cx, cy := mx/mass, my/mass
	if cx < 11 || cx > 17 || cy < 11 || cy > 17 {
		t.Fatalf("centre of mass (%.1f,%.1f) not centred near 14,14", cx, cy)
	}
}
