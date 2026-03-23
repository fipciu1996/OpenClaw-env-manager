# CHANGELOG

All notable changes to this project will be documented in this file.

The format is managed with [`changelog-cli`](https://pypi.org/project/changelog-cli/)
and follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) together
with [Semantic Versioning](https://semver.org/spec/v2.0.0.html).



## Unreleased
---

### New
* Added regression tests for the GitHub Pages deploy helper so authentication URL building and token redaction are covered locally.

### Changes
* Updated the GitHub Pages deploy workflow to pass explicit GitHub repository metadata and token environment variables into the deploy step.

### Fixes
* Hardened the GitHub Pages deploy helper to prefer direct `GITHUB_TOKEN` authentication, redact git failure output, and push the generated site with `HEAD:<branch>` semantics that are more reliable for artifact-only branches.

### Breaks


## 1.2.0 - (2026-03-23)
---

### New
* Added dedicated security documentation covering the secure-by-default baseline, default skills and tools, advisory behavior, and OWASP-aligned operator guidance.

### Changes
* Hardened generated manifests and Compose artifacts with stronger secure-by-default settings while preserving explicit operator choices through non-blocking security advisories.
* Switched the MkDocs site to the `mkdocs-shadcn` theme and added a repository-local documentation hook so builds do not require global Git `safe.directory` changes.


## 1.1.2 - (2026-03-23)
---

### Changes
* GitHub Actions now publishes the MkDocs documentation site to GitHub Pages, while keeping the generated coverage report under `/coverage/` on the same deployed site.
* Replaced the deprecated Node 20 GitHub Pages actions with a repository-managed deploy script that publishes the generated site to the `gh-pages` branch.
* Renamed the generated manifest and lockfile defaults from `openenv.*` to `openclawenv.*` while keeping compatibility with existing bot directories and legacy file names.
* Updated generated Dockerfiles for `alpine/openclaw:main` to install packages as `root` and restore the `node` runtime user afterwards, so package installation succeeds without breaking the default OpenClaw gateway runtime.
* Added tracked `openclawenv` documentation and fixture files used by MkDocs navigation and the CLI/manifests test suite.


## 1.1.1 - (2026-03-23)
---

### Changes
* Updated repository URLs, badges, docs branding, and release metadata defaults to use the renamed GitHub repository OpenClaw-env-manager.


## 1.1.0 - (2026-03-23)
---

### Changes
* Renamed the installed console entrypoint to `clawopenenv` and added
  `python -m clawopenenv` as the matching module execution path.
* Renamed the PyPI distribution package to OpenClaw-env-manager while keeping the internal Python package and CLI command as openenv.
* Upgraded GitHub artifact actions to Node 24 compatible versions and opted CI workflows into Node 24 execution early with FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true.


## 1.0.3 - (2026-03-23)
---

### Changes
* The release tag helper now configures Git safe.directory automatically, so local release tagging works in protected repositories.


## 1.0.2 - (2026-03-22)

### Changes
* Added a repository-managed pre-push hook that blocks pushing release tags when the package version does not match the tag.
* The PyPI publish workflow now accepts both numeric tags like 1.0.2 and v-prefixed tags like v1.0.2.


## 1.0.1 - (2026-03-22)

### Changes

* Patch release.

## 0.1.0 - (2026-03-22)

### New

* Initial `Open-env` release with declarative `openenv.toml` manifests and
  deterministic `openenv.lock` generation for OpenClaw agent environments.
* CLI workflows for `init`, `validate`, `lock`, `export dockerfile`,
  `export compose`, `build`, and local skill scanning.
* Generated Docker and OpenClaw Compose artifacts with support for Python,
  Node.js, Chromium, `agent-browser`, `freeride`, and build-time skill scanning
  with `cisco-ai-skill-scanner`.
* Interactive multilingual bot management for listing, creating, editing,
  deleting, exporting, and inspecting bots and their running containers.
* Bot-specific secret handling through sidecar `.env` files and markdown-based
  agent document management with file references stored in manifests.
* OpenRouter-powered markdown improvement flow with batched processing to reduce
  token cost and normalize generated bot documents to English.
* Snapshot support for running bots that inspects installed skills in
  containers and merges discovered changes back into bot manifests.
* CI, coverage reporting, MkDocs plus `mkdocstrings` documentation, GitLab
  Pages publishing, and a tag-only GitHub Actions workflow for publishing the
  package to PyPI.
