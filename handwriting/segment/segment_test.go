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

// TestSpaceGapBoundary locks the exact threshold: a gap of SpaceGap blank
// columns emits a space, but SpaceGap-1 does not.
func TestSpaceGapBoundary(t *testing.T) {
	p := DefaultParams()
	// Build two glyphs separated by exactly `gap` blank columns and count spaces.
	spacesFor := func(gap int) int {
		w, h := 40+gap, 20
		g := &imageprep.Grid{W: w, H: h, Data: make([]float64, w*h)}
		fill := func(x0, x1 int) {
			for y := 4; y < 16; y++ {
				for x := x0; x <= x1; x++ {
					g.Data[y*w+x] = 1
				}
			}
		}
		fill(2, 6)          // glyph A ends at col 6
		fill(7+gap, 11+gap) // glyph B starts after `gap` blank columns
		spaces := 0
		for _, gl := range segmentGrid(g, p) {
			if gl.IsSpace {
				spaces++
			}
		}
		return spaces
	}

	if s := spacesFor(p.SpaceGap - 1); s != 0 {
		t.Fatalf("gap SpaceGap-1 (%d): got %d spaces, want 0", p.SpaceGap-1, s)
	}
	if s := spacesFor(p.SpaceGap); s != 1 {
		t.Fatalf("gap SpaceGap (%d): got %d spaces, want 1", p.SpaceGap, s)
	}
}
