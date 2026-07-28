#!/usr/bin/env python3
from pathlib import Path
import sqlite3, hashlib, csv, re
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "papers.db"
CSV_PATH = ROOT / "papers.csv"

from importlib.util import find_spec

if find_spec("pypdf") is not None:
    from pypdf import PdfReader
else:
    PdfReader = None


def clean_title(file_name: str) -> str:
    stem = Path(file_name).stem
    stem = re.sub(r"[_-]+", " ", stem)
    return re.sub(r"\s+", " ", stem).strip()


def gather_pdfs(root: Path):
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")


def extract_metadata(pdf_path: Path):
    pages = None
    title = None
    authors = None
    if PdfReader is not None:
        try:
            reader = PdfReader(str(pdf_path))
            pages = len(reader.pages)
            md = reader.metadata or {}
            title = (md.get("/Title") or md.get("Title") or "").strip() or None
            authors = (md.get("/Author") or md.get("Author") or "").strip() or None
        except Exception:
            pass
    if not title:
        title = clean_title(pdf_path.name)
    return title, authors, pages


def build_database(root: Path):
    pdfs = gather_pdfs(root)
    now = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS papers")
    cur.execute(
        """
        CREATE TABLE papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            file_name TEXT NOT NULL,
            title TEXT,
            authors TEXT,
            pages INTEGER,
            file_size_bytes INTEGER,
            sha256 TEXT,
            extracted_at_utc TEXT NOT NULL
        )
        """
    )

    for pdf in pdfs:
        rel = str(pdf.relative_to(root))
        content = pdf.read_bytes()
        sha = hashlib.sha256(content).hexdigest()
        size = pdf.stat().st_size
        title, authors, pages = extract_metadata(pdf)
        cur.execute(
            """
            INSERT OR REPLACE INTO papers
            (file_path, file_name, title, authors, pages, file_size_bytes, sha256, extracted_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (rel, pdf.name, title, authors, pages, size, sha, now),
        )

    conn.commit()

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id",
            "file_path",
            "file_name",
            "title",
            "authors",
            "pages",
            "file_size_bytes",
            "sha256",
            "extracted_at_utc",
        ])
        for row in cur.execute(
            """
            SELECT id, file_path, file_name, title, authors, pages, file_size_bytes, sha256, extracted_at_utc
            FROM papers
            ORDER BY file_path
            """
        ):
            writer.writerow(row)

    conn.close()
    return len(pdfs)


if __name__ == "__main__":
    count = build_database(ROOT)
    print(f"Indexed {count} PDF papers into {DB_PATH.name} and {CSV_PATH.name}")
