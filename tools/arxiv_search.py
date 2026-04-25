#!/usr/bin/env python3
"""Search arXiv and DBLP for fuzzing research papers, with PDF download support.

Usage:
    python tools/arxiv_search.py --query "coverage-guided fuzzing" --max-results 20
    python tools/arxiv_search.py --query "seed scheduling greybox" --source dblp --max-results 10
    python tools/arxiv_search.py download --url "https://arxiv.org/abs/2301.12345" --output-dir phase1-idea/papers/
    python tools/arxiv_search.py download --id "2301.12345" --output-dir phase1-idea/papers/
    python tools/arxiv_search.py download-top --query "seed scheduling fuzzing" --top 5 --output-dir phase1-idea/papers/
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

import requests


@dataclass
class Paper:
    title: str
    authors: list[str]
    abstract: str
    year: str
    venue: str = ""
    url: str = ""
    doi: str = ""
    source: str = ""
    arxiv_id: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "year": self.year,
            "venue": self.venue,
            "url": self.url,
            "doi": self.doi,
            "source": self.source,
            "arxiv_id": self.arxiv_id,
        }


def _extract_arxiv_id(url: str) -> str:
    """Extract arXiv ID from a URL like https://arxiv.org/abs/2301.12345v2."""
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", url)
    if m:
        return m.group(1)
    m = re.search(r"arxiv.org/abs/(.+?)(?:v\d+)?$", url)
    if m:
        return m.group(1)
    return ""


def search_arxiv(query: str, max_results: int = 20, category: str = "cs.CR") -> list[Paper]:
    """Search arXiv API for papers."""
    search_query = f"all:{quote_plus(query)}"
    if category:
        search_query += f"+AND+cat:{category}"

    url = (
        f"http://export.arxiv.org/api/query?"
        f"search_query={search_query}&start=0&max_results={max_results}"
        f"&sortBy=relevance&sortOrder=descending"
    )

    papers: list[Paper] = []
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[arxiv] Request failed: {e}")
        return papers

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.text)

    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else ""

        authors = []
        for author in entry.findall("atom:author", ns):
            name_el = author.find("atom:name", ns)
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        abstract_el = entry.find("atom:summary", ns)
        abstract = abstract_el.text.strip().replace("\n", " ") if abstract_el is not None and abstract_el.text else ""

        published_el = entry.find("atom:published", ns)
        year = published_el.text[:4] if published_el is not None and published_el.text else ""

        link_el = entry.find("atom:id", ns)
        paper_url = link_el.text.strip() if link_el is not None and link_el.text else ""

        arxiv_id = _extract_arxiv_id(paper_url)

        papers.append(Paper(
            title=title,
            authors=authors,
            abstract=abstract,
            year=year,
            url=paper_url,
            source="arxiv",
            arxiv_id=arxiv_id,
        ))

    return papers


def search_dblp(query: str, max_results: int = 20) -> list[Paper]:
    """Search DBLP API for papers."""
    url = f"https://dblp.org/search/publ/api?q={quote_plus(query)}&h={max_results}&format=json"

    papers: list[Paper] = []
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"[dblp] Request failed: {e}")
        return papers

    hits = data.get("result", {}).get("hits", {}).get("hit", [])
    for hit in hits:
        info = hit.get("info", {})

        title = info.get("title", "").rstrip(".")
        year = info.get("year", "")
        venue = info.get("venue", "")
        doi = info.get("doi", "")
        paper_url = info.get("ee", info.get("url", ""))

        authors_data = info.get("authors", {}).get("author", [])
        if isinstance(authors_data, dict):
            authors_data = [authors_data]
        authors = [a.get("text", a) if isinstance(a, dict) else str(a) for a in authors_data]

        papers.append(Paper(
            title=title,
            authors=authors,
            abstract="",
            year=year,
            venue=venue,
            url=paper_url,
            doi=doi,
            source="dblp",
        ))

    return papers


def download_pdf(arxiv_id: str, output_dir: str, filename: str | None = None) -> str | None:
    """Download a paper's PDF from arXiv.

    Returns the path to the downloaded file, or None on failure.
    """
    arxiv_id = arxiv_id.strip()
    if not arxiv_id:
        print("[download] No arXiv ID provided", file=sys.stderr)
        return None

    arxiv_id = _extract_arxiv_id(arxiv_id) or arxiv_id

    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    os.makedirs(output_dir, exist_ok=True)
    if filename is None:
        safe_id = arxiv_id.replace("/", "_").replace(".", "_")
        filename = f"{safe_id}.pdf"
    output_path = os.path.join(output_dir, filename)

    if os.path.exists(output_path):
        print(f"[download] Already exists: {output_path}")
        return output_path

    print(f"[download] Downloading {pdf_url} ...")
    try:
        resp = requests.get(pdf_url, timeout=60, stream=True)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type and "octet-stream" not in content_type:
            print(f"[download] WARNING: Unexpected content-type: {content_type}")

        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_kb = os.path.getsize(output_path) / 1024
        print(f"[download] Saved: {output_path} ({size_kb:.0f} KB)")
        return output_path

    except requests.RequestException as e:
        print(f"[download] Failed to download {pdf_url}: {e}", file=sys.stderr)
        return None


