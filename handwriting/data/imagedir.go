package data

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/imageprep"
)

// imageExts are the raster formats LoadImageDir will pick up.
var imageExts = map[string]bool{
	".png": true, ".jpg": true, ".jpeg": true,
	".bmp": true, ".gif": true,
}

// LoadImageDir builds a dataset from a directory of labelled glyph images using
// the conventional "ImageFolder" layout: one sub-directory per class, named by
// the glyph it holds, each containing cropped character images.
//
//	data/
//	  0/   img1.png img2.png ...
//	  1/   ...
//	  A/   ...
//	  N/   ...
//
// This is the format you produce when labelling your own handwritten logs (see
// `export-glyphs` and TRAINING.md). Every image is run through the same MNIST-
// style normalisation used at inference, so training and prediction see glyphs
// the same way. Returns the dataset and the ordered class labels (sorted), so
// class index i corresponds to labels[i].
func LoadImageDir(root string) (*Dataset, []string, error) {
	entries, err := os.ReadDir(root)
	if err != nil {
		return nil, nil, err
	}

	// Collect class directories (sorted for a stable label ordering).
	var classes []string
	for _, e := range entries {
		if e.IsDir() {
			classes = append(classes, e.Name())
		}
	}
	if len(classes) == 0 {
		return nil, nil, fmt.Errorf("data: %s has no class sub-directories", root)
	}
	sort.Strings(classes)

	ds := &Dataset{Rows: imageprep.Side, Cols: imageprep.Side}
	for idx, class := range classes {
		dir := filepath.Join(root, class)
		files, err := os.ReadDir(dir)
		if err != nil {
			return nil, nil, err
		}
		for _, f := range files {
			if f.IsDir() || !imageExts[strings.ToLower(filepath.Ext(f.Name()))] {
				continue
			}
			grid, err := imageprep.LoadFile(filepath.Join(dir, f.Name()))
			if err != nil {
				return nil, nil, fmt.Errorf("data: %s: %w", f.Name(), err)
			}
			ds.Samples = append(ds.Samples, Sample{
				Pixels: grid.Normalize(),
				Label:  idx,
				Rows:   imageprep.Side,
				Cols:   imageprep.Side,
			})
		}
	}
	if len(ds.Samples) == 0 {
		return nil, nil, fmt.Errorf("data: no images found under %s", root)
	}
	return ds, classes, nil
}
