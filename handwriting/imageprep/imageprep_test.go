package imageprep

import (
	"image"
	"image/color"
	"testing"
)

// TestNormalizeCenters draws a small filled square in a corner and checks that
// after normalisation its ink ends up centred in the 28×28 frame.
func TestNormalizeCenters(t *testing.T) {
	img := image.NewGray(image.Rect(0, 0, 100, 100))
	// white background
	for i := range img.Pix {
		img.Pix[i] = 255
	}
	// black square in the top-left corner (the "ink")
	for y := 5; y < 25; y++ {
		for x := 5; x < 25; x++ {
			img.SetGray(x, y, color.Gray{Y: 0})
		}
	}
	g := FromImage(img)
	vec := g.Normalize()
	if len(vec) != Side*Side {
		t.Fatalf("got %d pixels, want %d", len(vec), Side*Side)
	}

	// centre of mass should be near the middle of the frame
	var mass, mx, my float64
	for y := 0; y < Side; y++ {
		for x := 0; x < Side; x++ {
			v := vec[y*Side+x]
			mass += v
			mx += v * float64(x)
			my += v * float64(y)
		}
	}
	if mass == 0 {
		t.Fatal("no ink after normalisation")
	}
	cx, cy := mx/mass, my/mass
	if cx < 11 || cx > 17 || cy < 11 || cy > 17 {
		t.Fatalf("centre of mass (%.1f,%.1f) not centred near 14,14", cx, cy)
	}
}

// TestPolarityAutoInvert ensures a dark-background/bright-ink image is read with
// the same polarity as paper scans.
func TestPolarityAutoInvert(t *testing.T) {
	img := image.NewGray(image.Rect(0, 0, 10, 10))
	// mostly black with a small bright mark -> already ink-positive, must stay
	for y := 0; y < 10; y++ {
		for x := 0; x < 10; x++ {
			img.SetGray(x, y, color.Gray{Y: 0})
		}
	}
	img.SetGray(5, 5, color.Gray{Y: 255})
	g := FromImage(img)
	if g.at(5, 5) < 0.5 {
		t.Fatalf("bright ink mark lost after polarity handling: %.2f", g.at(5, 5))
	}
}
