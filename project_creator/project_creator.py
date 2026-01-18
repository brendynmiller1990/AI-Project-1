from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import hashlib
import json
import re
import shutil
import sqlite3
import traceback
import uuid


# ----------------------------
# Exceptions (GUI-friendly)
# ----------------------------

class ProjectCreatorError(Exception):
    def __init__(self, message: str, diagnostic: str | None = None):
        super().__init__(message)
        self.message = message
        self.diagnostic = diagnostic or ""


class InvalidProjectNameError(ProjectCreatorError): ...
class InvalidConfigError(ProjectCreatorError): ...
class DuplicateProjectNameError(ProjectCreatorError): ...
class DuplicateProjectIdError(ProjectCreatorError): ...
class ProjectOpenError(ProjectCreatorError): ...
class FilesystemError(ProjectCreatorError): ...


class DatabaseSchemaMismatchError(ProjectCreatorError):
    def __init__(self, message: str, diff: str):
        super().__init__(message, diagnostic=diff)
        self.diff = diff


# ----------------------------
# Schema contracts (imported)
# ----------------------------

@dataclass(frozen=True)
class ExpectedTable:
    name: str
    columns: tuple[str, ...]  # column names only (v1)


@dataclass(frozen=True)
class ExpectedSchema:
    tables: tuple[ExpectedTable, ...]


# ----------------------------
# Dataclasses (API)
# ----------------------------

@dataclass(frozen=True)
class ProjectConfig:
    project_name: str
    topic_prompt: str
    base_projects_dir: Path
    citation_style: str = "vancouver"
    sources: tuple[str, ...] = ("pmc", "biorxiv")
    notes: str | None = None


@dataclass(frozen=True)
class ProjectInfo:
    project_id: str
    project_dir: Path
    manifest_path: Path
    database_path: Path
    status: str  # "created" | "opened"


@dataclass(frozen=True)
class ProjectSummary:
    project_id: str
    project_name: str
    project_dir: Path
    created_at: str
    topic_prompt: str
    valid: bool
    error: str | None = None


# ----------------------------
# Constants / validation
# ----------------------------

_ALLOWED_SOURCES = {"pmc", "biorxiv"}
_NAME_RE = re.compile(r"^[a-z0-9_]+$")


def _utc_now_iso() -> str:
    # ISO-8601 with Z suffix, no microseconds for stable logs/manifests
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _date_yyyy_mm_dd_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _validate_config(cfg: ProjectConfig) -> None:
    if not cfg.project_name or not _NAME_RE.match(cfg.project_name):
        raise InvalidProjectNameError(
            "Invalid project_name. Use lowercase snake_case: a-z, 0-9, underscore.",
            diagnostic=f"project_name={cfg.project_name!r}",
        )
    if cfg.project_name != cfg.project_name.lower():
        raise InvalidProjectNameError("project_name must be lowercase.", diagnostic=cfg.project_name)

    if not cfg.topic_prompt.strip():
        raise InvalidConfigError("topic_prompt must be non-empty.")

    if cfg.citation_style != "vancouver":
        raise InvalidConfigError("citation_style must be 'vancouver' in v1.", diagnostic=cfg.citation_style)

    bad = [s for s in cfg.sources if s not in _ALLOWED_SOURCES]
    if bad:
        raise InvalidConfigError(
            f"Invalid sources in v1: {bad}. Allowed: {sorted(_ALLOWED_SOURCES)}",
            diagnostic="sources=" + ",".join(cfg.sources),
        )


# ----------------------------
# Logging (plain text)
# ----------------------------

def _write_text_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


def _log(log_path: Path, level: str, event: str, msg: str = "") -> None:
    ts = _utc_now_iso()
    tail = f" {msg}" if msg else ""
    _write_text_line(log_path, f"{ts} [{level}] {event}{tail}")


# ----------------------------
# Manifest (v1 strict)
# ----------------------------

