import json
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    # text=True gives us stdout/stderr as strings
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def _parse_json(s: str):
    return json.loads(s.strip())


def test_cli_create_list_open(tmp_path: Path):
    """
    End-to-end:
      - create a project
      - list projects
      - open the created project
    """
    project_root = Path(__file__).resolve().parents[1]  # repo root
    base_dir = tmp_path / "projects"

    # CREATE
    cp = _run(
        [
            sys.executable, "-m", "project_creator",
            "create",
            "--name", "bladder_smc_strain",
            "--topic", "Effects of cyclic mechanical strain on bladder smooth muscle cells",
            "--base-dir", str(base_dir),
            "--notes", "Initial literature exploration",
        ],
        cwd=project_root,
    )
    assert cp.returncode == 0, f"stderr:\n{cp.stderr}\nstdout:\n{cp.stdout}"

    created = _parse_json(cp.stdout)
    assert created["status"] == "created"
    assert created["project_id"].endswith("_bladder_smc_strain")
    assert Path(created["project_dir"]).name == created["project_id"]

    project_dir = project_root / created["project_dir"]
    assert project_dir.exists()
    assert (project_dir / "manifest.json").exists()
    assert (project_dir / "library.db").exists()

    # LIST
    lp = _run(
        [
            sys.executable, "-m", "project_creator",
            "list",
            "--base-dir", str(base_dir),
        ],
        cwd=project_root,
    )
    assert lp.returncode == 0, f"stderr:\n{lp.stderr}\nstdout:\n{lp.stdout}"

    items = _parse_json(lp.stdout)
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0]["valid"] is True
    assert items[0]["project_id"] == created["project_id"]

    # OPEN
    op = _run(
        [
            sys.executable, "-m", "project_creator",
            "open",
            "--project-dir", str(base_dir / created["project_id"]),
        ],
        cwd=project_root,
    )
    assert op.returncode == 0, f"stderr:\n{op.stderr}\nstdout:\n{op.stdout}"

    opened = _parse_json(op.stdout)
    assert opened["status"] == "opened"
    assert opened["project_id"] == created["project_id"]


def test_cli_duplicate_name_is_error(tmp_path: Path):
    """
    Create a project, then try to create again with same name in same base-dir.
    Must return exit code 2 and emit JSON error on stderr.
    """
    project_root = Path(__file__).resolve().parents[1]
    base_dir = tmp_path / "projects"

    # First create (should succeed)
    cp1 = _run(
        [
            sys.executable, "-m", "project_creator",
            "create",
            "--name", "bladder_smc_strain",
            "--topic", "x",
            "--base-dir", str(base_dir),
        ],
        cwd=project_root,
    )
    assert cp1.returncode == 0, f"stderr:\n{cp1.stderr}\nstdout:\n{cp1.stdout}"

    # Second create (must fail)
    cp2 = _run(
        [
            sys.executable, "-m", "project_creator",
            "create",
            "--name", "bladder_smc_strain",
            "--topic", "y",
            "--base-dir", str(base_dir),
        ],
        cwd=project_root,
    )
    assert cp2.returncode == 2, f"stderr:\n{cp2.stderr}\nstdout:\n{cp2.stdout}"

    err = _parse_json(cp2.stderr)
    assert "error" in err
    assert "Duplicate project_name" in err["error"] or "Duplicate" in err["error"]
    assert "diagnostic" in err


def test_cli_open_missing_project_is_error(tmp_path: Path):
    """
    Opening a non-existent project should return exit code 2 with JSON error on stderr.
    """
    project_root = Path(__file__).resolve().parents[1]
    missing_dir = tmp_path / "projects" / "does_not_exist"

    op = _run(
        [
            sys.executable, "-m", "project_creator",
            "open",
            "--project-dir", str(missing_dir),
        ],
        cwd=project_root,
    )
    assert op.returncode == 2, f"stderr:\n{op.stderr}\nstdout:\n{op.stdout}"

    err = _parse_json(op.stderr)
    assert "error" in err
