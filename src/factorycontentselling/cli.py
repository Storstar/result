from __future__ import annotations

import argparse
import sys
from typing import Optional


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="factorycontent MVP tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("run-bot", help="Run the Telegram intake bot")

    pipeline_parser = subparsers.add_parser("run-pipeline", help="Run the pipeline for an existing submission")
    pipeline_parser.add_argument("--submission-id", required=True, help="Existing submission id under submissions/")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run-bot":
        from .bot import run_bot

        run_bot()
        return 0

    if args.command == "run-pipeline":
        from .orchestrator import SubmissionOrchestrator
        from .storage import SubmissionStorage

        storage = SubmissionStorage()
        orchestrator = SubmissionOrchestrator(storage=storage)
        result = orchestrator.run(args.submission_id)
        print(f"submission_id={result.submission_id}")
        print(f"status={result.status}")
        for key, value in result.artifacts.items():
            print(f"{key}={value}")
        if result.warnings:
            print("warnings:")
            for warning in result.warnings:
                print(f"- {warning}")
        if result.errors:
            print("errors:")
            for error in result.errors:
                print(f"- {error}")
            return 1
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