def download_top_papers(
    query: str,
    top_n: int = 5,
    output_dir: str = "phase1-idea/papers",
    category: str = "cs.CR",
) -> list[dict]:
    """Search arXiv and download PDFs for the top N results.

    Returns a list of dicts with paper metadata and local file path.
    """
    papers = search_arxiv(query, max_results=top_n * 2, category=category)

    downloaded = []
    count = 0
    for paper in papers:
        if count >= top_n:
            break
        if not paper.arxiv_id:
            continue

        safe_title = re.sub(r'[^\w\s-]', '', paper.title)[:60].strip().replace(' ', '_')
        filename = f"{paper.arxiv_id.replace('/', '_')}_{safe_title}.pdf"

        path = download_pdf(paper.arxiv_id, output_dir, filename)
        if path:
            downloaded.append({
                **paper.to_dict(),
                "local_path": path,
            })
            count += 1
            time.sleep(1)

    index_path = os.path.join(output_dir, "index.json")
    with open(index_path, "w") as f:
        json.dump(downloaded, f, indent=2, ensure_ascii=False)
    print(f"[download] Index saved: {index_path}")

    return downloaded


def format_papers_md(papers: list[Paper]) -> str:
    """Format papers as Markdown."""
    lines: list[str] = []
    for i, p in enumerate(papers, 1):
        authors_str = ", ".join(p.authors[:3])
        if len(p.authors) > 3:
            authors_str += " et al."
        lines.append(f"### {i}. {p.title}")
        lines.append(f"- **Authors**: {authors_str}")
        lines.append(f"- **Year**: {p.year}")
        if p.venue:
            lines.append(f"- **Venue**: {p.venue}")
        lines.append(f"- **URL**: {p.url}")
        if p.arxiv_id:
            lines.append(f"- **arXiv ID**: {p.arxiv_id}")
        if p.abstract:
            abstract_short = p.abstract[:300]
            if len(p.abstract) > 300:
                abstract_short += "..."
            lines.append(f"- **Abstract**: {abstract_short}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search for fuzzing research papers")
    sub = parser.add_subparsers(dest="command")

    # Default: search mode (backward compatible)
    parser.add_argument("--query", help="Search query")
    parser.add_argument("--source", default="both", choices=["arxiv", "dblp", "both"])
    parser.add_argument("--max-results", type=int, default=20, help="Max results per source")
    parser.add_argument("--category", default="cs.CR", help="arXiv category filter")
    parser.add_argument("--output", help="Save results to file (JSON or MD)")
    parser.add_argument("--format", default="md", choices=["json", "md"])

    # download subcommand: download a single paper
    p_dl = sub.add_parser("download", help="Download a paper PDF from arXiv")
    p_dl.add_argument("--id", dest="arxiv_id", help="arXiv paper ID (e.g., 2301.12345)")
    p_dl.add_argument("--url", help="arXiv paper URL")
    p_dl.add_argument("--output-dir", default="phase1-idea/papers", help="Output directory")
    p_dl.add_argument("--filename", help="Override output filename")

    # download-top subcommand: search + download top N
    p_dt = sub.add_parser("download-top", help="Search and download top N papers")
    p_dt.add_argument("--query", required=True, help="Search query")
    p_dt.add_argument("--top", type=int, default=5, help="Number of papers to download")
    p_dt.add_argument("--output-dir", default="phase1-idea/papers", help="Output directory")
    p_dt.add_argument("--category", default="cs.CR", help="arXiv category filter")

    args = parser.parse_args()

    if args.command == "download":
        aid = args.arxiv_id
        if not aid and args.url:
            aid = _extract_arxiv_id(args.url)
        if not aid:
            parser.error("Provide --id or --url")
        download_pdf(aid, args.output_dir, args.filename)

    elif args.command == "download-top":
        results = download_top_papers(args.query, args.top, args.output_dir, args.category)
        print(f"\n[download-top] Downloaded {len(results)} papers")
        for r in results:
            print(f"  - {r['title'][:80]}  →  {r['local_path']}")

    else:
        if not args.query:
            parser.error("--query is required for search mode")

        all_papers: list[Paper] = []

        if args.source in ("arxiv", "both"):
            print(f"[arxiv] Searching for: {args.query}")
            arxiv_papers = search_arxiv(args.query, args.max_results, args.category)
            all_papers.extend(arxiv_papers)
            print(f"[arxiv] Found {len(arxiv_papers)} papers")
            if args.source == "both":
                time.sleep(1)

        if args.source in ("dblp", "both"):
            print(f"[dblp] Searching for: {args.query}")
            dblp_papers = search_dblp(args.query, args.max_results)
            all_papers.extend(dblp_papers)
            print(f"[dblp] Found {len(dblp_papers)} papers")

        if args.output:
            if args.format == "json":
                with open(args.output, "w") as f:
                    json.dump([p.to_dict() for p in all_papers], f, indent=2)
            else:
                with open(args.output, "w") as f:
                    f.write(f"# Search Results: {args.query}\n\n")
                    f.write(f"Total: {len(all_papers)} papers\n\n")
                    f.write(format_papers_md(all_papers))
            print(f"[search] Saved to {args.output}")
        else:
            print(format_papers_md(all_papers))


if __name__ == "__main__":
    main()
