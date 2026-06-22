package segment

import (
	"testing"

	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/imageprep"
)

// TestPageSplitsLines builds two horizontal bands of ink separated by a blank
// gap and checks the page segmenter recovers two lines, each with glyphs.
func TestPageSplitsLines(t *testing.T) {
	w, h := 60, 60
	g := &imageprep.Grid{W: w, H: h, Data: make([]float64, w*h)}
	fillBlock := func(x0, x1, y0, y1 int) {
		for y := y0; y <= y1; y++ {
			for x := x0; x <= x1; x++ {
				g.Data[y*w+x] = 1
			}
		}
	}
	// line 1: two glyphs near the top
	fillBlock(4, 9, 5, 15)
	fillBlock(16, 21, 5, 15)
	// line 2: two glyphs near the bottom (blank rows 16..40 between)
	fillBlock(4, 9, 45, 55)
	fillBlock(16, 21, 45, 55)

	lines := pageGrid(g, DefaultPageParams())
	if len(lines) != 2 {
		t.Fatalf("got %d lines, want 2", len(lines))
	}
	for i, ln := range lines {
		chars := 0
		for _, gl := range ln.Glyphs {
			if !gl.IsSpace {
				chars++
			}
		}
		if chars != 2 {
			t.Fatalf("line %d: got %d glyphs, want 2", i, chars)
		}
	}
}
