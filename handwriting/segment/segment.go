// Package segment splits a handwritten line image into individual character
// glyphs so the per-character classifier can read a whole logbook entry.
//
// The approach is a vertical projection profile: sum ink down each column, then
// cut the line wherever the ink falls to (near) zero for a run of columns. Wide
// blank runs become spaces. This is deliberately simple and works well for the
// hand-PRINTED block capitals/digits typical of aviation logbooks and tech-log
// entries. Cursive (connected) writing needs a stronger segmentation-free model
// (CRNN+CTC); see the package README for that roadmap.
package segment

import (
	"image"

	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/imageprep"
)

// Glyph is one segmented character: its normalised 28×28 vector plus the source
// column span (useful for drawing debug overlays).
type Glyph struct {
	Pixels  []float64
	X0, X1  int
	IsSpace bool
}

// Params tunes the projection segmentation.
type Params struct {
	// InkThreshold: a column counts as "ink" if its summed ink exceeds this
	// fraction of the busiest column.
	InkThreshold float64
	// MinGap: blank columns needed to end a character.
	MinGap int
	// SpaceGap: blank columns wide enough to emit a space between words.
	SpaceGap int
	// MinWidth: discard specks narrower than this many columns.
	MinWidth int
}

// DefaultParams are reasonable for a ~30-60 px tall scanned line.
func DefaultParams() Params {
	return Params{InkThreshold: 0.06, MinGap: 2, SpaceGap: 12, MinWidth: 2}
}

// Line segments an image of a single text line into ordered glyphs.
func Line(img image.Image, p Params) []Glyph {
	grid := imageprep.FromImage(img)
	return segmentGrid(grid, p)
}

// internal: operate on an ink grid so tests can build grids directly.
func segmentGrid(g *imageprep.Grid, p Params) []Glyph {
	cols := columnInk(g)
	peak := 0.0
	for _, v := range cols {
		if v > peak {
			peak = v
		}
	}
	if peak == 0 {
		return nil
	}
	cut := peak * p.InkThreshold

	var glyphs []Glyph
	x := 0
	prevEnd := -1
	for x < len(cols) {
		// skip blank columns
		if cols[x] <= cut {
			x++
			continue
		}
		// found ink: extend until a gap of >= MinGap blank columns
		start := x
		end := x
		blank := 0
		for x < len(cols) {
			if cols[x] > cut {
				end = x
				blank = 0
			} else {
				blank++
				if blank >= p.MinGap {
					break
				}
			}
			x++
		}
		if end-start+1 < p.MinWidth {
			continue // speck / noise
		}
		// emit a space if the gap before this glyph was word-sized
		if prevEnd >= 0 && start-prevEnd >= p.SpaceGap {
			glyphs = append(glyphs, Glyph{IsSpace: true, X0: prevEnd, X1: start})
		}
		glyphs = append(glyphs, Glyph{
			Pixels: cropNormalize(g, start, end),
			X0:     start,
			X1:     end,
		})
		prevEnd = end
	}
	return glyphs
}

// columnInk returns the summed ink per column.
func columnInk(g *imageprep.Grid) []float64 {
	cols := make([]float64, g.W)
	for y := 0; y < g.H; y++ {
		for x := 0; x < g.W; x++ {
			cols[x] += g.Data[y*g.W+x]
		}
	}
	return cols
}

// cropNormalize extracts columns [x0,x1] (full height) and MNIST-normalises it.
func cropNormalize(g *imageprep.Grid, x0, x1 int) []float64 {
	w := x1 - x0 + 1
	sub := &imageprep.Grid{W: w, H: g.H, Data: make([]float64, w*g.H)}
	for y := 0; y < g.H; y++ {
		copy(sub.Data[y*w:(y+1)*w], g.Data[y*g.W+x0:y*g.W+x1+1])
	}
	return sub.Normalize()
}
