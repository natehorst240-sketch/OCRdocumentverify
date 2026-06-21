package data

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/imageprep"
)

// TestLoadImageDir writes a couple of glyph PNGs into class folders and checks
// they load with the right labels and normalised geometry.
func TestLoadImageDir(t *testing.T) {
	root := t.TempDir()
	// two classes "7" and "A", one image each
	for _, class := range []string{"7", "A"} {
		dir := filepath.Join(root, class)
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatal(err)
		}
		// a simple non-empty 28x28 ink vector
		vec := make([]float64, imageprep.Side*imageprep.Side)
		for i := 0; i < len(vec); i += 3 {
			vec[i] = 1
		}
		if err := imageprep.SavePNG(filepath.Join(dir, "g.png"), vec); err != nil {
			t.Fatal(err)
		}
	}

	ds, labels, err := LoadImageDir(root)
	if err != nil {
		t.Fatal(err)
	}
	if len(labels) != 2 || labels[0] != "7" || labels[1] != "A" {
		t.Fatalf("labels = %v, want [7 A] (sorted)", labels)
	}
	if len(ds.Samples) != 2 {
		t.Fatalf("got %d samples, want 2", len(ds.Samples))
	}
	if ds.Rows != imageprep.Side || ds.Cols != imageprep.Side {
		t.Fatalf("geometry = %dx%d, want %dx%d", ds.Rows, ds.Cols, imageprep.Side, imageprep.Side)
	}
	for _, s := range ds.Samples {
		if len(s.Pixels) != imageprep.Side*imageprep.Side {
			t.Fatalf("sample has %d pixels, want %d", len(s.Pixels), imageprep.Side*imageprep.Side)
		}
	}
}
