"""Export service: Markdown, BibTeX, CSV."""

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from paperbot.models.paper import Paper

Format = Literal["tex", "md", "csv"]
EXT: dict[str, str] = {"tex": ".bib", "md": ".md", "csv": ".csv"}


def _bib_slug(title: str, paper_id: int) -> str:
    """Generate short slug from title for BibTeX citation key."""
    if not title:
        return f"paper_{paper_id}"
    words = re.sub(r"[^\w\s]", "", title).split()[:3]
    slug = "_".join(w.lower() for w in words if w)[:40]
    return slug or f"paper_{paper_id}"


def _bib_author(authors: str | None) -> str:
    """Format authors for BibTeX: 'A and B and C and others'."""
    if not authors or not authors.strip():
        return "Unknown"
    # Semicolon or comma -> " and "
    parts = re.split(r"[;,]", authors)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return "Unknown"
    if len(parts) > 3:
        return " and ".join(parts[:3]) + " and others"
    return " and ".join(parts)


def _content_tex(papers: list[Paper]) -> str:
    """Generate BibTeX content."""
    lines = []
    for p in papers:
        year = (p.published or "")[:4] or "0000"
        month = (p.published or "-")[5:7] if len(p.published or "") >= 7 else "01"
        day = (p.published or "-")[8:10] if len(p.published or "") >= 10 else "01"
        slug = _bib_slug(p.title or "", p.id or 0)
        key = f"paperbot_{year}_{p.id or 0}_{slug}" if (p.id is not None) else f"paperbot_{year}_{slug}"
        author = _bib_author(p.authors)
        title = (p.title or "").replace("{", "{{").replace("}", "}}")
        journal = (p.journal or "").replace("{", "{{").replace("}", "}}")
        doi = (p.doi or "").strip()
        block = f"""@article{{{key},
  author  = {{{author}}},
  title   = {{{title}}},
  journal = {{{journal}}},
  year    = {{{year}}},
  month   = {{{month}}},
  day     = {{{day}}},
  doi     = {{{doi}}},"""
        if doi:
            block += f"\n  url     = {{https://doi.org/{doi}}}"
        block += "\n}\n"
        lines.append(block)
    return "\n".join(lines)


def _content_md(papers: list[Paper], export_date: str) -> str:
    """Generate Markdown content (PaperBot Export List style)."""
    lines = [f"# PaperBot Export List ({export_date})\n"]
    for p in papers:
        title = p.title or "(No title)"
        lines.append(f"## {title}\n")
        if p.journal:
            lines.append(f"- **Journal**: {p.journal}")
        authors = (p.authors or "").strip()
        if authors:
            # Show first few authors, then et al.
            parts = [x.strip() for x in re.split(r"[;,]", authors) if x.strip()]
            if len(parts) > 3:
                authors_display = ", ".join(parts[:3]) + ", et al."
            else:
                authors_display = ", ".join(parts)
            lines.append(f"- **Authors**: {authors_display}")
        if p.published:
            lines.append(f"- **Published**: {p.published[:10]}")
        if p.doi:
            lines.append(f"- **DOI**: [{p.doi}](https://doi.org/{p.doi})")
        elif p.link:
            lines.append(f"- **Link**: {p.link}")
        lines.append("")
    return "\n".join(lines)


def _content_csv(papers: list[Paper]) -> str:
    """Generate CSV content."""
    import io

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Title", "Journal", "Authors", "Date_Published", "DOI", "Added_Date"])
    for p in papers:
        authors = (p.authors or "").replace(",", "; ").strip()
        if not authors:
            authors = ""
        added = (p.created_at or "")[:10] if p.created_at else ""
        pub = (p.published or "")[:10] if p.published else ""
        w.writerow(
            [
                p.title or "",
                p.journal or "",
                authors,
                pub,
                p.doi or "",
                added,
            ]
        )
    return out.getvalue()


class MarkdownExporter:
    """Service for exporting papers to Markdown, BibTeX, or CSV."""

    def __init__(self, export_dir: Path):
        """Initialize exporter.

        Args:
            export_dir: Base directory for exports (e.g. exports/)
        """
        self.export_dir = export_dir
        self.export_dir.mkdir(exist_ok=True)

    def export(
        self,
        papers: list[Paper],
        subdir: str = "picked",
        format: Format = "md",
    ) -> Path:
        """Export papers to a file.

        Args:
            papers: List of papers to export
            subdir: Subdirectory under export_dir (e.g. "picked", "read")
            format: "tex" (BibTeX .bib), "md", or "csv"

        Returns:
            Path to the created file (exports/{subdir}/yyyy-mm-dd_hhmm.ext)
        """
        now = datetime.now()
        stamp = now.strftime("%Y-%m-%d_%H%M")
        ext = EXT.get(format, ".md")
        target_dir = self.export_dir / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        filepath = target_dir / f"{stamp}{ext}"

        if format == "tex":
            content = _content_tex(papers)
        elif format == "csv":
            content = _content_csv(papers)
        else:
            content = _content_md(papers, now.strftime("%Y-%m-%d"))

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return filepath