def _manifest_dict(cfg: ProjectConfig, project_id: str, created_at: str) -> dict:
    d: dict = {
        "project_id": project_id,
        "project_name": cfg.project_name,
        "topic_prompt": cfg.topic_prompt,
        "created_at": created_at,
        "sources": list(cfg.sources),
        "citation_style": cfg.citation_style,
        "status": "active",
        "version": "v1",
    }
    if cfg.notes:
        d["notes"] = cfg.notes
    return d


def _read_manifest(manifest_path: Path) -> dict:
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ProjectOpenError("manifest.json not found.", diagnostic=str(e))
    except Exception as e:
        raise ProjectOpenError("manifest.json is corrupt or unreadable.", diagnostic=str(e))


def _validate_manifest_v1(m: dict, expected_project_dir: Path) -> None:
    required = [
        "project_id", "project_name", "topic_prompt", "created_at",
        "sources", "citation_style", "status", "version",
    ]
    missing = [k for k in required if k not in m]
    if missing:
        raise ProjectOpenError("manifest.json missing required fields.", diagnostic="missing=" + ",".join(missing))

    if m.get("version") != "v1":
        raise ProjectOpenError("Unsupported manifest version. Expected v1.", diagnostic=f"version={m.get('version')!r}")

    if m.get("project_id") != expected_project_dir.name:
        raise ProjectOpenError(
            "Manifest project_id does not match folder name.",
            diagnostic=f"manifest={m.get('project_id')!r} folder={expected_project_dir.name!r}",
        )


# ----------------------------
# SQLite schema guard (schema_meta)
# ----------------------------

def compute_schema_hash(canonical_schema_sql: str) -> str:
    normalized = canonical_schema_sql.strip().replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def apply_canonical_schema(conn: sqlite3.Connection, schema_sql: str) -> None:
    conn.executescript(schema_sql)
    conn.commit()


def upsert_schema_meta(conn: sqlite3.Connection, *, schema_version: str, schema_hash: str) -> None:
    # Insert only on first creation; do not overwrite in v1
    conn.execute("INSERT OR IGNORE INTO schema_meta(key,value) VALUES (?,?);", ("schema_version", schema_version))
    conn.execute("INSERT OR IGNORE INTO schema_meta(key,value) VALUES (?,?);", ("schema_hash", schema_hash))
    conn.commit()


def verify_schema_meta(conn: sqlite3.Connection, *, expected_version: str, expected_hash: str) -> None:
    cur = conn.cursor()
    cur.execute("SELECT value FROM schema_meta WHERE key='schema_version';")
    row_v = cur.fetchone()
    cur.execute("SELECT value FROM schema_meta WHERE key='schema_hash';")
    row_h = cur.fetchone()

    if not row_v:
        raise DatabaseSchemaMismatchError("schema_meta missing schema_version.", diff="schema_meta.schema_version missing")
    if row_v[0] != expected_version:
        raise DatabaseSchemaMismatchError(
            "Unsupported schema_version in library.db.",
            diff=f"expected schema_version={expected_version!r} got {row_v[0]!r}",
        )

    if not row_h:
        raise DatabaseSchemaMismatchError("schema_meta missing schema_hash.", diff="schema_meta.schema_hash missing")
    if row_h[0] != expected_hash:
        raise DatabaseSchemaMismatchError(
            "schema_hash mismatch.",
            diff=f"expected schema_hash={expected_hash} got {row_h[0]}",
        )


# ----------------------------
# Schema validation (tables + columns; v1)
# ----------------------------

