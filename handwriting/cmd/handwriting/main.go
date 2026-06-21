// Command handwriting trains and runs a from-scratch Go neural network that
// recognises handwritten characters, and reads whole handwritten logbook lines
// by segmenting them into characters first.
//
// Subcommands:
//
//	train     train a model on an MNIST/EMNIST IDX dataset and save it
//	eval      report accuracy of a saved model on a test set
//	quantize  shrink a trained model to int8 for embedding/shipping
//	predict   classify a single glyph image (PNG/JPEG)
//	read      transcribe a line (or a page with -multiline) to text/JSON
//
// Run a subcommand with -h to see its flags.
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"image"
	_ "image/jpeg"
	_ "image/png"
	"math/rand"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/data"
	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/imageprep"
	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/model"
	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/nn"
	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/segment"
)

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	var err error
	switch os.Args[1] {
	case "train":
		err = cmdTrain(os.Args[2:])
	case "eval":
		err = cmdEval(os.Args[2:])
	case "predict":
		err = cmdPredict(os.Args[2:])
	case "read":
		err = cmdRead(os.Args[2:])
	case "quantize":
		err = cmdQuantize(os.Args[2:])
	case "export-glyphs":
		err = cmdExportGlyphs(os.Args[2:])
	case "-h", "--help", "help":
		usage()
		return
	default:
		fmt.Fprintf(os.Stderr, "unknown subcommand %q\n\n", os.Args[1])
		usage()
		os.Exit(2)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}

func usage() {
	fmt.Fprint(os.Stderr, `handwriting — Go neural net for handwritten logbook recognition

usage:
  handwriting train    -images F -labels F -out model.gob [options]
  handwriting eval     -model model.gob -images F -labels F
  handwriting quantize -in model.gob -out model.q8.gob
  handwriting predict  [-model model.gob] -image glyph.png
  handwriting read     [-model model.gob] -image line.png
  handwriting export-glyphs -image page.png -out dir/   (label your own logs)

-model is optional when a default model is embedded in the binary.
run "handwriting <subcommand> -h" for the full flag list.
`)
}

// --- train ---

func cmdTrain(args []string) error {
	fs := flag.NewFlagSet("train", flag.ExitOnError)
	images := fs.String("images", "", "path to IDX images file (.idx/.gz)")
	labels := fs.String("labels", "", "path to IDX labels file (.idx/.gz)")
	dir := fs.String("dir", "", "train from a folder of labelled glyph images (one sub-dir per class) instead of IDX")
	out := fs.String("out", "model.gob", "output model path")
	alphabet := fs.String("alphabet", "digits", "label set: digits | letters")
	mapping := fs.String("mapping", "", "EMNIST class->ASCII mapping file (e.g. emnist-balanced-mapping.txt); overrides -alphabet")
	epochs := fs.Int("epochs", 20, "training epochs")
	batch := fs.Int("batch", 32, "mini-batch size")
	lr := fs.Float64("lr", 0.05, "learning rate")
	hidden := fs.String("hidden", "128", "comma-separated hidden layer sizes")
	limit := fs.Int("limit", 0, "cap training samples (0 = all; for quick runs)")
	val := fs.Float64("val", 0.1, "fraction of data held out for validation")
	emnist := fs.Bool("emnist", false, "EMNIST letters split (transpose + 1-indexed labels)")
	transpose := fs.Bool("transpose", false, "transpose images (all EMNIST splits store them rotated)")
	normalize := fs.Bool("normalize", true, "re-normalize IDX glyphs through imageprep so training matches inference framing")
	seed := fs.Int64("seed", 1, "random seed")
	fs.Parse(args)

	if *dir == "" && (*images == "" || *labels == "") {
		return fmt.Errorf("train: provide -dir, or both -images and -labels")
	}

	labelSet, numClasses, transformLabel := alphabetSpec(*alphabet)
	datasetName := *alphabet
	var ds *data.Dataset
	var err error

	if *dir != "" {
		// Train on the user's own labelled glyph folders (see TRAINING.md).
		fmt.Printf("loading image folder %s ...\n", *dir)
		ds, labelSet, err = data.LoadImageDir(*dir)
		if err != nil {
			return err
		}
		numClasses = len(labelSet)
		datasetName = "imagedir:" + filepath.Base(*dir)
	} else {
		switch {
		case *mapping != "":
			// EMNIST balanced/byclass/digits: 0-based labels; the mapping file
			// gives the printable glyph per class.
			labelSet, err = loadMapping(*mapping)
			if err != nil {
				return err
			}
			numClasses, transformLabel = len(labelSet), nil
			datasetName = "emnist:" + filepath.Base(*mapping)
		case *emnist:
			// EMNIST letters: labels are 1..26; shift to 0..25.
			transformLabel = func(l int) int { return l - 1 }
			datasetName = "emnist-letters"
		}
		doTranspose := *emnist || *transpose || *mapping != ""
		fmt.Printf("loading dataset %s / %s ...\n", *images, *labels)
		ds, err = data.LoadIDX(*images, *labels, doTranspose, transformLabel)
		if err != nil {
			return err
		}
		if *normalize {
			// Match the inference front-end so the model works on real scans,
			// not just the dataset's own framing (critical for EMNIST).
			ds.Renormalize()
		}
	}

	rng := rand.New(rand.NewSource(*seed))
	ds.Shuffle(rng)
	ds = ds.Limit(*limit)
	valSet, trainSet := ds.Split(*val)
	fmt.Printf("samples: %d train, %d validation; %d classes\n",
		len(trainSet.Samples), len(valSet.Samples), numClasses)

	layers := append([]int{ds.Rows * ds.Cols}, parseHidden(*hidden)...)
	layers = append(layers, numClasses)

	cfg := nn.DefaultConfig(numClasses)
	cfg.Layers = layers
	cfg.Epochs = *epochs
	cfg.BatchSize = *batch
	cfg.LearningRate = *lr
	cfg.Seed = *seed

	net := nn.New(layers, rng)
	fmt.Printf("network: %v\n", layers)

	valInputs, valLabels := valSet.Inputs(), valSet.Labels()
	err = net.Train(cfg, trainSet.Inputs(), trainSet.OneHot(numClasses), func(epoch int, loss float64) {
		acc := net.Evaluate(valInputs, valLabels)
		fmt.Printf("epoch %3d/%d  loss %.4f  val-acc %.4f\n", epoch, cfg.Epochs, loss, acc)
	})
	if err != nil {
		return err
	}

	acc := net.Evaluate(valInputs, valLabels)
	m := &model.Model{Net: net, Labels: labelSet, Dataset: datasetName, Accuracy: acc}
	if err := m.Save(*out); err != nil {
		return err
	}
	fmt.Printf("saved %s  (val-acc %.4f)\n", *out, acc)
	return nil
}

