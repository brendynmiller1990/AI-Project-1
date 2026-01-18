import json
import sqlite3
from pathlib import Path

import pytest

from project_creator import (
    create_project,
    DuplicateProjectNameError,
    InvalidProjectNameError,
)
from project_creator.project_creator import compute_schema_hash


def test_create_project_success(valid_config, expected_schema, canonical_schema_sql):
    info = create_project(
        valid_config,
        expected_schema=expected_schema,
        canonical_schema_sql=canonical_schema_sql,
    )

    assert info.status == "created"
    assert info.project_dir.exists()
    assert info.manifest_path.exists()
    assert info.database_path.exists()

    # folder structure
    for sub in ["pdfs", "ingested", "indexes", "drafts", "exports", "logs"]:
        assert (info.project_dir / sub).exists()

    # manifest v1
    m = json.loads(info.manifest_path.read_text(encoding="utf-8"))
    assert m["version"] == "v1"
    assert m["project_id"] == info.project_dir.name
    assert m["project_name"] == valid_config.project_name
    assert m["citation_style"] == "vancouver"
    assert m["status"] == "active"

    # logging
    log_path = info.project_dir / "logs" / "project.log"
    assert log_path.exists()
    log_txt = log_path.read_text(encoding="utf-8")
    assert "create.start" in log_txt
    assert "create.finalized" in log_txt

    # schema_meta populated
    schema_hash = compute_schema_hash(canonical_schema_sql)
    conn = sqlite3.connect(info.database_path)
    try:
        v = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version';").fetchone()
        h = conn.execute("SELECT value FROM schema_meta WHERE key='schema_hash';").fetchone()
        assert v and v[0] == "v1"
        assert h and h[0] == schema_hash
    finally:
        conn.close()


def test_duplicate_project_name_blocked(valid_config, expected_schema, canonical_schema_sql, base_dir: Path):
    info1 = create_project(
        valid_config,
        expected_schema=expected_schema,
        canonical_schema_sql=canonical_schema_sql,
    )
    assert info1.project_dir.exists()

    # attempt duplicate name (same project_name)
    with pytest.raises(DuplicateProjectNameError):
        create_project(
            valid_config,
            expected_schema=expected_schema,
            canonical_schema_sql=canonical_schema_sql,
        )

    # ensure no leftover temp dirs
    leftovers = [p for p in base_dir.iterdir() if p.is_dir() and p.name.startswith(".tmp_")]
    assert leftovers == []


def test_invalid_project_name(valid_config, expected_schema, canonical_schema_sql):
    bad = valid_config.__class__(
        project_name="Bad Name!",
        topic_prompt=valid_config.topic_prompt,
        base_projects_dir=valid_config.base_projects_dir,
        citation_style=valid_config.citation_style,
        sources=valid_config.sources,
        notes=valid_config.notes,
    )
    with pytest.raises(InvalidProjectNameError):
        create_project(bad, expected_schema=expected_schema, canonical_schema_sql=canonical_schema_sql)


def test_partial_creation_rollback_on_bad_schema_sql(valid_config, expected_schema, base_dir: Path):
    bad_sql = "THIS IS NOT SQL;"
    with pytest.raises(Exception):
        create_project(valid_config, expected_schema=expected_schema, canonical_schema_sql=bad_sql)

    # base dir should contain no finalized project dirs
    if base_dir.exists():
        # no tmp leftovers either
        leftovers = [p for p in base_dir.iterdir() if p.is_dir()]
        assert leftovers == []
