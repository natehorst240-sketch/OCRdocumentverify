// Command handwriting trains and runs a from-scratch Go neural network that
// recognises handwritten characters, and reads whole handwritten logbook lines
// by segmenting them into characters first.
//
// Subcommands:
//
//	train    train a model on an MNIST/EMNIST IDX dataset and save it
//	eval     report accuracy of a saved model on a test set
//	predict  classify a single glyph image (PNG/JPEG)
//	read     segment a line image and transcribe it to text
//
// Run a subcommand with -h to see its flags.
package main

import (
	"flag"
	"fmt"
	"image"
	_ "image/jpeg"
	_ "image/png"
	"math/rand"
	"os"
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
  handwriting train   -images F -labels F -out model.gob [options]
  handwriting eval     -model model.gob -images F -labels F
  handwriting predict  -model model.gob -image glyph.png
  handwriting read     -model model.gob -image line.png

run "handwriting <subcommand> -h" for the full flag list.
`)
}

// --- train ---

func cmdTrain(args []string) error {
	fs := flag.NewFlagSet("train", flag.ExitOnError)
	images := fs.String("images", "", "path to IDX images file (.idx/.gz)")
	labels := fs.String("labels", "", "path to IDX labels file (.idx/.gz)")
	out := fs.String("out", "model.gob", "output model path")
	alphabet := fs.String("alphabet", "digits", "label set: digits | letters")
	epochs := fs.Int("epochs", 20, "training epochs")
	batch := fs.Int("batch", 32, "mini-batch size")
	lr := fs.Float64("lr", 0.05, "learning rate")
	hidden := fs.String("hidden", "128", "comma-separated hidden layer sizes")
	limit := fs.Int("limit", 0, "cap training samples (0 = all; for quick runs)")
	val := fs.Float64("val", 0.1, "fraction of data held out for validation")
	emnist := fs.Bool("emnist", false, "treat images as EMNIST (transpose + 1-indexed labels)")
	seed := fs.Int64("seed", 1, "random seed")
	fs.Parse(args)

	if *images == "" || *labels == "" {
		return fmt.Errorf("train: -images and -labels are required")
	}

	labelSet, numClasses, transformLabel := alphabetSpec(*alphabet)
	if *emnist {
		// EMNIST letter labels are 1..26; shift to 0..25.
		transformLabel = func(l int) int { return l - 1 }
	}

	fmt.Printf("loading dataset %s / %s ...\n", *images, *labels)
	ds, err := data.LoadIDX(*images, *labels, *emnist, transformLabel)
	if err != nil {
		return err
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
	m := &model.Model{Net: net, Labels: labelSet, Dataset: *alphabet, Accuracy: acc}
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
	emnist := fs.Bool("emnist", false, "EMNIST geometry/labels")
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
	ds, err := data.LoadIDX(*images, *labels, *emnist, transform)
	if err != nil {
		return err
	}
	acc := m.Net.Evaluate(ds.Inputs(), ds.Labels())
	fmt.Printf("model %s  dataset %s  test-acc %.4f over %d samples\n",
		*modelPath, m.Dataset, acc, len(ds.Samples))
	return nil
}

// --- predict ---

func cmdPredict(args []string) error {
	fs := flag.NewFlagSet("predict", flag.ExitOnError)
	modelPath := fs.String("model", "model.gob", "model path")
	imgPath := fs.String("image", "", "glyph image (PNG/JPEG)")
	topK := fs.Int("topk", 3, "how many ranked guesses to show")
	fs.Parse(args)

	if *imgPath == "" {
		return fmt.Errorf("predict: -image is required")
	}
	m, err := model.Load(*modelPath)
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
	modelPath := fs.String("model", "model.gob", "model path")
	imgPath := fs.String("image", "", "line image (PNG/JPEG)")
	minConf := fs.Float64("minconf", 0.0, "mark glyphs below this confidence with '·'")
	verbose := fs.Bool("v", false, "print per-glyph confidence")
	fs.Parse(args)

	if *imgPath == "" {
		return fmt.Errorf("read: -image is required")
	}
	m, err := model.Load(*modelPath)
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

	glyphs := segment.Line(img, segment.DefaultParams())
	var sb strings.Builder
	for _, g := range glyphs {
		if g.IsSpace {
			sb.WriteByte(' ')
			continue
		}
		class, prob := m.Net.Classify(g.Pixels)
		ch := m.Label(class)
		if prob < *minConf {
			ch = "·"
		}
		sb.WriteString(ch)
		if *verbose {
			fmt.Printf("  cols %3d-%-3d  %-2s  %.3f\n", g.X0, g.X1, m.Label(class), prob)
		}
	}
	fmt.Println(sb.String())
	return nil
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
