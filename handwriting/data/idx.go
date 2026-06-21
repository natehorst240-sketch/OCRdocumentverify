// Package data loads handwritten-character datasets in the IDX file format used
// by MNIST (digits 0-9) and EMNIST (letters/balanced). These are the standard
// corpora for handwriting recognition, so a model trained here can recognise
// the individual glyphs that make up a logbook entry.
//
// IDX files are tiny and dependency-free to parse: a short big-endian header
// followed by raw unsigned bytes. The loader transparently handles gzip-
// compressed files (the form the datasets ship in), so you can point it at the
// downloaded *.gz directly.
package data

import (
	"compress/gzip"
	"encoding/binary"
	"fmt"
	"io"
	"os"
	"strings"
)

// Sample is one labelled glyph: a normalised pixel vector (length Rows*Cols,
// values in [0,1]) and its integer class label.
type Sample struct {
	Pixels []float64
	Label  int
	Rows   int
	Cols   int
}

// Dataset is a collection of samples sharing one image geometry.
type Dataset struct {
	Samples    []Sample
	Rows, Cols int
}

func openMaybeGzip(path string) (io.ReadCloser, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	if !strings.HasSuffix(path, ".gz") {
		return f, nil
	}
	gz, err := gzip.NewReader(f)
	if err != nil {
		f.Close()
		return nil, err
	}
	return &gzipReadCloser{gz: gz, f: f}, nil
}

type gzipReadCloser struct {
	gz *gzip.Reader
	f  *os.File
}

func (g *gzipReadCloser) Read(p []byte) (int, error) { return g.gz.Read(p) }
func (g *gzipReadCloser) Close() error {
	g.gz.Close()
	return g.f.Close()
}

// LoadIDX reads an images IDX file and a labels IDX file into a Dataset.
//
// EMNIST stores its images transposed relative to MNIST; pass transpose=true
// for EMNIST so glyphs come out upright. transformLabel optionally remaps raw
// label bytes (e.g. EMNIST letters are 1-indexed); pass nil for identity.
func LoadIDX(imagesPath, labelsPath string, transpose bool, transformLabel func(int) int) (*Dataset, error) {
	rows, cols, images, err := readImages(imagesPath, transpose)
	if err != nil {
		return nil, fmt.Errorf("read images %s: %w", imagesPath, err)
	}
	labels, err := readLabels(labelsPath)
	if err != nil {
		return nil, fmt.Errorf("read labels %s: %w", labelsPath, err)
	}
	if len(images) != len(labels) {
		return nil, fmt.Errorf("data: %d images but %d labels", len(images), len(labels))
	}
	ds := &Dataset{Rows: rows, Cols: cols, Samples: make([]Sample, len(images))}
	for i := range images {
		label := labels[i]
		if transformLabel != nil {
			label = transformLabel(label)
		}
		ds.Samples[i] = Sample{Pixels: images[i], Label: label, Rows: rows, Cols: cols}
	}
	return ds, nil
}

func readImages(path string, transpose bool) (rows, cols int, out [][]float64, err error) {
	r, err := openMaybeGzip(path)
	if err != nil {
		return 0, 0, nil, err
	}
	defer r.Close()

	var hdr [4]uint32
	if err := binary.Read(r, binary.BigEndian, &hdr); err != nil {
		return 0, 0, nil, err
	}
	if hdr[0] != 0x00000803 {
		return 0, 0, nil, fmt.Errorf("data: bad image magic 0x%08x (want 0x00000803)", hdr[0])
	}
	n, rows, cols := int(hdr[1]), int(hdr[2]), int(hdr[3])
	px := rows * cols

	buf, err := io.ReadAll(r)
	if err != nil {
		return 0, 0, nil, err
	}
	if len(buf) < n*px {
		return 0, 0, nil, fmt.Errorf("data: image payload short: %d < %d", len(buf), n*px)
	}

	out = make([][]float64, n)
	for i := 0; i < n; i++ {
		img := make([]float64, px)
		raw := buf[i*px : (i+1)*px]
		if transpose {
			for r := 0; r < rows; r++ {
				for c := 0; c < cols; c++ {
					img[r*cols+c] = float64(raw[c*rows+r]) / 255.0
				}
			}
		} else {
			for j := 0; j < px; j++ {
				img[j] = float64(raw[j]) / 255.0
			}
		}
		out[i] = img
	}
	return rows, cols, out, nil
}

func readLabels(path string) ([]int, error) {
	r, err := openMaybeGzip(path)
	if err != nil {
		return nil, err
	}
	defer r.Close()

	var hdr [2]uint32
	if err := binary.Read(r, binary.BigEndian, &hdr); err != nil {
		return nil, err
	}
	if hdr[0] != 0x00000801 {
		return nil, fmt.Errorf("data: bad label magic 0x%08x (want 0x00000801)", hdr[0])
	}
	buf, err := io.ReadAll(r)
	if err != nil {
		return nil, err
	}
	n := int(hdr[1])
	if len(buf) < n {
		return nil, fmt.Errorf("data: label payload short: %d < %d", len(buf), n)
	}
	out := make([]int, n)
	for i := 0; i < n; i++ {
		out[i] = int(buf[i])
	}
	return out, nil
}
