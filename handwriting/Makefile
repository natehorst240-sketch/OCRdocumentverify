# Build the standalone handwriting recognizer.
#
# Everything here produces a single static, dependency-free executable — no
# Python, no Ollama/LLM, no shared libraries. CGO is disabled so the binaries
# are fully static and cross-compile from any one machine.

BIN     := handwriting
PKG     := ./cmd/handwriting
DIST    := dist
VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
LDFLAGS := -s -w   # strip symbol table + DWARF -> smaller binary
GOFLAGS := -trimpath
export CGO_ENABLED = 0

.PHONY: all build test clean dist embed-model usb model-mnist model-emnist docker-train

## build: compile for the host OS/arch
build:
	go build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(BIN) $(PKG)

## test: run the unit tests
test:
	go test ./...

## embed-model: bake a trained model into the binary (MODEL=path required)
##   make embed-model MODEL=digits.q8.gob
embed-model:
	@test -n "$(MODEL)" || (echo "usage: make embed-model MODEL=<file.gob>"; exit 1)
	cp "$(MODEL)" cmd/handwriting/assets/default.gob
	$(MAKE) build
	@echo "embedded $(MODEL) -> self-contained ./$(BIN)"

MNIST_URL := https://storage.googleapis.com/cvdf-datasets/mnist

## model-mnist: download MNIST, train a digit model, quantize, and embed it.
## Reproduces the shipped cmd/handwriting/assets/default.gob (~98% test acc).
model-mnist: build
	@mkdir -p .data
	@for f in train-images-idx3-ubyte train-labels-idx1-ubyte t10k-images-idx3-ubyte t10k-labels-idx1-ubyte; do \
		test -f .data/$$f.gz || curl -fsSL -o .data/$$f.gz "$(MNIST_URL)/$$f.gz"; done
	./$(BIN) train -images .data/train-images-idx3-ubyte.gz -labels .data/train-labels-idx1-ubyte.gz \
		-alphabet digits -epochs 15 -hidden 128 -out .data/mnist.gob
	./$(BIN) eval -model .data/mnist.gob -images .data/t10k-images-idx3-ubyte.gz -labels .data/t10k-labels-idx1-ubyte.gz
	./$(BIN) quantize -in .data/mnist.gob -out .data/mnist.q8.gob
	$(MAKE) embed-model MODEL=.data/mnist.q8.gob

EMNIST_URL := https://biometrics.nist.gov/cs_links/EMNIST/gzip.zip

## model-emnist: download EMNIST, train an alphanumeric model (47 classes:
## digits + letters), quantize, and embed it. Bigger/slower than MNIST.
model-emnist: build
	@mkdir -p .data/emnist
	@test -f .data/emnist.zip || curl -fsSL -o .data/emnist.zip "$(EMNIST_URL)"
	@cd .data/emnist && unzip -o -j ../emnist.zip \
		"gzip/emnist-balanced-train-images-idx3-ubyte.gz" \
		"gzip/emnist-balanced-train-labels-idx1-ubyte.gz" \
		"gzip/emnist-balanced-test-images-idx3-ubyte.gz" \
		"gzip/emnist-balanced-test-labels-idx1-ubyte.gz" \
		"gzip/emnist-balanced-mapping.txt" >/dev/null
	./$(BIN) train \
		-images .data/emnist/emnist-balanced-train-images-idx3-ubyte.gz \
		-labels .data/emnist/emnist-balanced-train-labels-idx1-ubyte.gz \
		-mapping .data/emnist/emnist-balanced-mapping.txt \
		-hidden 256 -epochs 20 -out .data/emnist.gob
	./$(BIN) eval -model .data/emnist.gob -transpose \
		-images .data/emnist/emnist-balanced-test-images-idx3-ubyte.gz \
		-labels .data/emnist/emnist-balanced-test-labels-idx1-ubyte.gz
	./$(BIN) quantize -in .data/emnist.gob -out .data/emnist.q8.gob
	$(MAKE) embed-model MODEL=.data/emnist.q8.gob

## docker-train: build the training container (no Go toolchain needed to use it)
docker-train:
	docker build -f Dockerfile.train -t handwriting-trainer .

# Cross-compile matrix: GOOS/GOARCH pairs to ship.
PLATFORMS := \
	windows/amd64 \
	windows/arm64 \
	darwin/amd64 \
	darwin/arm64 \
	linux/amd64 \
	linux/arm64

## dist: cross-compile every platform into ./dist (run embed-model first for a
## truly standalone, model-included build)
dist: clean
	@mkdir -p $(DIST)
	@for p in $(PLATFORMS); do \
		os=$${p%/*}; arch=$${p#*/}; \
		ext=""; [ "$$os" = "windows" ] && ext=".exe"; \
		out="$(DIST)/$(BIN)-$(VERSION)-$$os-$$arch$$ext"; \
		echo "  $$os/$$arch -> $$out"; \
		GOOS=$$os GOARCH=$$arch go build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o "$$out" $(PKG) || exit 1; \
	done
	@echo "done. binaries in ./$(DIST)"

## usb: build a ready-to-copy folder for a USB stick (Windows + a README)
usb: dist
	@mkdir -p $(DIST)/usb
	@cp $(DIST)/$(BIN)-$(VERSION)-windows-amd64.exe $(DIST)/usb/$(BIN).exe
	@cp USB_README.txt $(DIST)/usb/README.txt 2>/dev/null || true
	@echo "USB folder ready: $(DIST)/usb (copy this whole folder to the stick)"

## clean: remove build artifacts
clean:
	rm -rf $(DIST) $(BIN)
