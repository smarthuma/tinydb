"""tinydb CLI / REPL — interactive command-line interface.

Design references:
  - specs/cli-repl/spec.md (REQ-CR-001..007)
  - design.md (no separate decision — straightforward stdio layer)
"""
from __future__ import annotations

import argparse
import sys
from typing import Callable, TextIO

from tinydb import executor, parser, tx
from tinydb import types as tt


__version__ = "0.1.0"


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tinydb",
        description="tinydb — a tiny embedded relational database (CLI/REPL)",
    )
    p.add_argument("path", nargs="?", help="path to .db file")
    p.add_argument("--version", action="store_true", help="print version and exit")
    return p


def _print_result(result: object, out: TextIO) -> None:
    """Render an Executor result for the REPL."""
    if isinstance(result, list):
        # SELECT result — list of tuples
        if not result:
            out.write("(empty)\n")
            return
        # Compute column widths
        cols = len(result[0])
        str_rows = [[str(v) if v is not None else "" for v in row] for row in result]
        widths = [max(len(str_rows[i][c]) for i in range(len(str_rows))) for c in range(cols)]
        # Header
        out.write(" | ".join("".ljust(widths[c]) for c in range(cols)) + "\n")
        out.write("-+-".join("-" * widths[c] for c in range(cols)) + "\n")
        for row in str_rows:
            out.write(" | ".join(row[c].ljust(widths[c]) for c in range(cols)) + "\n")
        out.write(f"{len(result)} row(s)\n")
    elif isinstance(result, int):
        out.write(f"{result} row(s) affected\n")
    else:
        out.write("OK\n")


def _handle_dot_command(line: str, db: executor.Executor, tx_mgr: tx.TxManager, out: TextIO) -> bool:
    """Return True if the line was a dot-command (handled); False otherwise."""
    parts = line.strip().split()
    if not parts:
        return True
    cmd = parts[0].lower()
    if cmd in (".exit", ".quit"):
        raise EOFError
    if cmd == ".tables":
        for name in db.catalog.all_tables():
            out.write(name + "\n")
        return True
    if cmd == ".help":
        out.write(".tables — list tables\n.schema <name> — show CREATE TABLE\n.exit / .quit — exit\n")
        return True
    if cmd == ".schema" and len(parts) >= 2:
        name = parts[1]
        schema = db.catalog.get_schema(name)
        if schema is None:
            out.write(f"TableNotFound({name!r})\n")
        else:
            cols = ", ".join(
                f"{c.name} {c.type_name}" + (" " + " ".join(c.constraints) if c.constraints else "")
                for c in schema.columns
            )
            out.write(f"CREATE TABLE {name} ({cols});\n")
        return True
    return False


def _execute_sql(
    sql: str, db: executor.Executor, tx_mgr: tx.TxManager, out: TextIO, err: TextIO,
) -> None:
    """Parse, dispatch (tx-control vs DDL/DML), execute, print result."""
    from tinydb.parser.ast import Begin, Commit, Rollback
    try:
        from tinydb.parser.parser import parse as parse_sql
        stmt = parse_sql(sql)
    except tt.ParseError as e:
        err.write(str(e) + "\n")
        return
    try:
        if isinstance(stmt, Begin):
            db.begin_transaction()
            tx_mgr.begin()  # low-level WAL
            out.write("OK\n")
            return
        if isinstance(stmt, Commit):
            tx_id = getattr(tx_mgr, "_current_tx_id", None)
            if tx_id is not None:
                db.commit_transaction()
                tx_mgr.commit(tx_id)
                out.write("OK\n")
            else:
                err.write("no active transaction\n")
            return
        if isinstance(stmt, Rollback):
            tx_id = getattr(tx_mgr, "_current_tx_id", None)
            if tx_id is not None:
                db.rollback_transaction()
                tx_mgr.rollback(tx_id)
                out.write("OK\n")
            else:
                err.write("no active transaction\n")
            return
        result = db.execute(stmt)
        _print_result(result, out)
    except tt.TinyDBError as e:
        err.write(str(e) + "\n")


def _repl(stdin: TextIO, stdout: TextIO, stderr: TextIO, db_path: str) -> int:
    """Read statements (one per line or multi-line until `;`) and execute."""
    db = executor.Executor.open(db_path)
    try:
        tx_mgr = tx.TxManager(db._store)  # type: ignore[attr-defined]
    except Exception:
        tx_mgr = tx.TxManager(db._store)  # type: ignore[attr-defined]
    stdout.write(f"tinydb v{__version__} — type .help for commands\n")
    stdout.write("> ")
    stdout.flush()
    buffer: list[str] = []
    try:
        while True:
            line = stdin.readline()
            if not line:
                # EOF
                if buffer:
                    _execute_sql(" ".join(buffer), db, tx_mgr, stdout, stderr)
                break
            line = line.rstrip("\n")
            stripped = line.strip()
            if not buffer and stripped.startswith("."):
                try:
                    _handle_dot_command(stripped, db, tx_mgr, stdout)
                except EOFError:
                    break
                stdout.write("> ")
                stdout.flush()
                continue
            buffer.append(line)
            if ";" in line:
                sql = " ".join(buffer).strip()
                _execute_sql(sql, db, tx_mgr, stdout, stderr)
                buffer = []
                stdout.write("> ")
                stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            tx_mgr.close()
        except Exception:
            pass
        try:
            db.close()
        except Exception:
            pass
    return 0


def main(argv: list[str] | None = None, stdin: TextIO | None = None,
         stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr
    args = _build_arg_parser().parse_args(argv)
    if args.version:
        stdout.write(f"tinydb {__version__}\n")
        return 0
    if not args.path:
        stderr.write("Usage: tinydb <file.db> [--version]\n")
        return 2
    return _repl(stdin, stdout, stderr, args.path)


if __name__ == "__main__":
    sys.exit(main())
