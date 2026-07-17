"""Tests for ACID transactions (BEGIN/COMMIT/ROLLBACK)."""
from __future__ import annotations

import pytest

from tinydb import executor
from tinydb.parser.parser import parse
from tinydb import types as tt


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "t.db")
    d = executor.Executor.open(path)
    yield d
    d.close()


class TestBeginCommit:
    def test_commit_persists_writes(self, db):
        db.execute(parse("CREATE TABLE t (id INT);"))
        db.execute(parse("INSERT INTO t VALUES (1);"))
        db.begin_transaction()
        db.execute(parse("INSERT INTO t VALUES (2);"))
        db.execute(parse("INSERT INTO t VALUES (3);"))
        db.commit_transaction()
        rows = db.execute(parse("SELECT id FROM t ORDER BY id;"))
        assert [r[0] for r in rows] == [1, 2, 3]

    def test_in_transaction_flag(self, db):
        db.execute(parse("CREATE TABLE t (id INT);"))
        assert db.in_transaction is False
        db.begin_transaction()
        assert db.in_transaction is True
        db.commit_transaction()
        assert db.in_transaction is False

    def test_nested_begin_rejected(self, db):
        db.execute(parse("CREATE TABLE t (id INT);"))
        db.begin_transaction()
        with pytest.raises(tt.TinyDBError):
            db.begin_transaction()
        db.commit_transaction()

    def test_commit_without_begin_raises(self, db):
        with pytest.raises(tt.TinyDBError):
            db.commit_transaction()


class TestBeginRollback:
    def test_rollback_discards_inserts(self, db):
        db.execute(parse("CREATE TABLE t (id INT, n TEXT);"))
        db.execute(parse("INSERT INTO t VALUES (1, 'a');"))
        db.execute(parse("INSERT INTO t VALUES (2, 'b');"))
        db.begin_transaction()
        db.execute(parse("INSERT INTO t VALUES (3, 'c');"))
        db.execute(parse("INSERT INTO t VALUES (4, 'd');"))
        db.rollback_transaction()
        rows = db.execute(parse("SELECT id FROM t ORDER BY id;"))
        assert [r[0] for r in rows] == [1, 2]

    def test_rollback_via_cli_string(self, db):
        # Simulate CLI's BEGIN;...;ROLLBACK; routing
        db.execute(parse("CREATE TABLE t (id INT);"))
        db.execute(parse("INSERT INTO t VALUES (1);"))
        db.begin_transaction()
        db.execute(parse("INSERT INTO t VALUES (99);"))
        db.rollback_transaction()
        rows = db.execute(parse("SELECT COUNT(*) FROM t;"))
        assert rows[0][0] == 1

    def test_rollback_discards_updates(self, db):
        db.execute(parse("CREATE TABLE t (id INT, n TEXT);"))
        db.execute(parse("INSERT INTO t VALUES (1, 'a');"))
        db.execute(parse("INSERT INTO t VALUES (2, 'b');"))
        db.begin_transaction()
        db.execute(parse("UPDATE t SET n = 'X' WHERE id = 1;"))
        # Inside tx: should see updated value
        rows = db.execute(parse("SELECT n FROM t WHERE id = 1;"))
        assert rows[0][0] == "X"
        db.rollback_transaction()
        # After rollback: original value
        rows = db.execute(parse("SELECT n FROM t WHERE id = 1;"))
        assert rows[0][0] == "a"

    def test_rollback_discards_deletes(self, db):
        db.execute(parse("CREATE TABLE t (id INT);"))
        db.execute(parse("INSERT INTO t VALUES (1);"))
        db.execute(parse("INSERT INTO t VALUES (2);"))
        db.begin_transaction()
        db.execute(parse("DELETE FROM t WHERE id = 1;"))
        db.rollback_transaction()
        rows = db.execute(parse("SELECT id FROM t ORDER BY id;"))
        assert [r[0] for r in rows] == [1, 2]

    def test_rollback_without_begin_raises(self, db):
        with pytest.raises(tt.TinyDBError):
            db.rollback_transaction()


class TestTransactionPersistence:
    def test_committed_data_survives_reopen(self, tmp_path):
        path = str(tmp_path / "t.db")
        d1 = executor.Executor.open(path)
        d1.execute(parse("CREATE TABLE t (id INT);"))
        d1.execute(parse("INSERT INTO t VALUES (1);"))
        d1.begin_transaction()
        d1.execute(parse("INSERT INTO t VALUES (2);"))
        d1.commit_transaction()
        d1.close()
        # Reopen
        d2 = executor.Executor.open(path)
        rows = d2.execute(parse("SELECT id FROM t ORDER BY id;"))
        assert [r[0] for r in rows] == [1, 2]
        d2.close()

    def test_rolled_back_data_not_persisted(self, tmp_path):
        path = str(tmp_path / "t.db")
        d1 = executor.Executor.open(path)
        d1.execute(parse("CREATE TABLE t (id INT);"))
        d1.execute(parse("INSERT INTO t VALUES (1);"))
        d1.begin_transaction()
        d1.execute(parse("INSERT INTO t VALUES (999);"))
        d1.rollback_transaction()
        d1.close()
        # Reopen
        d2 = executor.Executor.open(path)
        rows = d2.execute(parse("SELECT id FROM t ORDER BY id;"))
        assert [r[0] for r in rows] == [1]  # 999 was rolled back
        d2.close()


class TestMultiTableTransaction:
    def test_rollback_restores_all_tables(self, db):
        db.execute(parse("CREATE TABLE a (id INT);"))
        db.execute(parse("CREATE TABLE b (id INT);"))
        db.execute(parse("INSERT INTO a VALUES (1);"))
        db.execute(parse("INSERT INTO b VALUES (10);"))
        db.begin_transaction()
        db.execute(parse("INSERT INTO a VALUES (2);"))
        db.execute(parse("INSERT INTO b VALUES (20);"))
        db.execute(parse("UPDATE a SET id = 999 WHERE id = 1;"))
        db.rollback_transaction()
        a_rows = db.execute(parse("SELECT id FROM a ORDER BY id;"))
        b_rows = db.execute(parse("SELECT id FROM b ORDER BY id;"))
        assert [r[0] for r in a_rows] == [1]
        assert [r[0] for r in b_rows] == [10]
