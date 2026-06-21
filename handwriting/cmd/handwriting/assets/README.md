# Embedded model slot

Drop a trained model here named `default.gob` and rebuild, and the binary
becomes fully self-contained — `predict` / `read` work with no `-model` flag and
no separate file to copy onto the USB stick.

    make embed-model MODEL=digits.q8.gob   # copies it here as default.gob, rebuilds

If `default.gob` is absent the binary still builds; `-model` is just required at
run time. This directory is embedded via `//go:embed` (see embed.go).