// --- eval ---

func cmdEval(args []string) error {
	fs := flag.NewFlagSet("eval", flag.ExitOnError)
	modelPath := fs.String("model", "model.gob", "model path")
	images := fs.String("images", "", "IDX images file")
	labels := fs.String("labels", "", "IDX labels file")
	emnist := fs.Bool("emnist", false, "EMNIST letters split (transpose + 1-indexed labels)")
	transpose := fs.Bool("transpose", false, "transpose images (EMNIST balanced/byclass/digits)")
	normalize := fs.Bool("normalize", false, "re-normalize through imageprep (match a model trained with -normalize)")
	fs.Parse(args)

	if *images == "" || *labels == "" {
		return fmt.Errorf("eval: -images and -labels are required")
	}
	m, err := model.Load(*modelPath)
	if err != nil {
		return err
	}
	var transform func(int) int
	if *emnist {
		transform = func(l int) int { return l - 1 }
	}
	ds, err := data.LoadIDX(*images, *labels, *emnist || *transpose, transform)
	if err != nil {
		return err
	}
	if *normalize {
		ds.Renormalize()
	}
	acc := m.Net.Evaluate(ds.Inputs(), ds.Labels())
	fmt.Printf("model %s  dataset %s  test-acc %.4f over %d samples\n",
		*modelPath, m.Dataset, acc, len(ds.Samples))
	return nil
}

// --- quantize ---

func cmdQuantize(args []string) error {
	fs := flag.NewFlagSet("quantize", flag.ExitOnError)
	in := fs.String("in", "", "input float model")
	out := fs.String("out", "", "output int8 model")
	fs.Parse(args)

	if *in == "" || *out == "" {
		return fmt.Errorf("quantize: -in and -out are required")
	}
	m, err := model.Load(*in)
	if err != nil {
		return err
	}
	if m.Quantized() {
		return fmt.Errorf("quantize: %s is already quantised", *in)
	}
	m.Quantize()
	if err := m.Save(*out); err != nil {
		return err
	}
	inSize, _ := fileSize(*in)
	outSize, _ := fileSize(*out)
	fmt.Printf("quantised %s (%s) -> %s (%s int8)\n",
		*in, humanBytes(inSize), *out, humanBytes(outSize))
	return nil
}

func fileSize(path string) (int64, error) {
	fi, err := os.Stat(path)
	if err != nil {
		return 0, err
	}
	return fi.Size(), nil
}

func humanBytes(n int64) string {
	switch {
	case n >= 1<<20:
		return fmt.Sprintf("%.1f MB", float64(n)/(1<<20))
	case n >= 1<<10:
		return fmt.Sprintf("%.1f KB", float64(n)/(1<<10))
	default:
		return fmt.Sprintf("%d B", n)
	}
}

