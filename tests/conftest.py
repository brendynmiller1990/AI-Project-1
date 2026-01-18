import pytest
from pathlib import Path

from project_creator import ProjectConfig
from project_overview.canonical_schema import CANONICAL_SCHEMA_SQL, EXPECTED_SCHEMA


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    return tmp_path / "projects"


@pytest.fixture
def canonical_schema_sql() -> str:
    return CANONICAL_SCHEMA_SQL


@pytest.fixture
def expected_schema():
    return EXPECTED_SCHEMA


@pytest.fixture
def valid_config(base_dir: Path) -> ProjectConfig:
    return ProjectConfig(
        project_name="bladder_smc_strain",
        topic_prompt="Effects of cyclic mechanical strain on bladder smooth muscle cells",
        base_projects_dir=base_dir,
        citation_style="vancouver",
        sources=("pmc", "biorxiv"),
        notes="Initial literature exploration for review paper",
    )
