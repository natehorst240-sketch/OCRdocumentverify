// Package imageprep turns an arbitrary scanned glyph into the 28×28 normalised
// vector the network expects. It reproduces the preprocessing MNIST itself used,
// so a real-world pen stroke lands in the same distribution the model trained on:
//
//  1. decode (PNG/JPEG) and convert to grayscale,
//  2. invert if needed so ink is bright on a dark background,
//  3. crop to the ink's bounding box,
//  4. scale the longest side to 20 px (preserving aspect ratio),
//  5. paste into a 28×28 frame, shifting so the centre of mass sits in the
//     middle — exactly the MNIST recipe.
//
// Only the standard library image packages are used.
package imageprep

import (
	"fmt"
	"image"
	_ "image/jpeg" // register decoders
	_ "image/png"
	"math"
	"os"
)

const (
	// Side is the network's input image dimension (28×28 like MNIST/EMNIST).
	Side = 28
	// inner is the box the glyph is scaled into before centring.
	inner = 20
)

// Grid is a row-major grayscale image with values in [0,1], 1 == ink.
type Grid struct {
	W, H int
	Data []float64
}

func (g *Grid) at(x, y int) float64 { return g.Data[y*g.W+x] }

// LoadFile decodes an image file to a normalised ink Grid.
func LoadFile(path string) (*Grid, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	img, _, err := image.Decode(f)
	if err != nil {
		return nil, fmt.Errorf("imageprep: decode %s: %w", path, err)
	}
	return FromImage(img), nil
}

// FromImage converts any image.Image into an ink Grid. Ink is detected as the
// darker pixels: if the image is mostly dark already (a photo negative or a
// pre-inverted scan) the polarity is flipped automatically.
func FromImage(img image.Image) *Grid {
	b := img.Bounds()
	g := &Grid{W: b.Dx(), H: b.Dy(), Data: make([]float64, b.Dx()*b.Dy())}
	var sum float64
	for y := 0; y < g.H; y++ {
		for x := 0; x < g.W; x++ {
			r, gr, bl, _ := img.At(b.Min.X+x, b.Min.Y+y).RGBA()
			// luminance in [0,1]; 1 == white paper, 0 == black ink
			lum := (0.299*float64(r) + 0.587*float64(gr) + 0.114*float64(bl)) / 65535.0
			ink := 1 - lum // ink-positive
			g.Data[y*g.W+x] = ink
			sum += ink
		}
	}
	// If "ink" covers more than half the page, we mistook background for ink.
	if sum > float64(g.W*g.H)*0.5 {
		for i := range g.Data {
			g.Data[i] = 1 - g.Data[i]
		}
	}
	return g
}

// Normalize returns the MNIST-style 28×28 vector for the glyph in g.
func (g *Grid) Normalize() []float64 {
	x0, y0, x1, y1, any := g.boundingBox(0.15)
	if !any {
		return make([]float64, Side*Side) // blank glyph
	}
	cw, ch := x1-x0+1, y1-y0+1

	// scale longest side to `inner`, preserving aspect ratio
	scale := float64(inner) / math.Max(float64(cw), float64(ch))
	dw := int(math.Round(float64(cw) * scale))
	dh := int(math.Round(float64(ch) * scale))
	if dw < 1 {
		dw = 1
	}
	if dh < 1 {
		dh = 1
	}
	scaled := g.resizeRegion(x0, y0, cw, ch, dw, dh)

	// centre of mass of the scaled glyph
	var mass, mx, my float64
	for y := 0; y < dh; y++ {
		for x := 0; x < dw; x++ {
			v := scaled[y*dw+x]
			mass += v
			mx += v * float64(x)
			my += v * float64(y)
		}
	}
	out := make([]float64, Side*Side)
	if mass == 0 {
		return out
	}
	comX, comY := mx/mass, my/mass
	offX := int(math.Round(Side/2.0 - comX))
	offY := int(math.Round(Side/2.0 - comY))

	for y := 0; y < dh; y++ {
		ty := y + offY
		if ty < 0 || ty >= Side {
			continue
		}
		for x := 0; x < dw; x++ {
			tx := x + offX
			if tx < 0 || tx >= Side {
				continue
			}
			out[ty*Side+tx] = scaled[y*dw+x]
		}
	}
	return out
}

// boundingBox returns the tight box around pixels above thresh (relative to the
// grid's peak ink). The last result reports whether any ink was found.
func (g *Grid) boundingBox(thresh float64) (x0, y0, x1, y1 int, found bool) {
	var peak float64
	for _, v := range g.Data {
		if v > peak {
			peak = v
		}
	}
	cut := peak * thresh
	x0, y0 = g.W, g.H
	for y := 0; y < g.H; y++ {
		for x := 0; x < g.W; x++ {
			if g.at(x, y) > cut {
				found = true
				if x < x0 {
					x0 = x
				}
				if x > x1 {
					x1 = x
				}
				if y < y0 {
					y0 = y
				}
				if y > y1 {
					y1 = y
				}
			}
		}
	}
	return x0, y0, x1, y1, found
}

// resizeRegion area-samples a sub-rectangle of g into a dw×dh slice. Box
// (area) sampling is the right filter for shrinking line art — it avoids the
// aliasing a naive nearest-neighbour would introduce on thin pen strokes.
func (g *Grid) resizeRegion(sx, sy, sw, sh, dw, dh int) []float64 {
	out := make([]float64, dw*dh)
	for dy := 0; dy < dh; dy++ {
		fy0 := float64(dy) / float64(dh) * float64(sh)
		fy1 := float64(dy+1) / float64(dh) * float64(sh)
		for dx := 0; dx < dw; dx++ {
			fx0 := float64(dx) / float64(dw) * float64(sw)
			fx1 := float64(dx+1) / float64(dw) * float64(sw)
			var sum, area float64
			for yy := int(fy0); yy < int(math.Ceil(fy1)); yy++ {
				cover := overlap(float64(yy), float64(yy+1), fy0, fy1)
				for xx := int(fx0); xx < int(math.Ceil(fx1)); xx++ {
					w := cover * overlap(float64(xx), float64(xx+1), fx0, fx1)
					sum += w * g.at(sx+xx, sy+yy)
					area += w
				}
			}
			if area > 0 {
				out[dy*dw+dx] = sum / area
			}
		}
	}
	return out
}

func overlap(a0, a1, b0, b1 float64) float64 {
	lo := math.Max(a0, b0)
	hi := math.Min(a1, b1)
	if hi <= lo {
		return 0
	}
	return hi - lo
}
