# project_overview/canonical_schema.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpectedTable:
    name: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class ExpectedSchema:
    tables: tuple[ExpectedTable, ...]


CANONICAL_SCHEMA_SQL = r"""
PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- Schema guard (v1 only; no migrations)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- The Project Creator must:
-- 1) INSERT schema_version='v1' and schema_hash=<hash> on first creation
-- 2) On open, verify schema_version == 'v1' AND table/column expectations match
--    (hard fail with diagnostic diff if mismatch)

-- -----------------------------------------------------------------------------
-- Papers: one row per paper in the project library
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS papers (
  paper_id TEXT PRIMARY KEY,                 -- e.g., P000012
  source TEXT NOT NULL CHECK (source IN ('pmc','biorxiv')),
  title TEXT NOT NULL,
  authors_json TEXT NOT NULL,                -- JSON array of author strings
  year INTEGER,                              -- nullable
  venue TEXT,                                -- journal / bioRxiv category
  doi TEXT,                                  -- nullable
  pmcid TEXT,                                -- nullable (PMC only)
  landing_url TEXT,                          -- nullable
  pdf_url TEXT,                              -- nullable
  pdf_path TEXT,                             -- local path relative or absolute (choose one convention)
  sha256 TEXT,                               -- file hash for dedup
  status TEXT NOT NULL CHECK (status IN ('found','downloaded','ingested','indexed','error')),
  status_detail TEXT,                        -- error message / warnings
  added_at TEXT NOT NULL,                    -- ISO-8601
  updated_at TEXT NOT NULL                   -- ISO-8601
);

CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status);
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_papers_pmcid ON papers(pmcid);
CREATE INDEX IF NOT EXISTS idx_papers_sha256 ON papers(sha256);

-- -----------------------------------------------------------------------------
-- Ingested document representation (optional but helpful):
-- Stores per-paper ingest artifact metadata (paths, page counts, etc.)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingests (
  paper_id TEXT PRIMARY KEY,
  ingested_json_path TEXT NOT NULL,          -- e.g., ingested/P000012.json
  pages INTEGER NOT NULL,
  sections_json TEXT NOT NULL,               -- JSON array of discovered section names
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE
);

-- -----------------------------------------------------------------------------
-- Chunks: canonical citeable / retrievable spans.
-- Each chunk maps to a specific page and char span (within that page text).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id TEXT PRIMARY KEY,                 -- e.g., CP000012_07_03
  paper_id TEXT NOT NULL,
  page_num INTEGER NOT NULL,                 -- 1-based page number
  section TEXT,                              -- best-effort label
  text TEXT NOT NULL,
  start_char INTEGER NOT NULL,               -- inclusive char offset in page text
  end_char INTEGER NOT NULL,                 -- exclusive char offset in page text
  embedding_ref TEXT,                        -- optional pointer/key to embedding store
  created_at TEXT NOT NULL,
  FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_paper_page ON chunks(paper_id, page_num);
CREATE INDEX IF NOT EXISTS idx_chunks_section ON chunks(section);

-- -----------------------------------------------------------------------------
-- Citations: individual citeable excerpts selected from chunks (or other spans).
-- NOTE: ref_number is intentionally NOT stored here because Vancouver numbering
-- is document-specific (depends on order of first appearance in a draft).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS citations (
  cite_id TEXT PRIMARY KEY,                  -- e.g., Z000041
  paper_id TEXT NOT NULL,
  chunk_id TEXT,                             -- nullable; excerpt may come from page span not in a chunk
  page_num INTEGER NOT NULL,
  section TEXT,
  excerpt TEXT NOT NULL,                     -- exact snippet shown to user
  start_char INTEGER NOT NULL,               -- inclusive
  end_char INTEGER NOT NULL,                 -- exclusive
  excerpt_sha256 TEXT NOT NULL,              -- hash for exact-match validation
  created_at TEXT NOT NULL,
  FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE,
  FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_citations_paper_page ON citations(paper_id, page_num);
CREATE INDEX IF NOT EXISTS idx_citations_chunk ON citations(chunk_id);
CREATE INDEX IF NOT EXISTS idx_citations_excerpt_hash ON citations(excerpt_sha256);

-- -----------------------------------------------------------------------------
-- Drafts: stored markdown + doc_type. Vancouver numbering is stored per draft.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS drafts (
  draft_id TEXT PRIMARY KEY,                 -- e.g., D000003
  title TEXT NOT NULL,
  doc_type TEXT NOT NULL,                    -- e.g., 'review', 'intro', 'methods'
  content_md TEXT NOT NULL,                  -- markdown containing inline [n]
  citation_style TEXT NOT NULL CHECK (citation_style IN ('vancouver')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_drafts_doc_type ON drafts(doc_type);

-- -----------------------------------------------------------------------------
-- Draft ↔ citations map: stores how a draft's [n] references map to cite objects.
-- This is what makes Vancouver numbering reproducible.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS draft_citation_map (
  draft_id TEXT NOT NULL,
  ref_number INTEGER NOT NULL,               -- the [n] in the draft
  cite_id TEXT NOT NULL,
  PRIMARY KEY (draft_id, ref_number),
  FOREIGN KEY (draft_id) REFERENCES drafts(draft_id) ON DELETE CASCADE,
  FOREIGN KEY (cite_id) REFERENCES citations(cite_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_dcm_cite_id ON draft_citation_map(cite_id);

-- -----------------------------------------------------------------------------
-- Retrieval index metadata (so GUI can display status and tool can validate)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS indexes (
  index_id TEXT PRIMARY KEY,                 -- e.g., I000001
  kind TEXT NOT NULL CHECK (kind IN ('bm25','vector')),
  path TEXT NOT NULL,                        -- e.g., indexes/bm25/
  params_json TEXT NOT NULL,                 -- JSON blob of chunking + model params
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_indexes_kind ON indexes(kind);
"""


EXPECTED_SCHEMA = ExpectedSchema(tables=(
    ExpectedTable("schema_meta", ("key", "value")),
    ExpectedTable("papers", (
        "paper_id",
        "source",
        "title",
        "authors_json",
        "year",
        "venue",
        "doi",
        "pmcid",
        "landing_url",
        "pdf_url",
        "pdf_path",
        "sha256",
        "status",
        "status_detail",
        "added_at",
        "updated_at",
    )),
    ExpectedTable("ingests", (
        "paper_id",
        "ingested_json_path",
        "pages",
        "sections_json",
        "created_at",
        "updated_at",
    )),
    ExpectedTable("chunks", (
        "chunk_id",
        "paper_id",
        "page_num",
        "section",
        "text",
        "start_char",
        "end_char",
        "embedding_ref",
        "created_at",
    )),
    ExpectedTable("citations", (
        "cite_id",
        "paper_id",
        "chunk_id",
        "page_num",
        "section",
        "excerpt",
        "start_char",
        "end_char",
        "excerpt_sha256",
        "created_at",
    )),
    ExpectedTable("drafts", (
        "draft_id",
        "title",
        "doc_type",
        "content_md",
        "citation_style",
        "created_at",
        "updated_at",
    )),
    ExpectedTable("draft_citation_map", (
        "draft_id",
        "ref_number",
        "cite_id",
    )),
    ExpectedTable("indexes", (
        "index_id",
        "kind",
        "path",
        "params_json",
        "created_at",
        "updated_at",
    )),
))
