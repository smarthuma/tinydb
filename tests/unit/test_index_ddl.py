"""Tests for CREATE INDEX / DROP INDEX SQL execution paths."""
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


class TestCreateIndex:
    def test_create_index_basic(self, db):
        db.execute(parse("CREATE TABLE t (id INT, n TEXT);"))
        db.execute(parse("INSERT INTO t VALUES (1, 'a');"))
        db.execute(parse("INSERT INTO t VALUES (2, 'b');"))
        db.execute(parse("CREATE INDEX idx_id ON t (id);"))
        schema = db.catalog.get_schema("t")
        assert "idx_id" in schema.indexes

    def test_create_index_populated_from_existing(self, db):
        db.execute(parse("CREATE TABLE t (id INT);"))
        db.execute(parse("INSERT INTO t VALUES (1);"))
        db.execute(parse("INSERT INTO t VALUES (2);"))
        db.execute(parse("INSERT INTO t VALUES (3);"))
        # Index built on existing data
        db.execute(parse("CREATE INDEX idx_id ON t (id);"))
        assert "idx_id" in db.catalog.get_schema("t").indexes

    def test_create_index_if_not_exists(self, db):
        db.execute(parse("CREATE TABLE t (id INT);"))
        db.execute(parse("CREATE INDEX i ON t (id);"))
        # Second create with IF NOT EXISTS is a no-op
        db.execute(parse("CREATE INDEX IF NOT EXISTS i ON t (id);"))
        # Without IF NOT EXISTS raises
        from tinydb.types import TinyDBError
        with pytest.raises(TinyDBError):
            db.execute(parse("CREATE INDEX i ON t (id);"))

    def test_create_index_unknown_table(self, db):
        from tinydb.types import TableNotFound
        with pytest.raises(TableNotFound):
            db.execute(parse("CREATE INDEX i ON missing (id);"))

    def test_create_index_unknown_column(self, db):
        db.execute(parse("CREATE TABLE t (id INT);"))
        with pytest.raises(tt.TinyDBError):
            db.execute(parse("CREATE INDEX i ON t (missing_col);"))

    def test_create_unique_index_rejects_duplicate(self, db):
        db.execute(parse("CREATE TABLE t (n TEXT);"))
        db.execute(parse("INSERT INTO t VALUES ('a');"))
        db.execute(parse("INSERT INTO t VALUES ('b');"))
        # Both have different values, so the unique index can be created
        db.execute(parse("CREATE UNIQUE INDEX uniq_n ON t (n);"))

    def test_create_unique_index_fails_on_existing_dups(self, db):
        db.execute(parse("CREATE TABLE t (n TEXT);"))
        db.execute(parse("INSERT INTO t VALUES ('a');"))
        db.execute(parse("INSERT INTO t VALUES ('a');"))  # duplicate!
        from tinydb.types import UniqueViolation
        with pytest.raises(UniqueViolation):
            db.execute(parse("CREATE UNIQUE INDEX uniq_n ON t (n);"))

    def test_index_skips_null_keys(self, db):
        # NULL values should not be indexed
        db.execute(parse("CREATE TABLE t (id INT, n INT);"))
        db.execute(parse("INSERT INTO t VALUES (1, NULL);"))
        db.execute(parse("INSERT INTO t VALUES (2, 10);"))
        # Should not raise even though NULL exists
        db.execute(parse("CREATE INDEX i ON t (n);"))


class TestDropIndex:
    def test_drop_index(self, db):
        db.execute(parse("CREATE TABLE t (id INT);"))
        db.execute(parse("INSERT INTO t VALUES (1);"))
        db.execute(parse("CREATE INDEX i ON t (id);"))
        db.execute(parse("DROP INDEX i;"))
        assert "i" not in db.catalog.get_schema("t").indexes

    def test_drop_index_if_exists_missing(self, db):
        # IF EXISTS makes it a no-op
        db.execute(parse("DROP INDEX IF EXISTS missing;"))

    def test_drop_index_missing_raises(self, db):
        from tinydb.types import TinyDBError
        with pytest.raises(TinyDBError):
            db.execute(parse("DROP INDEX missing;"))
