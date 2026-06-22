package segment

import (
	"image"

	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/imageprep"
)

// Line groups the glyphs of one text line together with its vertical extent in
// the source image.
type TextLine struct {
	Glyphs []Glyph
	Y0, Y1 int
}

// PageParams tunes how a multi-line block is split into lines before each line
// is split into glyphs.
type PageParams struct {
	Line Params
	// RowInkThreshold: a row counts as "ink" if its summed ink exceeds this
	// fraction of the busiest row.
	RowInkThreshold float64
	// MinRowGap: blank rows needed to end a line.
	MinRowGap int
	// MinLineHeight: discard bands shorter than this many rows (noise).
	MinLineHeight int
}

// DefaultPageParams suits a scanned logbook page at a few hundred px tall.
func DefaultPageParams() PageParams {
	return PageParams{
		Line:            DefaultParams(),
		RowInkThreshold: 0.04,
		MinRowGap:       3,
		MinLineHeight:   6,
	}
}

// Page segments a multi-line handwritten block into text lines, each already
// split into ordered glyphs. It first cuts horizontal bands by a row-wise
// projection profile (the same idea as column segmentation, rotated 90°), then
// runs the existing per-line glyph segmentation inside each band.
func Page(img image.Image, p PageParams) []TextLine {
	grid := imageprep.FromImage(img)
	return pageGrid(grid, p)
}

func pageGrid(g *imageprep.Grid, p PageParams) []TextLine {
	rows := rowInk(g)
	var peak float64
	for _, v := range rows {
		if v > peak {
			peak = v
		}
	}
	if peak == 0 {
		return nil
	}
	cut := peak * p.RowInkThreshold

	var lines []TextLine
	y := 0
	for y < len(rows) {
		if rows[y] <= cut {
			y++
			continue
		}
		start, end, blank := y, y, 0
		for y < len(rows) {
			if rows[y] > cut {
				end = y
				blank = 0
			} else {
				blank++
				if blank >= p.MinRowGap {
					break
				}
			}
			y++
		}
		if end-start+1 < p.MinLineHeight {
			continue
		}
		band := cropRows(g, start, end)
		lines = append(lines, TextLine{
			Glyphs: segmentGrid(band, p.Line),
			Y0:     start,
			Y1:     end,
		})
	}
	return lines
}

// rowInk returns summed ink per row.
func rowInk(g *imageprep.Grid) []float64 {
	out := make([]float64, g.H)
	for y := 0; y < g.H; y++ {
		var s float64
		for x := 0; x < g.W; x++ {
			s += g.Data[y*g.W+x]
		}
		out[y] = s
	}
	return out
}

// cropRows extracts the full-width band of rows [y0,y1] as its own grid.
func cropRows(g *imageprep.Grid, y0, y1 int) *imageprep.Grid {
	h := y1 - y0 + 1
	sub := &imageprep.Grid{W: g.W, H: h, Data: make([]float64, g.W*h)}
	copy(sub.Data, g.Data[y0*g.W:(y1+1)*g.W])
	return sub
}
