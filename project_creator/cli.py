from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from project_creator.project_creator import (
    ProjectConfig,
    create_project,
    list_projects,
    open_project,
    ProjectCreatorError,
)
from project_overview.canonical_schema import CANONICAL_SCHEMA_SQL, EXPECTED_SCHEMA


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def cmd_create(args: argparse.Namespace) -> int:
    cfg = ProjectConfig(
        project_name=args.name,
        topic_prompt=args.topic,
        base_projects_dir=Path(args.base_dir),
        citation_style="vancouver",
        sources=tuple(args.sources),
        notes=args.notes,
    )
    info = create_project(cfg, expected_schema=EXPECTED_SCHEMA, canonical_schema_sql=CANONICAL_SCHEMA_SQL)
    _print_json({
        "project_id": info.project_id,
        "project_dir": str(info.project_dir),
        "manifest_path": str(info.manifest_path),
        "database_path": str(info.database_path),
        "status": info.status,
    })
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir)
    info = open_project(project_dir, expected_schema=EXPECTED_SCHEMA, canonical_schema_sql=CANONICAL_SCHEMA_SQL)
    _print_json({
        "project_id": info.project_id,
        "project_dir": str(info.project_dir),
        "manifest_path": str(info.manifest_path),
        "database_path": str(info.database_path),
        "status": info.status,
    })
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    base = Path(args.base_dir)
    items = list_projects(base)
    _print_json([{
        "project_id": p.project_id,
        "project_name": p.project_name,
        "project_dir": str(p.project_dir),
        "created_at": p.created_at,
        "topic_prompt": p.topic_prompt,
        "valid": p.valid,
        "error": p.error,
    } for p in items])
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="project_creator", description="AI Project 1 - Project Creator (v1)")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="Create a new project workspace")
    p_create.add_argument("--name", required=True, help="project_name (lowercase snake_case)")
    p_create.add_argument("--topic", required=True, help="topic prompt")
    p_create.add_argument("--base-dir", default="./projects", help="base projects directory (default: ./projects)")
    p_create.add_argument("--sources", nargs="+", default=["pmc", "biorxiv"], help="sources (v1: pmc biorxiv)")
    p_create.add_argument("--notes", default=None, help="optional notes")
    p_create.set_defaults(func=cmd_create)

    p_open = sub.add_parser("open", help="Open an existing project (validate manifest + schema)")
    p_open.add_argument("--project-dir", required=True, help="path to the project directory")
    p_open.set_defaults(func=cmd_open)

    p_list = sub.add_parser("list", help="List projects under base directory")
    p_list.add_argument("--base-dir", default="./projects", help="base projects directory (default: ./projects)")
    p_list.set_defaults(func=cmd_list)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.func(args)
    except ProjectCreatorError as e:
        err = {"error": e.message, "diagnostic": e.diagnostic}
        print(json.dumps(err, indent=2, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