// --- export-glyphs ---

// cmdExportGlyphs segments a real handwritten page into individual glyph images
// (normalised exactly as the trainer expects) and writes them to a folder for a
// human to label. This is step one of building a model on your own logs: run it
// over real scans, sort the PNGs into class sub-folders, then `train -dir`.
func cmdExportGlyphs(args []string) error {
	fs := flag.NewFlagSet("export-glyphs", flag.ExitOnError)
	imgPath := fs.String("image", "", "page/line image to segment (PNG/JPEG)")
	outDir := fs.String("out", "glyphs", "directory to write glyph PNGs into")
	singleLine := fs.Bool("line", false, "treat the image as one line (default: multi-line page)")
	modelPath := fs.String("model", "", "optional model: also pre-label each glyph in its filename")
	fs.Parse(args)

	if *imgPath == "" {
		return fmt.Errorf("export-glyphs: -image is required")
	}
	f, err := os.Open(*imgPath)
	if err != nil {
		return err
	}
	defer f.Close()
	img, _, err := image.Decode(f)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(*outDir, 0o755); err != nil {
		return err
	}

	// A model is optional here; when present we pre-label to speed up sorting.
	var m *model.Model
	if *modelPath != "" || hasEmbeddedModel() {
		if mm, e := resolveModel(*modelPath); e == nil {
			m = mm
		}
	}

	var lines []segment.TextLine
	if *singleLine {
		lines = []segment.TextLine{{Glyphs: segment.Line(img, segment.DefaultParams())}}
	} else {
		lines = segment.Page(img, segment.DefaultPageParams())
	}

	base := strings.TrimSuffix(filepath.Base(*imgPath), filepath.Ext(*imgPath))
	count := 0
	for li, line := range lines {
		for gi, g := range line.Glyphs {
			if g.IsSpace {
				continue
			}
			guess := ""
			if m != nil {
				class, _ := m.Net.Classify(g.Pixels)
				guess = sanitizeLabel(m.Label(class)) + "_"
			}
			name := fmt.Sprintf("%s%s_l%02d_g%02d.png", guess, base, li, gi)
			if err := imageprep.SavePNG(filepath.Join(*outDir, name), g.Pixels); err != nil {
				return err
			}
			count++
		}
	}
	fmt.Printf("wrote %d glyph images to %s/\n", count, *outDir)
	if m != nil {
		fmt.Println("filenames are prefixed with the model's guess — correct them by")
		fmt.Println("moving each PNG into a sub-folder named for its true character.")
	}
	return nil
}

// sanitizeLabel makes a class glyph safe for a filename prefix.
func sanitizeLabel(s string) string {
	switch s {
	case "/", "\\", ":", "*", "?", "\"", "<", ">", "|", " ", "":
		return "x"
	default:
		return s
	}
}

// --- predict ---

func cmdPredict(args []string) error {
	fs := flag.NewFlagSet("predict", flag.ExitOnError)
	modelPath := fs.String("model", "", "model path (optional if a model is embedded)")
	imgPath := fs.String("image", "", "glyph image (PNG/JPEG)")
	topK := fs.Int("topk", 3, "how many ranked guesses to show")
	fs.Parse(args)

	if *imgPath == "" {
		return fmt.Errorf("predict: -image is required")
	}
	m, err := resolveModel(*modelPath)
	if err != nil {
		return err
	}
	grid, err := imageprep.LoadFile(*imgPath)
	if err != nil {
		return err
	}
	probs := m.Net.Predict(grid.Normalize())
	for i, r := range ranked(probs, *topK) {
		fmt.Printf("%d. %-2s  %.3f\n", i+1, m.Label(r.class), r.prob)
	}
	return nil
}

// --- read ---

func cmdRead(args []string) error {
	fs := flag.NewFlagSet("read", flag.ExitOnError)
	modelPath := fs.String("model", "", "model path (optional if a model is embedded)")
	imgPath := fs.String("image", "", "image (PNG/JPEG): one line, or a page with -multiline")
	minConf := fs.Float64("minconf", 0.0, "mark glyphs below this confidence with '·'")
	multiline := fs.Bool("multiline", false, "segment the image into multiple text lines first")
	asJSON := fs.Bool("json", false, "emit structured JSON (text + per-glyph confidence)")
	verbose := fs.Bool("v", false, "print per-glyph confidence to stderr")
	fs.Parse(args)

	if *imgPath == "" {
		return fmt.Errorf("read: -image is required")
	}
	m, err := resolveModel(*modelPath)
	if err != nil {
		return err
	}
	f, err := os.Open(*imgPath)
	if err != nil {
		return err
	}
	defer f.Close()
	img, _, err := image.Decode(f)
	if err != nil {
		return err
	}

	// Normalise to a list of lines so single-line and page modes share one path.
	var lines []segment.TextLine
	if *multiline {
		lines = segment.Page(img, segment.DefaultPageParams())
	} else {
		b := img.Bounds()
		lines = []segment.TextLine{{
			Glyphs: segment.Line(img, segment.DefaultParams()),
			Y0:     0, Y1: b.Dy() - 1,
		}}
	}

	result := transcribe(m, lines, *minConf, *verbose)
	if *asJSON {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(result)
	}
	fmt.Println(result.Text)
	return nil
}

