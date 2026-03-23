PYTHON ?= python
PIP ?= $(PYTHON) -m pip
MANIFEST ?= openclawenv.toml
LOCKFILE ?= openclawenv.lock
DOCKERFILE ?= Dockerfile
OPENENV = $(PYTHON) -c "import sys; sys.path.insert(0, 'src'); from openenv.cli import main; raise SystemExit(main(sys.argv[1:]))"

.PHONY: help install install-dev install-docs install-scan install-hooks test coverage coverage-html docs-build docs-serve menu init validate lock scan dockerfile compose build release-tag clean

help:
	@$(PYTHON) -c "from textwrap import dedent; print(dedent('''OpenClawenv Make Targets\n  make install       Install the project in editable mode\n  make install-dev   Install development tooling, including coverage\n  make install-docs  Install MkDocs and mkdocstrings tooling\n  make install-scan  Install optional skill-scanner integration\n  make install-hooks Configure Git to use repo-managed hooks from .githooks\n  make test          Run the unittest suite\n  make coverage      Run tests with terminal coverage report\n  make coverage-html Run tests with terminal and HTML coverage reports\n  make docs-build    Build the project documentation site\n  make docs-serve    Run the local MkDocs preview server\n  make menu          Open the interactive bot menu\n  make init          Create $(MANIFEST)\n  make validate      Validate $(MANIFEST)\n  make lock          Generate $(LOCKFILE)\n  make scan          Run skill-scanner on inline skills\n  make dockerfile    Export $(DOCKERFILE)\n  make compose       Export the bot docker-compose file\n  make build         Build the Docker image and compose file\n  make release-tag   Update release metadata, create a release commit, and tag it\n  make clean         Remove local build/test artifacts\n\nOverrides:\n  MANIFEST=custom.openclawenv.toml\n  LOCKFILE=custom.openclawenv.lock\n  DOCKERFILE=Custom.Dockerfile\n  TAG=openclawenv/custom:dev\n  COMPOSE_FILE=custom-compose.yml\n  SCAN_ARGS=-- --policy strict --fail-on-severity high\n  VERSION=1.0.2\n  TAG_MESSAGE=OpenClawenv 1.0.2'''))"

install:
	$(PIP) install -e .

install-dev:
	$(PIP) install -e .[dev]

install-docs:
	$(PIP) install -e .[docs]

install-scan:
	$(PIP) install -e .[scan]

install-hooks:
	git config core.hooksPath .githooks

test:
	$(PYTHON) -m unittest discover -s tests -t . -v

coverage:
	$(PYTHON) -m coverage run -m unittest discover -s tests -t . -v
	$(PYTHON) -m coverage report -m

coverage-html:
	$(PYTHON) -m coverage run -m unittest discover -s tests -t . -v
	$(PYTHON) -m coverage report -m
	$(PYTHON) -m coverage html

docs-build:
	$(PYTHON) -m mkdocs build --strict

docs-serve:
	$(PYTHON) -m mkdocs serve

menu:
	$(OPENENV)

init:
	$(OPENENV) init --path $(MANIFEST)

validate:
	$(OPENENV) validate --path $(MANIFEST)

lock:
	$(OPENENV) lock --path $(MANIFEST) --output $(LOCKFILE)

scan:
	$(OPENENV) scan --path $(MANIFEST) $(SCAN_ARGS)

dockerfile:
	$(OPENENV) export dockerfile --path $(MANIFEST) --lock $(LOCKFILE) --output $(DOCKERFILE)

compose:
	$(OPENENV) export compose --path $(MANIFEST) --lock $(LOCKFILE) $(if $(COMPOSE_FILE),--output $(COMPOSE_FILE),)

build:
	$(OPENENV) build --path $(MANIFEST) --lock $(LOCKFILE) $(if $(TAG),--tag $(TAG),)

release-tag:
	$(PYTHON) .github/scripts/create_release_tag.py $(VERSION) $(if $(TAG_MESSAGE),--message "$(TAG_MESSAGE)",)

clean:
	$(PYTHON) -c "from pathlib import Path; import shutil; [shutil.rmtree(path, ignore_errors=True) for path in map(Path, ['build', 'dist', '.pytest_cache', 'tests/_tmp', '.openclawenv-scan', 'htmlcov', 'site'])]; [shutil.rmtree(path, ignore_errors=True) for path in Path('.').rglob('__pycache__')]; [shutil.rmtree(path, ignore_errors=True) for path in Path('.').glob('*.egg-info') if path.is_dir()]; [path.unlink() for path in Path('.').glob('*.egg-info') if path.is_file()]; [path.unlink() for path in [Path('.coverage'), Path('coverage.xml')] if path.exists()]; [path.unlink() for path in Path('.').glob('.coverage.*') if path.is_file()]"
