# Getting Started

## Install Development Dependencies

OpenClaw-env-manager itself requires Python `3.12+`. For documentation work, install the
extra docs dependencies:

```bash
python -m pip install -e .[docs]
```

If you also want tests and coverage locally:

```bash
python -m pip install -e .[dev,docs]
```

## Build The Documentation

Run a strict docs build:

```bash
python -m mkdocs build --strict
```

The generated site is written to `site/`.

## Run The Local Preview Server

```bash
python -m mkdocs serve
```

MkDocs starts a local preview server and rebuilds on file changes.

## Use The Makefile Shortcuts

```bash
make install-docs
make docs-build
make docs-serve
```

## What The Docs Include

- project overview and workflow notes
- operational concepts such as manifests, lockfiles, and generated artifacts
- API pages generated directly from the Python source tree with `mkdocstrings`

## CI Integration

GitHub Actions builds and publishes the documentation site in CI together with
coverage. On pushes to `main`, the published GitHub Pages site serves:

- the MkDocs site at the repository root
- the HTML coverage report under `/coverage/`
