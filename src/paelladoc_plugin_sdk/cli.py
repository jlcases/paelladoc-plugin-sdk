"""Command line tools for PAELLADOC plugin authors."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .manifest import ManifestError, validate_plugin_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paelladoc-plugin")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a plugin directory")
    validate_parser.add_argument("plugin_dir", type=Path)

    args = parser.parse_args(argv)
    if args.command == "validate":
        return _validate(args.plugin_dir)
    parser.error(f"unknown command: {args.command}")
    return 2


def _validate(plugin_dir: Path) -> int:
    try:
        manifest = validate_plugin_dir(plugin_dir)
    except ManifestError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1

    contribution_count = sum(len(paths) for paths in manifest.contributes.values())
    print(f"OK {manifest.plugin_id}@{manifest.version} ({contribution_count} contributions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
