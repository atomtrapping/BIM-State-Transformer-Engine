"""Regenerate every reproducible record in ``validation/`` from a live run.

    python validation/regenerate.py                 # what runs without the corpus
    python validation/regenerate.py --corpus DIR    # everything
    python validation/regenerate.py --check         # fail if a record drifted

``--check`` is what CI runs: it never writes, and exits non-zero when a
shipped record no longer matches what the engine produces. Records that
depend on the public IFC corpus are skipped unless ``--corpus`` is given, so
a run without it can never quietly delete them.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in (None, ""):  # direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validation.records import build_all, dumps


VALIDATION_DIR = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        default=os.environ.get("GAT_IFC_VALIDATION_ROOT"),
        help="fetched public IFC corpus directory (or GAT_IFC_VALIDATION_ROOT)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit non-zero if any shipped record has drifted",
    )
    args = parser.parse_args(argv)

    records = build_all(args.corpus)
    drifted: list[str] = []
    wrote: list[str] = []

    for name, record in sorted(records.items()):
        path = VALIDATION_DIR / name
        want = dumps(record)
        have = path.read_text(encoding="utf-8") if path.exists() else None
        if have == want:
            continue
        if args.check:
            drifted.append(name)
            continue
        path.write_text(want, encoding="utf-8")
        wrote.append(name)

    if args.corpus is None:
        print("note: no corpus given; corpus-dependent records were not rebuilt")

    if args.check:
        for name in drifted:
            print(f"drifted: {name}", file=sys.stderr)
        if drifted:
            print(
                f"\n{len(drifted)} record(s) no longer match the engine. "
                "Run validation/regenerate.py to update them, and check the "
                "diff: a changed digest means a changed decision.",
                file=sys.stderr,
            )
            return 1
        print(f"checked {len(records)} record(s): all current")
        return 0

    for name in wrote:
        print(f"wrote {name}")
    if not wrote:
        print(f"checked {len(records)} record(s): all already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
