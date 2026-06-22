# Building a Windows installer (setup.exe)

This packages the **whole app** — the Streamlit UI (including the *Read
Handwritten Log* page), the Go handwriting OCR engine, and a private Python
runtime — into a single `setup.exe`. The person you send it to just
double-clicks it; there's no Python, no Docker, no admin rights, and nothing
else to install.

## What the end user gets

- A normal Windows install (Start-Menu entry, optional desktop shortcut,
  Add/Remove Programs uninstaller).
- Installs per-user into a writable folder, so the app can store its database,
  uploads, and output beside itself without admin rights.
- Launching it opens the app in **its own window** (Edge/Chrome "app mode" —
  no tabs or address bar), served locally at `http://localhost:8501` in no-LLM
  mode with the Go handwriting engine enabled. Closing the app window quits.
  (A small console window runs the server in the background; you can minimize
  it — it closes automatically when you quit the app.)

## Easiest: build it in the cloud (no Windows machine needed)

A GitHub Action builds the installer on a Windows runner for you:

1. Push this branch to GitHub.
2. Open the repo's **Actions** tab → **Build Windows installer** → **Run
   workflow**.
3. When it finishes (~5–10 min), download the **AviationRecordsProcessor-Setup**
   artifact from the run's summary page — that's your `setup.exe`.

Tagging a release also triggers it and attaches the installer to the GitHub
release:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

The workflow (`.github/workflows/windows-installer.yml`) sets up Go, installs
Inno Setup, builds the Python runtime + engine, and runs the same
`build_installer.bat` you'd run locally.

## Build it once (on a Windows machine with internet)

You need two tools on the **build** machine (not the end user's):

1. **Inno Setup 6** — https://jrsoftware.org/isdl.php (gives you `ISCC.exe`).
2. **Go** (optional) — https://go.dev/dl/, only to compile `handwriting.exe`
   here. If you don't have Go, build the engine elsewhere
   (`cd handwriting && make dist`) and copy the resulting
   `handwriting-*-windows-amd64.exe` to the repo root as `handwriting.exe`.

Then, from the repo root:

```bat
build_installer.bat
```

That script:

1. builds the private Python runtime via `build_portable.bat` (embeddable
   Python + the lite dependencies) if `runtime\` isn't already there,
2. builds the Go engine to `handwriting.exe` (or uses an existing one),
3. runs Inno Setup on `installer\aviation_app.iss`.

The finished installer lands in **`dist_installer\AviationRecordsProcessor-Setup-<version>.exe`**.
Share that file.

## Doing the steps manually

```bat
build_portable.bat                                   :: 1) runtime\  (Python + deps)
go build -ldflags "-s -w" -o handwriting.exe .\handwriting\cmd\handwriting   :: 2) engine
ISCC.exe installer\aviation_app.iss                  :: 3) setup.exe
```

## Notes & options

- **Which Python deps?** `build_portable.bat` uses `requirements-lite.txt` by
  default — small and reliable, and all that's needed because handwriting OCR is
  handled by the Go engine, not PaddleOCR. Run `build_portable.bat full` if you
  also want the heavy PaddleOCR stack for printed-text scans.
- **Handwriting model.** `handwriting.exe` has a trained model embedded, so it
  reads out of the box. To ship a model trained on *your* logs, embed it first
  (`cd handwriting && make embed-model MODEL=yourmodel.q8.gob`) before building
  the installer. See `handwriting/TRAINING.md`.
- **Version / name.** Edit the `#define` lines at the top of
  `installer\aviation_app.iss` (`AppVersion`, `AppName`). Keep `AppId` stable so
  upgrades replace the previous install instead of installing side-by-side.
- **Code signing.** Unsigned installers trigger SmartScreen ("Unknown
  publisher"). For wide distribution, sign `setup.exe` with an Authenticode
  certificate (Inno Setup supports a `SignTool` directive).
- **User data on uninstall.** The uninstaller leaves `records.db`, `uploads\`,
  and `output\` in place so reinstalling doesn't wipe a user's records; it
  removes the bundled runtime and program files. Delete the install folder by
  hand to remove everything.

## When to use this vs. the portable bundle

- **`setup.exe` (this):** a familiar install with shortcuts and an uninstaller —
  best for handing to a non-technical recipient.
- **Portable bundle (`build_portable.bat` + zip):** no install at all; runs from
  a folder or USB stick. Best for locked-down machines. Same app either way.
