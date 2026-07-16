"""T-7.1..T-7.6 tests: CLI entry point + REPL + dot-commands + multi-line + batch + TxManager routing."""
from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile

import pytest


def _run_cli(input_text: str, args: list[str] | None = None) -> tuple[int, str, str]:
    """Invoke main() in-process with synthetic stdin/stdout."""
    from tinydb import cli
    stdin = io.StringIO(input_text)
    stdout = io.StringIO()
    stderr = io.StringIO()
    if args is None:
        argv = ["test.db"]
    else:
        argv = args
    rc = cli.main(argv, stdin=stdin, stdout=stdout, stderr=stderr)
    return rc, stdout.getvalue(), stderr.getvalue()


class TestCliHelpVersion:
    def test_version_exits_zero(self) -> None:
        rc, out, err = _run_cli("", ["--version"])
        assert rc == 0
        assert "0.1.0" in out

    def test_no_args_shows_usage(self) -> None:
        rc, out, err = _run_cli("", [])
        assert rc == 2
        assert "Usage" in err


class TestReplBasic:
    def test_create_table(self, tmp_path) -> None:
        db_path = str(tmp_path / "t.db")
        rc, out, err = _run_cli(
            f"CREATE TABLE users (id INT, name TEXT);\n.exit\n",
            [db_path],
        )
        assert rc == 0
        assert "OK" in out

    def test_select_empty(self, tmp_path) -> None:
        db_path = str(tmp_path / "t.db")
        rc, out, err = _run_cli(
            f"CREATE TABLE t (id INT);\nSELECT * FROM t;\n.exit\n",
            [db_path],
        )
        assert rc == 0
        assert "(empty)" in out or "row(s)" in out

    def test_insert_returns_count(self, tmp_path) -> None:
        db_path = str(tmp_path / "t.db")
        rc, out, err = _run_cli(
            f"CREATE TABLE t (id INT);\n"
            f"INSERT INTO t VALUES (1);\n.exit\n",
            [db_path],
        )
        assert rc == 0
        assert "1 row(s)" in out

    def test_select_after_insert_shows_row(self, tmp_path) -> None:
        db_path = str(tmp_path / "t.db")
        rc, out, err = _run_cli(
            f"CREATE TABLE t (id INT);\n"
            f"INSERT INTO t VALUES (42);\n"
            f"SELECT id FROM t;\n.exit\n",
            [db_path],
        )
        assert rc == 0
        assert "42" in out
        assert "row(s)" in out

    def test_parse_error_does_not_kill_repl(self, tmp_path) -> None:
        db_path = str(tmp_path / "t.db")
        rc, out, err = _run_cli(
            f"SELEC * FROM t;\n.exit\n",
            [db_path],
        )
        assert rc == 0
        # Error went to stderr; REPL continues
        assert err.strip() != "", "expected an error message on stderr"
        assert "unexpected token" in err or "ParseError" in err or "parse" in err.lower()


class TestDotCommands:
    def test_tables_empty(self, tmp_path) -> None:
        db_path = str(tmp_path / "t.db")
        rc, out, err = _run_cli(
            ".tables\n.exit\n",
            [db_path],
        )
        assert rc == 0
        # No table names listed (empty output besides header)

    def test_tables_after_create(self, tmp_path) -> None:
        db_path = str(tmp_path / "t.db")
        rc, out, err = _run_cli(
            f"CREATE TABLE users (id INT);\n.tables\n.exit\n",
            [db_path],
        )
        assert rc == 0
        assert "users" in out

    def test_schema_shows_create(self, tmp_path) -> None:
        db_path = str(tmp_path / "t.db")
        rc, out, err = _run_cli(
            f"CREATE TABLE users (id INT PRIMARY KEY, name TEXT NOT NULL);\n"
            f".schema users\n.exit\n",
            [db_path],
        )
        assert rc == 0
        assert "CREATE TABLE users" in out
        assert "id" in out and "name" in out


class TestBatchMode:
    def test_batch_success(self, tmp_path) -> None:
        db_path = str(tmp_path / "t.db")
        rc, out, err = _run_cli(
            f"CREATE TABLE t (id INT);\n"
            f"INSERT INTO t VALUES (1);\n",
            [db_path],
        )
        assert rc == 0

    def test_batch_persists_across_runs(self, tmp_path) -> None:
        db_path = str(tmp_path / "t.db")
        _run_cli(
            f"CREATE TABLE t (id INT);\nINSERT INTO t VALUES (1);\n",
            [db_path],
        )
        rc, out, _ = _run_cli(
            f"SELECT id FROM t;\n",
            [db_path],
        )
        assert rc == 0
        assert "1" in out


class TestTxRouting:
    def test_begin_commit(self, tmp_path) -> None:
        db_path = str(tmp_path / "t.db")
        rc, out, err = _run_cli(
            f"CREATE TABLE t (id INT);\n"
            f"BEGIN;\nINSERT INTO t VALUES (1);\nCOMMIT;\n.exit\n",
            [db_path],
        )
        assert rc == 0
