package imageprep

import (
	"fmt"
	"image"
	"image/png"
	"os"
)

// VectorToGray turns a normalised 28×28 ink vector back into a grayscale image
// (dark ink on white paper) so segmented glyphs can be written out for human
// labelling. Inverse of the ink-positive convention used during recognition.
// A short vector leaves the remaining pixels white; an over-long vector is
// truncated — SavePNG rejects wrong sizes outright.
func VectorToGray(vec []float64) *image.Gray {
	img := image.NewGray(image.Rect(0, 0, Side, Side))
	for i := range img.Pix {
		img.Pix[i] = 255 // white paper
	}
	n := len(vec)
	if n > len(img.Pix) {
		n = len(img.Pix)
	}
	for i := 0; i < n; i++ {
		v := vec[i]
		if v < 0 {
			v = 0
		} else if v > 1 {
			v = 1
		}
		img.Pix[i] = uint8(255 * (1 - v)) // ink (v=1) -> black
	}
	return img
}

// SavePNG writes a 28×28 ink vector to a PNG file.
func SavePNG(path string, vec []float64) error {
	if len(vec) != Side*Side {
		return fmt.Errorf("imageprep: expected %d pixels, got %d", Side*Side, len(vec))
	}
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	return png.Encode(f, VectorToGray(vec))
}
