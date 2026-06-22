package main

import (
	"bytes"
	"embed"
	"fmt"
	"os"

	"github.com/natehorst240-sketch/ocrdocumentverify/handwriting/model"
)

// assets embeds the optional default model so the binary can be fully
// self-contained — copy one .exe onto a USB stick and it runs with no extra
// files. If cmd/handwriting/assets/default.gob is absent at build time the
// binary still compiles; -model is simply required at run time.
//
//go:embed assets
var assets embed.FS

const embeddedModelPath = "assets/default.gob"

// hasEmbeddedModel reports whether a default model was baked into the binary.
func hasEmbeddedModel() bool {
	_, err := assets.ReadFile(embeddedModelPath)
	return err == nil
}

// resolveModel loads the model to use: the -model file if one was given,
// otherwise the embedded default. This is what lets `predict`/`read` work with
// no flags on a self-contained build.
func resolveModel(flagPath string) (*model.Model, error) {
	if flagPath != "" {
		if _, err := os.Stat(flagPath); err == nil {
			return model.Load(flagPath)
		} else if !hasEmbeddedModel() {
			return nil, fmt.Errorf("model %q not found and no model is embedded in this binary", flagPath)
		}
		// flag given but file missing and we DO have an embedded one: fall through.
	}
	if hasEmbeddedModel() {
		b, err := assets.ReadFile(embeddedModelPath)
		if err != nil {
			return nil, err
		}
		return model.Read(bytes.NewReader(b))
	}
	return nil, fmt.Errorf("no -model given and no model embedded in this binary")
}
