"""MkDocs hooks for repository-local documentation behavior."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin

from mkdocs.config.defaults import MkDocsConfig
from shadcn.plugins.mixins.markdown import MarkdownMixin


def on_config(config: MkDocsConfig) -> MkDocsConfig:
    """Disable shadcn git timestamp integration for reproducible local builds.

    The theme's built-in search plugin attempts to inspect Git commit history for
    every page. In sandboxed, containerized, or dubious-ownership checkouts this
    can fail even when the documentation itself is otherwise valid. Clearing the
    cached repository object keeps the theme usable without requiring global Git
    safe-directory changes on every machine.
    """

    config["git_repository"] = None
    _patch_shadcn_markdown_mixin()
    return config


def on_page_context(context, page, config, nav):  # type: ignore[no-untyped-def]
    """Normalize theme-provided markdown URLs after plugin processing."""

    raw_markdown_url = context.get("raw_markdown_url")
    if isinstance(raw_markdown_url, str):
        context["raw_markdown_url"] = raw_markdown_url.replace("\\", "/")
    return context


def _patch_shadcn_markdown_mixin() -> None:
    """Normalize shadcn markdown URLs and copy targets to POSIX-style paths.

    `mkdocs-shadcn` currently uses `os.path.join` when constructing markdown
    URLs exposed to templates. On Windows that leaks backslashes into document
    paths, which `mkdocs --strict` now warns about. This small monkey patch
    keeps the theme in place while making the generated documentation portable.
    """

    def on_page_context(self, context, page, config, nav):  # type: ignore[no-untyped-def]
        src_uri = page.file.src_uri.replace("\\", "/")
        self.raw_markdown[page.file.abs_src_path] = str(Path(config.site_dir) / Path(src_uri))
        context.update({"raw_markdown_url": urljoin(config.site_url or "/", src_uri)})
        return super(MarkdownMixin, self).on_page_context(context, page, config, nav)

    MarkdownMixin.on_page_context = on_page_context