// readGlyph is one recognised character with its confidence and source span.
type readGlyph struct {
	Char       string  `json:"char"`
	Confidence float64 `json:"confidence"`
	X0         int     `json:"x0"`
	X1         int     `json:"x1"`
}

// readResult is the structured transcription of an image.
type readResult struct {
	Text           string        `json:"text"`
	Lines          []string      `json:"lines"`
	Glyphs         [][]readGlyph `json:"glyphs"`
	LineBounds     [][2]int      `json:"line_bounds"` // [y0,y1] per line, source pixels
	MeanConfidence float64       `json:"mean_confidence"`
}

// transcribe classifies every glyph in every line and assembles the result.
func transcribe(m *model.Model, lines []segment.TextLine, minConf float64, verbose bool) readResult {
	var res readResult
	var confSum float64
	var confN int
	for li, line := range lines {
		var sb strings.Builder
		var lineGlyphs []readGlyph
		for _, g := range line.Glyphs {
			if g.IsSpace {
				sb.WriteByte(' ')
				continue
			}
			class, prob := m.Net.Classify(g.Pixels)
			ch := m.Label(class)
			confSum += prob
			confN++
			if prob < minConf {
				ch = "·"
			}
			sb.WriteString(ch)
			lineGlyphs = append(lineGlyphs, readGlyph{Char: m.Label(class), Confidence: prob, X0: g.X0, X1: g.X1})
			if verbose {
				fmt.Fprintf(os.Stderr, "  line %d  cols %3d-%-3d  %-2s  %.3f\n", li, g.X0, g.X1, m.Label(class), prob)
			}
		}
		res.Lines = append(res.Lines, sb.String())
		res.Glyphs = append(res.Glyphs, lineGlyphs)
		res.LineBounds = append(res.LineBounds, [2]int{line.Y0, line.Y1})
	}
	res.Text = strings.Join(res.Lines, "\n")
	if confN > 0 {
		res.MeanConfidence = confSum / float64(confN)
	}
	return res
}

// --- helpers ---

type rankedClass struct {
	class int
	prob  float64
}

func ranked(probs []float64, k int) []rankedClass {
	rs := make([]rankedClass, len(probs))
	for i, p := range probs {
		rs[i] = rankedClass{i, p}
	}
	sort.Slice(rs, func(i, j int) bool { return rs[i].prob > rs[j].prob })
	if k > 0 && k < len(rs) {
		rs = rs[:k]
	}
	return rs
}

// loadMapping reads an EMNIST "class_index ascii_code" mapping file into an
// ordered label slice, so class i prints as the glyph mapping[i]. Classes are
// expected to be 0-based and contiguous.
func loadMapping(path string) ([]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	pairs := map[int]string{}
	maxIdx := -1
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		fields := strings.Fields(sc.Text())
		if len(fields) < 2 {
			continue
		}
		var idx, code int
		if _, err := fmt.Sscan(fields[0], &idx); err != nil {
			continue
		}
		if _, err := fmt.Sscan(fields[1], &code); err != nil {
			continue
		}
		pairs[idx] = string(rune(code))
		if idx > maxIdx {
			maxIdx = idx
		}
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	if maxIdx < 0 {
		return nil, fmt.Errorf("mapping %s: no usable entries", path)
	}
	labels := make([]string, maxIdx+1)
	for i := range labels {
		if g, ok := pairs[i]; ok {
			labels[i] = g
		} else {
			labels[i] = "?"
		}
	}
	return labels, nil
}

func alphabetSpec(name string) (labels []string, numClasses int, transform func(int) int) {
	switch name {
	case "letters":
		return model.LetterLabels(), 26, nil
	default: // digits
		return model.DigitLabels(), 10, nil
	}
}

func parseHidden(s string) []int {
	var out []int
	for _, part := range strings.Split(s, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		var v int
		fmt.Sscanf(part, "%d", &v)
		if v > 0 {
			out = append(out, v)
		}
	}
	if len(out) == 0 {
		out = []int{128}
	}
	return out
}