def _introspect_schema(conn: sqlite3.Connection) -> dict[str, list[str]]:
    cur = conn.cursor()
    cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name;
    """)
    tables = [r[0] for r in cur.fetchall()]
    out: dict[str, list[str]] = {}
    for t in tables:
        cur.execute(f"PRAGMA table_info({t});")
        cols = [r[1] for r in cur.fetchall()]  # r[1] = column name
        out[t] = cols
    return out


def _format_schema_diff(
    missing_tables: list[str],
    extra_tables: list[str],
    column_diffs: list[tuple[str, list[str], list[str]]],
) -> str:
    lines: list[str] = ["SCHEMA_MISMATCH", ""]
    if missing_tables:
        lines.append("Missing tables:")
        for t in missing_tables:
            lines.append(f"  - {t}")
        lines.append("")
    if extra_tables:
        lines.append("Unexpected tables:")
        for t in extra_tables:
            lines.append(f"  - {t}")
        lines.append("")
    if column_diffs:
        lines.append("Column mismatches:")
        for t, missing_cols, extra_cols in column_diffs:
            lines.append(f"  - {t}:")
            lines.append(f"      missing: {missing_cols}")
            lines.append(f"      unexpected: {extra_cols}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def validate_schema(conn: sqlite3.Connection, expected: ExpectedSchema) -> None:
    actual = _introspect_schema(conn)
    exp_tables = {t.name: list(t.columns) for t in expected.tables}

    missing_tables = sorted(set(exp_tables) - set(actual))
    extra_tables = sorted(set(actual) - set(exp_tables))

    column_diffs: list[tuple[str, list[str], list[str]]] = []
    for tname, exp_cols in exp_tables.items():
        if tname not in actual:
            continue
        act_cols = actual[tname]
        missing_cols = [c for c in exp_cols if c not in act_cols]
        extra_cols = [c for c in act_cols if c not in exp_cols]
        if missing_cols or extra_cols:
            column_diffs.append((tname, missing_cols, extra_cols))

    if missing_tables or extra_tables or column_diffs:
        diff = _format_schema_diff(missing_tables, extra_tables, column_diffs)
        raise DatabaseSchemaMismatchError("Database schema mismatch.", diff=diff)


# ----------------------------
# Project discovery helpers
# ----------------------------

def _scan_for_project_name(base_dir: Path, project_name: str) -> list[Path]:
    hits: list[Path] = []
    if not base_dir.exists():
        return hits

    for d in base_dir.iterdir():
        if not d.is_dir():
            continue
        manifest = d / "manifest.json"
        if not manifest.exists():
            continue
        try:
            m = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("version") == "v1" and m.get("project_name") == project_name:
            hits.append(d)
    return hits


def _ensure_staging_tree(staging_dir: Path) -> None:
    staging_dir.mkdir(parents=True, exist_ok=False)
    for sub in ["pdfs", "ingested", "indexes", "drafts", "exports", "logs"]:
        (staging_dir / sub).mkdir(parents=False, exist_ok=False)


# ----------------------------
# Public API
# ----------------------------

def create_project(
    cfg: ProjectConfig,
    *,
    expected_schema: ExpectedSchema,
    canonical_schema_sql: str,
) -> ProjectInfo:
    """
    Atomic creation:
      - create temp dir
      - create folders
      - init DB + apply schema + write schema_meta
      - validate schema_meta + tables/columns
      - write manifest LAST
      - rename temp dir -> final dir
    Rollback: delete staging dir on any failure.
    """
    _validate_config(cfg)

    base = cfg.base_projects_dir
    project_id = f"{_date_yyyy_mm_dd_utc()}_{cfg.project_name}"
    final_dir = base / project_id

    # Uniqueness checks
    dup_name_dirs = _scan_for_project_name(base, cfg.project_name)
    if dup_name_dirs:
        raise DuplicateProjectNameError(
            f"Duplicate project_name '{cfg.project_name}' already exists.",
            diagnostic="found_in=" + ",".join(str(p) for p in dup_name_dirs),
        )
    if final_dir.exists():
        raise DuplicateProjectIdError(
            f"Duplicate project_id '{project_id}' already exists.",
            diagnostic=str(final_dir),
        )

    staging_dir = base / f".tmp_{project_id}_{uuid.uuid4().hex}"
    created_at = _utc_now_iso()

    # staging paths
    log_path = staging_dir / "logs" / "project.log"
    db_path = staging_dir / "library.db"
    manifest_path = staging_dir / "manifest.json"

    conn: sqlite3.Connection | None = None
    schema_hash = compute_schema_hash(canonical_schema_sql)

    try:
        base.mkdir(parents=True, exist_ok=True)

        _ensure_staging_tree(staging_dir)
        _log(
            log_path, "INFO", "create.start",
            f"project_name={cfg.project_name} sources={','.join(cfg.sources)} citation_style={cfg.citation_style}",
        )

        _log(log_path, "INFO", "create.dirs_created")

        # DB init
        _log(log_path, "INFO", "create.db_init", f"path={db_path}")
        conn = sqlite3.connect(db_path)
        apply_canonical_schema(conn, canonical_schema_sql)
        upsert_schema_meta(conn, schema_version="v1", schema_hash=schema_hash)
        verify_schema_meta(conn, expected_version="v1", expected_hash=schema_hash)
        validate_schema(conn, expected_schema)
        _log(log_path, "INFO", "create.schema_validated")

        conn.close()
        conn = None

        # Manifest last
        m = _manifest_dict(cfg, project_id, created_at)
        manifest_path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _log(log_path, "INFO", "create.manifest_written", f"path={manifest_path}")

        _validate_manifest_v1(_read_manifest(manifest_path), final_dir)

        # Finalize: atomic rename
        staging_dir.rename(final_dir)
        # write finalization line in the final log file (now moved)
        _log(final_dir / "logs" / "project.log", "INFO", "create.finalized", f"project_dir={final_dir}")

        return ProjectInfo(
            project_id=project_id,
            project_dir=final_dir,
            manifest_path=final_dir / "manifest.json",
            database_path=final_dir / "library.db",
            status="created",
        )

    except Exception as e:
        # best-effort log + rollback
        try:
            if staging_dir.exists():
                _log(log_path, "ERROR", "create.failed", f"error={type(e).__name__} detail={str(e)}")
                _write_text_line(log_path, "traceback:\n" + traceback.format_exc())
        except Exception:
            pass

        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass

        try:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
        except Exception as re_err:
            raise FilesystemError("Creation failed and rollback also failed.", diagnostic=str(re_err)) from e

        if isinstance(e, ProjectCreatorError):
            raise
        raise ProjectCreatorError("Project creation failed.", diagnostic=str(e)) from e

    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def open_project(
    project_dir: Path,
    *,
    expected_schema: ExpectedSchema,
    canonical_schema_sql: str,
) -> ProjectInfo:
    manifest_path = project_dir / "manifest.json"
    db_path = project_dir / "library.db"

    m = _read_manifest(manifest_path)
    _validate_manifest_v1(m, project_dir)

    if not db_path.exists():
        raise ProjectOpenError("library.db not found.", diagnostic=str(db_path))

    schema_hash = compute_schema_hash(canonical_schema_sql)

    conn = sqlite3.connect(db_path)
    try:
        verify_schema_meta(conn, expected_version="v1", expected_hash=schema_hash)
        validate_schema(conn, expected_schema)
    finally:
        conn.close()

    return ProjectInfo(
        project_id=m["project_id"],
        project_dir=project_dir,
        manifest_path=manifest_path,
        database_path=db_path,
        status="opened",
    )


def list_projects(base_projects_dir: Path) -> list[ProjectSummary]:
    """
    Scan base_projects_dir for directories containing manifest.json.
    Strict v1: valid manifests must parse and be version=='v1' and match folder name.
    Corrupt manifests are "flagged" (valid=False) with an error string.
    """
    out: list[ProjectSummary] = []
    if not base_projects_dir.exists():
        return out

    dirs = [p for p in base_projects_dir.iterdir() if p.is_dir()]
    for d in sorted(dirs, key=lambda p: p.name):
        manifest = d / "manifest.json"
        if not manifest.exists():
            continue

        try:
            m = json.loads(manifest.read_text(encoding="utf-8"))
            if m.get("version") != "v1":
                raise ValueError(f"Unsupported version: {m.get('version')!r}")
            if m.get("project_id") != d.name:
                raise ValueError("project_id mismatch")

            out.append(ProjectSummary(
                project_id=m["project_id"],
                project_name=m["project_name"],
                project_dir=d,
                created_at=m["created_at"],
                topic_prompt=m["topic_prompt"],
                valid=True,
                error=None,
            ))
        except Exception as e:
            out.append(ProjectSummary(
                project_id=d.name,
                project_name="(unknown)",
                project_dir=d,
                created_at="",
                topic_prompt="",
                valid=False,
                error=str(e),
            ))

    return out
