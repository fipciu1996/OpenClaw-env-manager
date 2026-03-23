# CHANGELOG

All notable changes to this project will be documented in this file.

The format is managed with [`changelog-cli`](https://pypi.org/project/changelog-cli/)
and follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) together
with [Semantic Versioning](https://semver.org/spec/v2.0.0.html).



## Unreleased
---

### New

### Changes

### Fixes

### Breaks


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
