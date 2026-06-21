# Training the handwriting recognizer on your own logs

The model shipped in the binary is trained on public datasets (MNIST digits,
optionally EMNIST letters). Real aviation logbooks have their own hands, pens,
and quirks, so the way to get genuinely good accuracy is to train on **your
own** scans before publishing. This is a human-in-the-loop loop:

```
 real scans ──► export-glyphs ──► (human labels) ──► train -dir ──► quantize ──► embed ──► ship
      ▲                                                                                │
      └────────────────────── repeat until accuracy is good enough ◄──────────────────┘
```

Everything runs locally. Use the Go binary directly, or the training container
(`Dockerfile.train`) if you'd rather not install Go.

## 1. Export glyphs from real scans

Point the recognizer at scanned pages; it segments each into individual
character images, normalised exactly the way the trainer expects, and (using the
current model) prefixes each filename with its best guess to speed up sorting:

```bash
handwriting export-glyphs -image scans/logbook_page1.png -out unlabeled/
# wrote 248 glyph images to unlabeled/
```

`-line` treats the image as a single line; the default is a multi-line page.

## 2. Label them

Sort the PNGs in `unlabeled/` into one sub-folder per character. The folder name
*is* the label (use any filesystem-safe name; e.g. a folder literally called `7`
or `N`):

```
labeled/
  0/   ... .png
  1/   ...
  7/   ...
  A/   ...
  N/   ...
```

Because `export-glyphs` pre-labels filenames with the model's guess, most of the
work is dragging correctly-guessed PNGs into the right folder and fixing the
mistakes. The more hands and pens you include, the better the model generalises.

## 3. Train on your labels

```bash
handwriting train -dir labeled/ -hidden 256 -epochs 40 -out mylogs.gob
# class labels and count are read straight from the folder names
```

Tips:
- Aim for **at least ~50–100 examples per character**; more for ambiguous pairs
  (0/O, 1/I/l, 2/Z, 5/S, 8/B).
- `-val 0.15` holds out 15% to report honest accuracy each epoch.
- Combine your data with a public set (copy EMNIST-derived glyphs into the same
  folders) if you're short on examples for some characters.

### Train/inference parity (`-normalize`)

`train` defaults to `-normalize`, which runs IDX datasets (MNIST/EMNIST) through
the **same** image normalisation the recognizer applies to real scans. This
matters: a model trained on a dataset's *native* framing can score ~80% on that
dataset's test set yet only ~60% on real images, because the glyphs are centred
and scaled differently. Normalising at train time closes that gap (measured
+16 points on EMNIST through the image pipeline). Glyph-folder training (`-dir`)
is already in this frame — `export-glyphs` produces normalised crops — so no
flag is needed there.

## 4. Quantize, embed, ship

```bash
handwriting quantize -in mylogs.gob -out mylogs.q8.gob   # ~8x smaller
make embed-model MODEL=mylogs.q8.gob                     # bake into the binary
make dist                                                # cross-compile to ship
```

The app picks up the model automatically (embedded, or via `HANDWRITING_MODEL`).

## Using the training container

No Go toolchain needed — build once, then run subcommands against a `./data`
volume:

```bash
docker build -f Dockerfile.train -t handwriting-trainer .

docker run --rm -v "$PWD/data:/data" handwriting-trainer \
  export-glyphs -image /data/scans/page1.png -out /data/unlabeled
# ...label /data/unlabeled into /data/labeled/<char>/ ...
docker run --rm -v "$PWD/data:/data" handwriting-trainer \
  train -dir /data/labeled -hidden 256 -epochs 40 -out /data/mylogs.gob
docker run --rm -v "$PWD/data:/data" handwriting-trainer \
  quantize -in /data/mylogs.gob -out /data/mylogs.q8.gob
```

Then `make embed-model MODEL=data/mylogs.q8.gob` on the host.

## Where the per-character model runs out of road

This recognizer classifies **segmented** characters, which works for hand-
*printed* entries. Truly **cursive** writing, where letters join, can't be split
by whitespace and needs a segmentation-free sequence model (CRNN + CTC), or a
pretrained one run via [onnx-go](https://github.com/oramasearch/onnx-go). The
labelling you do here (steps 1–2) is exactly the data such a model would need, so
none of this effort is wasted if you later upgrade the architecture.
