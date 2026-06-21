# handwriting — a Go neural network for handwritten logbook entries

A self-contained, **pure-Go** (standard library only, no third-party packages)
neural network that recognises handwritten characters and reads whole
handwritten logbook lines by segmenting them into characters first.

**Why this exists:** the rest of the app (PDF/Excel parsing, compliance,
templates) already works well; the one genuinely hard task is OCR of
*handwritten* logs, which PaddleOCR — tuned for printed text — does poorly. This
module is the dedicated handwriting engine for that one job. It plugs into the
Python pipeline via `handwriting_ocr.py` (see **Integration** below), so
handwritten scans are read by this trained neural net while everything else
stays in Python. It ships as a single static binary — no LLM, no Python ML
stack.

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
model/      gob save/load, int8 quantization, label alphabet (digits / letters)
cmd/handwriting/  CLI: train · eval · quantize · export-glyphs · predict · read
Makefile    build · test · model-mnist/emnist · embed · cross-compile · USB · docker-train
```

To train on **your own** handwritten logs (the way to real accuracy), see
[`TRAINING.md`](TRAINING.md): `export-glyphs` cuts real scans into labelled
glyphs, `train -dir` learns from the folders you sort them into, and
`Dockerfile.train` does it all without a Go toolchain.

## Build

```bash
cd handwriting
go build ./cmd/handwriting     # produces ./handwriting
go test ./...                  # XOR convergence, numeric-gradient check, etc.
```

## A trained model ships in the box

The binary already embeds a trained **digit** model — `make build` gives you a
recognizer that reads 0–9 out of the box at **~98% MNIST test accuracy** (int8,
~100 KB embedded). That covers a lot of real logbook content: tail numbers,
dates, hours, cycles, ATA codes. Reproduce or refresh it with:

```bash
make model-mnist   # downloads MNIST, trains, evaluates, quantizes, embeds
```

For **letters too** (full alphanumeric logbook text) train on EMNIST balanced
(47 classes: digits + upper/lowercase letters) and embed that instead:

```bash
make model-emnist  # downloads EMNIST, trains a 47-class model, quantizes, embeds
```

EMNIST is harder than MNIST (47 visually-confusable classes), so expect lower
per-character accuracy than the ~98% digit model — which is exactly why training
on your own logs (`TRAINING.md`) matters for production use.

## Get a training set

The model learns individual glyphs, so train it on a handwritten-character
corpus in IDX format:

- **MNIST** (digits 0–9) — https://storage.googleapis.com/cvdf-datasets/mnist/
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

## Packaging as a standalone app (USB-stick, no install, no LLM)

This tool has **no LLM and no Python dependency** — it never calls Qwen/Ollama
or PaddleOCR. That makes it trivial to ship as a single self-contained native
executable that someone can run from a USB stick with nothing to install.

Three pieces make that real (all driven by the `Makefile`):

**1. Shrink the model with int8 quantization.** `quantize` converts a trained
float model to symmetric int8 — ~8× smaller on disk for a negligible accuracy
hit (validated by a round-trip test):

```bash
./handwriting quantize -in digits.gob -out digits.q8.gob
# quantised digits.gob (447.5 KB) -> digits.q8.gob (50.9 KB int8)
```

(For this small MLP int8 is a nice-to-have, not a necessity — the binary is a
couple of MB either way. It becomes important if you grow to a large CRNN.)

**2. Embed the model into the binary** so the executable *is* the app — no
separate file to copy:

```bash
make embed-model MODEL=digits.q8.gob   # bakes it in, rebuilds
./handwriting predict -image glyph.png # note: no -model flag needed
```

The model is embedded via `//go:embed` (see `cmd/handwriting/embed.go`). If no
model is embedded the binary still builds and `-model` is simply required.

**3. Cross-compile to every OS from one machine.** CGO is disabled, so the
binaries are fully static — no DLLs, no libc version surprises:

```bash
make dist   # -> dist/handwriting-<ver>-windows-amd64.exe, darwin-arm64, linux-amd64, ...
make usb    # -> dist/usb/ : a ready-to-copy folder (Windows .exe + plain README.txt)
```

Copy `dist/usb/` to the stick. The recipient double-clicks / runs
`handwriting.exe read -image scan.png` — no installer, no admin rights, nothing
left behind on uninstall (`USB_README.txt` is the end-user instructions).

> Scope note: this packages the **handwriting recognizer**. The full aviation
> app (compliance, Veryon import, etc.) is the Python side; dropping *its* LLM
> dependency is a separate effort already partly covered by the root project's
> `build_portable.bat` lite bundle and `DISABLE_LLM=1` mode.

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

`handwriting_ocr.py` (in the repo root) is the bridge. It shells out to the
binary's JSON `read` mode and returns text, exposing the same shape as the
existing `ocr.py` helpers so it drops straight into the pipeline:

```python
import handwriting_ocr
ok, msg = handwriting_ocr.is_available()
text = handwriting_ocr.ocr_page("scan_of_handwritten_log.png")   # multi-line
text = handwriting_ocr.ocr_image(cv2_box_crop)                   # one field box
```

`ocr.py` already calls it automatically: when `HANDWRITING_OCR=1` is set,
`ocr.ocr_image` routes through the Go recognizer and **falls back to PaddleOCR**
on any error, so a misconfigured engine never breaks a scan.

Environment knobs:

| Variable | Purpose |
|---|---|
| `HANDWRITING_OCR=1` | turn the Go engine on for handwriting |
| `HANDWRITING_BIN`   | path to the binary (else auto-found under `handwriting/` or `$PATH`) |
| `HANDWRITING_MODEL` | path to a trained model (else the model embedded in the binary) |

The `read -json` output the bridge consumes looks like:

```json
{
  "text": "N123AB 100HR INSP",
  "lines": ["N123AB 100HR INSP"],
  "glyphs": [[{"char": "N", "confidence": 0.97, "x0": 4, "x1": 21}, ...]],
  "mean_confidence": 0.91
}
```

`mean_confidence` and the per-glyph scores let the Python side flag a scan for
human review instead of trusting a shaky reading — important when this feeds the
conservative compliance engine.

Because the binary is static and dependency-free, it fits the existing no-LLM /
low-RAM deployment targets (e.g. the 8 GB N100) described in the root README.
