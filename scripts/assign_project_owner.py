"""Give projects created before authentication an owner.

With authentication on, a project is visible only to the user who owns it.
Projects created in local single-user mode have no owner, so after switching
auth on they are visible to nobody — deliberately, rather than to everybody.
This script hands them to a user, explicitly.

    # list projects and their owners
    python scripts/assign_project_owner.py --list

    # give every unowned project to one Better Auth user id
    python scripts/assign_project_owner.py --owner <user-id> --all-unowned

    # or just one project
    python scripts/assign_project_owner.py --owner <user-id> --project <project-id>

It uses the same configuration as the API (``.env``), so it writes to SQLite or
to Supabase Postgres, whichever the API is using.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from app import bootstrap  # noqa: E402,F401
from app.store import metadata_store  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="list projects and owners")
    parser.add_argument("--owner", help="Better Auth user id to assign")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--project", help="one project id")
    target.add_argument("--all-unowned", action="store_true", help="every project with no owner")
    args = parser.parse_args(argv)

    metadata_store.load()
    projects = metadata_store.list_projects()

    if args.list or not args.owner:
        for project in projects:
            print(f"{project.id}  owner={project.owner_id or '(none)'}  {project.name}")
        return 0

    if args.project:
        chosen = [p for p in projects if p.id == args.project]
        if not chosen:
            print(f"No project {args.project}", file=sys.stderr)
            return 1
    elif args.all_unowned:
        chosen = [p for p in projects if not p.owner_id]
    else:
        parser.error("choose --project <id> or --all-unowned")

    for project in chosen:
        project.owner_id = args.owner
        metadata_store._persist("projects", project)
        print(f"assigned {project.id} ({project.name}) to {args.owner}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
