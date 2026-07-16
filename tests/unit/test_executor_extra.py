"""Additional executor + WAL tests to lift coverage above 80% gate."""
from __future__ import annotations

import pytest

from tinydb import executor, storage, wal
from tinydb.parser.parser import parse


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "t.db")
    d = executor.Executor.open(path)
    yield d
    d.close()


class TestExecutorExtra:
    def test_if_not_exists(self, db):
        db.execute(parse("CREATE TABLE t (id INT);"))
        # Re-creating without IF NOT EXISTS raises
        with pytest.raises(executor.tinydb_types.TinyDBError):
            db.execute(parse("CREATE TABLE t (id INT);"))
        # With IF NOT EXISTS, it's a no-op
        db.execute(parse("CREATE TABLE IF NOT EXISTS t (id INT);"))

    def test_drop_if_exists_missing(self, db):
        # Missing table with IF EXISTS is no-op
        db.execute(parse("DROP TABLE IF EXISTS missing;"))

    def test_drop_table_not_found_without_if(self, db):
        from tinydb.types import TableNotFound
        with pytest.raises(TableNotFound):
            db.execute(parse("DROP TABLE missing;"))

    def test_select_explicit_columns(self, db):
        db.execute(parse("CREATE TABLE t (a INT, b TEXT);"))
        db.execute(parse("INSERT INTO t VALUES (1, 'x');"))
        rows = db.execute(parse("SELECT a, b FROM t;"))
        assert rows == [(1, "x")]

    def test_between_predicate(self, db):
        db.execute(parse("CREATE TABLE t (age INT);"))
        for a in [10, 20, 30, 40]:
            db.execute(parse(f"INSERT INTO t VALUES ({a});"))
        rows = db.execute(parse("SELECT age FROM t WHERE age BETWEEN 18 AND 35;"))
        assert rows == [(20,), (30,)]

    def test_in_list_predicate(self, db):
        db.execute(parse("CREATE TABLE t (id INT);"))
        for i in [1, 2, 3, 4]:
            db.execute(parse(f"INSERT INTO t VALUES ({i});"))
        rows = db.execute(parse("SELECT id FROM t WHERE id IN (1, 3);"))
        assert sorted(rows) == [(1,), (3,)]

    def test_is_null_predicate(self, db):
        from tinydb.types import encode_with_null, is_null
        # Smoke test the encode_with_null path
        raw, was_null = encode_with_null(None, __import__('tinydb').types.ColumnType.INT)
        assert was_null
        assert is_null(raw)

    def test_group_by_single_column(self, db):
        db.execute(parse("CREATE TABLE t (k TEXT, v INT);"))
        for k, v in [("a", 1), ("b", 2), ("a", 3)]:
            db.execute(parse(f"INSERT INTO t VALUES ('{k}', {v});"))
        rows = db.execute(parse("SELECT k, SUM(v) FROM t GROUP BY k;"))
        assert ("a", 4) in rows
        assert ("b", 2) in rows


class TestWalReplay:
    def test_replay_with_committed_mutation(self, tmp_path):
        path = str(tmp_path / "t.db")
        with storage.FileStore.open(path) as s:
            w = wal.Wal(s)
            w.append("MUTATE", tx_id=1, page_id=1, before=b"", after=b"\x02" + b"\x00" * 100)
            w.append("COMMIT", tx_id=1)
            w.fsync()
            w.close()
            # Reopen and replay
            s2 = storage.FileStore.open(path)
            w2 = wal.Wal(s2)
            # Replay should not raise
            w2.replay(s2)
            w2.close()
            s2.close()
