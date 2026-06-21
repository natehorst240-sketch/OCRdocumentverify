# handwriting — a Go neural network for handwritten logbook entries

A self-contained, **pure-Go** (standard library only, no third-party packages)
neural network that recognises handwritten characters and reads whole
handwritten logbook lines by segmenting them into characters first.

It is the local, dependency-free counterpart to the project's Python OCR stack
(`ocr.py`, PaddleOCR): where PaddleOCR is a heavyweight printed-text engine, this
module is a transparent, hackable handwriting model you can train yourself on
aviation logbook / tech-log glyphs and ship as a single binary.

The network is built from scratch — forward pass, cross-entropy loss, and
backpropagation by hand — in the spirit of the well-known
["Neural Net from Scratch in Go"](https://datadan.io/blog/neural-net-with-go)
tutorial, but generalised for real handwriting recognition:

| | tutorial | this module |
|---|---|---|
| hidden layers | one | any number |
| activation | sigmoid | ReLU (He init) + softmax output |
| loss | squared error | cross-entropy (correct for classification) |
| optimiser | full-batch GD | mini-batch SGD + momentum + L2 |
| dependencies | gonum | none (stdlib only) |
| task | iris flowers | 28×28 handwritten glyphs |

## Layout

```
nn/         feed-forward network: matrices, forward/backprop, training
data/       MNIST / EMNIST IDX dataset loader (handles .gz transparently)
imageprep/  scan → MNIST-style 28×28 normalised vector (grayscale, crop,
            scale-to-20px, centre-of-mass centring)
segment/    split a line image into per-character glyphs (projection profile)
model/      gob save/load + label alphabet (digits "0-9" / letters "A-Z")
cmd/handwriting/  CLI: train · eval · predict · read
```

## Build

```bash
cd handwriting
go build ./cmd/handwriting     # produces ./handwriting
go test ./...                  # XOR convergence, numeric-gradient check, etc.
```

## Get a training set

The model learns individual glyphs, so train it on a handwritten-character
corpus in IDX format:

- **MNIST** (digits 0–9) — http://yann.lecun.com/exdb/mnist/
- **EMNIST** (letters / balanced) — https://www.nist.gov/itl/products-and-services/emnist-dataset

Download the image/label files (the loader reads the `.gz` directly).

## Train

Digits (MNIST):

```bash
./handwriting train \
  -images train-images-idx3-ubyte.gz \
  -labels train-labels-idx1-ubyte.gz \
  -alphabet digits -out digits.gob -epochs 20 -hidden 128
```

Letters (EMNIST — note `-emnist` handles its transposed images and 1-indexed
labels):

```bash
./handwriting train \
  -images emnist-letters-train-images-idx3-ubyte.gz \
  -labels emnist-letters-train-labels-idx1-ubyte.gz \
  -alphabet letters -emnist -out letters.gob -epochs 25 -hidden 256,128
```

A 784-128-10 net trained this way reaches roughly **97 % top-1 accuracy** on the
MNIST test set. Use `-limit` for a quick laptop run, `-hidden a,b,c` to set the
hidden topology, and `-lr` / `-batch` to tune.

## Use

Classify a single cropped glyph:

```bash
./handwriting predict -model digits.gob -image seven.png
# 1. 7   0.992
# 2. 1   0.005
# 3. 9   0.002
```

Transcribe a whole handwritten line (segments → classifies each glyph →
assembles text; wide gaps become spaces):

```bash
./handwriting read -model digits.gob -image logbook_line.png -v
```

`-minconf 0.6` marks low-confidence glyphs with `·` so a human reviewer can spot
where the model was unsure — useful when these readings feed the compliance
pipeline, which must never silently guess.

## How a scan becomes input

`imageprep` reproduces the original MNIST preprocessing so real pen strokes land
in the distribution the model trained on:

1. decode (PNG/JPEG) → grayscale, auto-detecting ink polarity,
2. crop to the ink bounding box,
3. scale the longest side to 20 px (aspect preserved),
4. paste into 28×28, shifted so the **centre of mass** is centred.

## Scope and roadmap

This is an honest, working foundation, not a finished cursive-handwriting engine:

- **Works well today:** hand-*printed* block digits and capitals — exactly the
  style of most aviation logbook / tech-log entries (tail numbers, dates, ATA
  codes, part numbers, hours).
- **Known limit:** the line reader segments on whitespace, so **connected /
  cursive** writing where letters touch will mis-segment. The fix is a
  segmentation-free sequence model — a CRNN (CNN feature extractor + RNN) trained
  with **CTC loss** — which reads a variable-length line in one shot. The current
  package boundaries (`imageprep` for input, `nn` for the model, a future
  `seqnn` alongside it) are arranged so that can be added without disturbing the
  CLI.

  There are two ways to get there, and they compose cleanly with this code:

  1. **Train a CRNN+CTC here in pure Go** — extends `nn` with conv layers and a
     CTC loss. Most work, zero dependencies, fully self-hostable.
  2. **Run a pretrained model with [onnx-go](https://github.com/oramasearch/onnx-go).**
     Pragmatic shortcut: export an existing CRNN / TrOCR handwriting model to
     ONNX and run inference in Go without re-implementing CTC. Trade-offs to
     know going in — onnx-go is lightly maintained, supports a subset of ONNX
     operators, and pulls in Gorgonia (so the "stdlib-only" property is lost for
     that path). `imageprep` still does the front-end normalisation; only the
     `nn.Network` call site swaps for an onnx-go session. Good for getting strong
     accuracy fast; the from-scratch path above remains the dependency-free
     option.
- **Accuracy lever:** the MLP treats pixels independently. Adding a small
  convolutional front-end in `nn` is the highest-value next step for raw glyph
  accuracy.

## Integration with the Python app

The CLI is the contract: the Streamlit/Python side can shell out to
`handwriting read -model … -image …` for a fully local, no-Ollama handwriting
pass on a scanned field box, and parse the transcribed line from stdout. Because
the binary is static and dependency-free, it drops cleanly into the existing
no-LLM / low-RAM deployment targets (e.g. the 8 GB N100) described in the root
README.
