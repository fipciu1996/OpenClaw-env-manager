"""Build static coverage site assets used by the CI workflow."""

from __future__ import annotations

import json
from pathlib import Path
import shutil


INDEX_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Open-env Coverage</title>
    <style>
      body {
        font-family: Arial, sans-serif;
        margin: 3rem auto;
        max-width: 48rem;
        padding: 0 1rem;
        line-height: 1.6;
      }
      .badge-link {
        font-weight: 700;
      }
    </style>
  </head>
  <body>
    <h1>Open-env Coverage</h1>
    <p>This site publishes the latest GitHub Actions coverage report.</p>
    <ul>
      <li><a class="badge-link" href="./coverage/index.html">Open HTML coverage report</a></li>
      <li><a href="./coverage.svg">Open coverage badge</a></li>
    </ul>
  </body>
</html>
"""

BADGE_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="124" height="20" role="img" aria-label="coverage: {label}">
  <title>coverage: {label}</title>
  <linearGradient id="smooth" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="round">
    <rect width="124" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#round)">
    <rect width="63" height="20" fill="#555"/>
    <rect x="63" width="61" height="20" fill="{color}"/>
    <rect width="124" height="20" fill="url(#smooth)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="32.5" y="15" fill="#010101" fill-opacity=".3">coverage</text>
    <text x="32.5" y="14">coverage</text>
    <text x="92.5" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="92.5" y="14">{label}</text>
  </g>
</svg>
"""


def build_index(site_dir: Path) -> None:
    """Write the landing page for the published coverage site."""
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")


def copy_html_report(source_dir: Path, target_dir: Path) -> None:
    """Copy the generated HTML coverage report into the publish directory."""
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(source_dir, target_dir)


def load_coverage_totals(coverage_json: Path) -> tuple[float, str]:
    """Read the numeric and display coverage values from coverage.json."""
    coverage = json.loads(coverage_json.read_text(encoding="utf-8"))
    totals = coverage["totals"]
    return float(totals["percent_covered"]), str(totals["percent_covered_display"])


def write_summary(total_display: str, output_path: Path) -> None:
    """Create the Markdown summary that is appended to the workflow summary."""
    output_path.write_text(
        "\n".join(
            [
                "## Coverage Summary",
                "",
                f"- Total coverage: **{total_display}%**",
                "- Documentation build is validated in CI.",
                "- The HTML coverage report is published via GitHub Pages on pushes to `main`.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def badge_color(percent: float) -> str:
    """Return a badge color based on the current coverage percentage."""
    if percent >= 90:
        return "#4c1"
    if percent >= 80:
        return "#97ca00"
    if percent >= 70:
        return "#a4a61d"
    if percent >= 60:
        return "#dfb317"
    if percent >= 50:
        return "#fe7d37"
    return "#e05d44"


def write_badge(total_percent: float, total_display: str, output_path: Path) -> None:
    """Create a static SVG badge without relying on external badge tooling."""
    output_path.write_text(
        BADGE_TEMPLATE.format(label=f"{total_display}%", color=badge_color(total_percent)),
        encoding="utf-8",
    )


def main() -> None:
    """Create the static coverage site layout expected by the CI workflow."""
    site_dir = Path("site")
    coverage_dir = site_dir / "coverage"
    total_percent, total_display = load_coverage_totals(Path("coverage.json"))

    build_index(site_dir)
    copy_html_report(Path("htmlcov"), coverage_dir)
    write_summary(total_display, Path(".coverage-summary.md"))
    write_badge(total_percent, total_display, site_dir / "coverage.svg")


if __name__ == "__main__":
    main()
