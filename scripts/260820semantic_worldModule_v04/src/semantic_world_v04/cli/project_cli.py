"""Create, validate, and compile v04 projects without a UI."""

import argparse
import json
from pathlib import Path

from semantic_world_v04.core.serde import pretty_json
from semantic_world_v04.studio import StudioController


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Semantic World v04 project tool")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("project_dir")
    create.add_argument("--project-id", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--usd", required=True)
    create.add_argument("--output", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("project_dir")

    compile_command = sub.add_parser("compile")
    compile_command.add_argument("project_dir")
    compile_command.add_argument("--job-id")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    controller = StudioController()
    if args.command == "create":
        controller.new_project(
            project_id=args.project_id,
            name=args.name,
            usd_path=args.usd,
            output_root=args.output,
        )
        controller.save_project(Path(args.project_dir))
        print(args.project_dir)
        return 0
    controller.open_project(Path(args.project_dir))
    if args.command == "validate":
        issues = controller.validate()
        if issues:
            print("\n".join(str(issue) for issue in issues))
            return 1
        print("validation passed")
        return 0
    job = controller.compile_job(job_id=args.job_id)
    print(pretty_json(job.to_dict()), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

