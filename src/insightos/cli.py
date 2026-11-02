"""Command-line entry point. Phase 1 exposes only ``--version`` and ``info``."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Sequence

from pydantic import ValidationError

from insightos import __version__
from insightos.errors import ConfigurationError
from insightos.runs import RunPhase
from insightos.settings import Settings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="insightos",
        description="InsightOS - AI-assisted, evidence-driven data preprocessing.",
    )
    parser.add_argument("--version", action="version", version=f"insightos {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("info", help="print the effective configuration (secrets masked) as JSON")
    return parser


def _cmd_info() -> int:
    settings = Settings()
    payload = {
        "insightos_version": __version__,
        "python_version": platform.python_version(),
        "settings": settings.public_dict(),
        "run_phase_dirs": [phase.value for phase in RunPhase],
    }
    print(json.dumps(payload, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        if args.command == "info":
            return _cmd_info()
    except (ConfigurationError, ValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    parser.error(f"unknown command: {args.command}")  # pragma: no cover - argparse guards this
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
