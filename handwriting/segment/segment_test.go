package segment

import (
	"testing"

	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/imageprep"
)

// TestSegmentCountsGlyphsAndSpace builds a grid with three ink blocks where the
// gap between the 2nd and 3rd is word-sized, and checks we recover 3 glyphs and
// one space between the words.
func TestSegmentCountsGlyphsAndSpace(t *testing.T) {
	w, h := 60, 20
	g := &imageprep.Grid{W: w, H: h, Data: make([]float64, w*h)}
	fillCol := func(x0, x1 int) {
		for y := 4; y < 16; y++ {
			for x := x0; x <= x1; x++ {
				g.Data[y*w+x] = 1
			}
		}
	}
	fillCol(2, 6)   // glyph 1
	fillCol(10, 14) // glyph 2 (small gap -> same word)
	fillCol(40, 44) // glyph 3 (big gap -> new word)

	glyphs := segmentGrid(g, DefaultParams())

	var chars, spaces int
	for _, gl := range glyphs {
		if gl.IsSpace {
			spaces++
		} else {
			chars++
		}
	}
	if chars != 3 {
		t.Fatalf("got %d character glyphs, want 3", chars)
	}
	if spaces != 1 {
		t.Fatalf("got %d spaces, want 1", spaces)
	}
}
