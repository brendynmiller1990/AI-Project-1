import os
import sqlite3
import time

import pytest

from project_creator import open_project, create_project, ProjectOpenError, DatabaseSchemaMismatchError


def test_open_existing_project_no_reinit(valid_config, expected_schema, canonical_schema_sql):
    info = create_project(valid_config, expected_schema=expected_schema, canonical_schema_sql=canonical_schema_sql)

    # record mtimes
    m_mtime = info.manifest_path.stat().st_mtime
    db_mtime = info.database_path.stat().st_mtime

    time.sleep(0.01)  # small buffer for filesystem timestamp resolution

    opened = open_project(
        info.project_dir,
        expected_schema=expected_schema,
        canonical_schema_sql=canonical_schema_sql,
    )
    assert opened.status == "opened"

    # should not have rewritten files
    assert info.manifest_path.stat().st_mtime == m_mtime
    assert info.database_path.stat().st_mtime == db_mtime


def test_open_missing_db(valid_config, expected_schema, canonical_schema_sql):
    info = create_project(valid_config, expected_schema=expected_schema, canonical_schema_sql=canonical_schema_sql)
    info.database_path.unlink()

    with pytest.raises(ProjectOpenError):
        open_project(info.project_dir, expected_schema=expected_schema, canonical_schema_sql=canonical_schema_sql)


def test_open_schema_meta_version_mismatch(valid_config, expected_schema, canonical_schema_sql):
    info = create_project(valid_config, expected_schema=expected_schema, canonical_schema_sql=canonical_schema_sql)

    conn = sqlite3.connect(info.database_path)
    try:
        conn.execute("UPDATE schema_meta SET value='v2' WHERE key='schema_version';")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(DatabaseSchemaMismatchError) as ei:
        open_project(info.project_dir, expected_schema=expected_schema, canonical_schema_sql=canonical_schema_sql)

    assert "expected schema_version='v1' got 'v2'" in ei.value.diff


def test_open_schema_table_column_mismatch(valid_config, expected_schema, canonical_schema_sql):
    info = create_project(valid_config, expected_schema=expected_schema, canonical_schema_sql=canonical_schema_sql)

    # create a mismatch by adding a column
    conn = sqlite3.connect(info.database_path)
    try:
        conn.execute("ALTER TABLE papers ADD COLUMN unexpected_col TEXT;")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(DatabaseSchemaMismatchError) as ei:
        open_project(info.project_dir, expected_schema=expected_schema, canonical_schema_sql=canonical_schema_sql)

    assert "SCHEMA_MISMATCH" in ei.value.diff
    assert "Column mismatches:" in ei.value.diff
    assert "papers" in ei.value.diff
