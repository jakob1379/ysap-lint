import argparse
import re
import sys
from pathlib import Path

from .linter import lint


_BASH_SHEBANG = re.compile(rb"#!.*\b(ba)?sh\b")


def _is_bash(path):
    if path.suffix:
        return path.suffix in (".sh", ".bash")
    try:
        with path.open("rb") as f:
            return bool(_BASH_SHEBANG.match(f.readline(256)))
    except OSError:
        return False


def _iter_files(paths):
    for p in paths:
        path = Path(p)
        if path.is_dir():
            yield from sorted(
                f for f in path.rglob("*")
                if not any(part.startswith(".")
                           for part in f.relative_to(path).parts)
                and f.is_file() and _is_bash(f))
        else:
            yield path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="ysap-lint",
        description="Bash linter for the style.ysap.sh style guide")
    sub = ap.add_subparsers(dest="cmd", required=True)
    chk = sub.add_parser("check", help="lint bash files")
    chk.add_argument("paths", nargs="+", help="files or directories")
    chk.add_argument("--ignore", default="",
                     help="comma-separated rule codes to ignore (e.g. YS102,YS501)")
    sub.add_parser("server", help="run the language server on stdio")
    args = ap.parse_args(argv)

    if args.cmd == "server":
        from .server import server
        server.start_io()
        return 0

    ignore = {c.strip().upper() for c in args.ignore.split(",") if c.strip()}
    count = 0
    errors = False
    for path in _iter_files(args.paths):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"{path}: {e}", file=sys.stderr)
            errors = True
            continue
        for d in lint(source):
            if d.code in ignore:
                continue
            count += 1
            print(f"{path}:{d.line + 1}:{d.col + 1}: {d.code} {d.message}")
    if count:
        print(f"Found {count} issue{'s' if count != 1 else ''}.")
    if errors:
        return 2
    return 1 if count else 0


if __name__ == "__main__":
    sys.exit(main())
