import json
import shutil

from project_creator import create_project, list_projects, open_project, ProjectOpenError


def test_list_projects_skips_deleted_folder(valid_config, expected_schema, canonical_schema_sql, base_dir):
    info = create_project(valid_config, expected_schema=expected_schema, canonical_schema_sql=canonical_schema_sql)
    shutil.rmtree(info.project_dir)

    projects = list_projects(base_dir)
    assert all(p.project_id != info.project_id for p in projects)


def test_corrupt_manifest_flagged_and_open_blocked(valid_config, expected_schema, canonical_schema_sql, base_dir):
    info = create_project(valid_config, expected_schema=expected_schema, canonical_schema_sql=canonical_schema_sql)

    # corrupt manifest
    info.manifest_path.write_text("{not valid json", encoding="utf-8")

    projects = list_projects(base_dir)
    flagged = [p for p in projects if p.project_dir == info.project_dir]
    assert len(flagged) == 1
    assert flagged[0].valid is False
    assert flagged[0].error is not None

    # open should fail loudly
    try:
        open_project(info.project_dir, expected_schema=expected_schema, canonical_schema_sql=canonical_schema_sql)
        assert False, "Expected ProjectOpenError"
    except ProjectOpenError:
        pass
