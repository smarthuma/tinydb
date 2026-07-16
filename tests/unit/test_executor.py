"""T-5.1..T-5.7 tests: catalog + heap + DML + WHERE + UPDATE/DELETE + ORDER BY + aggregates."""
from __future__ import annotations

import pytest

from tinydb import executor
from tinydb.parser.parser import parse
from tinydb import storage


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "t.db")
    d = executor.Executor.open(path)
    yield d
    d.close()


class TestCatalog:
    def test_create_then_get_table(self, db):
        db.execute(parse("CREATE TABLE users (id INT PRIMARY KEY, name TEXT);"))
        schema = db.catalog.get_schema("users")
        assert schema is not None
        assert schema.columns[0].name == "id"

    def test_drop_removes_table(self, db):
        db.execute(parse("CREATE TABLE t (id INT);"))
        db.execute(parse("DROP TABLE t;"))
        assert db.catalog.get_schema("t") is None


class TestInsert:
    def test_insert_and_select(self, db):
        db.execute(parse("CREATE TABLE users (id INT, name TEXT);"))
        db.execute(parse("INSERT INTO users VALUES (1, 'alice');"))
        rows = db.execute(parse("SELECT id, name FROM users;"))
        assert len(rows) == 1
        assert rows[0] == (1, "alice")

    def test_type_mismatch_rejected(self, db):
        from tinydb.types import TypeMismatch
        db.execute(parse("CREATE TABLE t (age INT);"))
        with pytest.raises(TypeMismatch):
            db.execute(parse("INSERT INTO t VALUES ('alice');"))

    def test_not_null_violation(self, db):
        from tinydb.types import NotNullViolation
        db.execute(parse("CREATE TABLE t (name TEXT NOT NULL);"))
        with pytest.raises(NotNullViolation):
            db.execute(parse("INSERT INTO t VALUES (NULL);"))

    def test_primary_key_unique(self, db):
        from tinydb.types import UniqueViolation
        db.execute(parse("CREATE TABLE t (id INT PRIMARY KEY);"))
        db.execute(parse("INSERT INTO t VALUES (1);"))
        with pytest.raises(UniqueViolation):
            db.execute(parse("INSERT INTO t VALUES (1);"))


class TestSelectWhere:
    def test_compound_predicate(self, db):
        db.execute(parse("CREATE TABLE t (id INT, name TEXT);"))
        db.execute(parse("INSERT INTO t VALUES (1, 'A');"))
        db.execute(parse("INSERT INTO t VALUES (2, 'B');"))
        db.execute(parse("INSERT INTO t VALUES (3, 'C');"))
        rows = db.execute(parse("SELECT id FROM t WHERE id >= 2 AND name = 'B';"))
        assert rows == [(2,)]

    def test_order_by_desc(self, db):
        db.execute(parse("CREATE TABLE t (id INT);"))
        for i in [1, 3, 2]:
            db.execute(parse(f"INSERT INTO t VALUES ({i});"))
        rows = db.execute(parse("SELECT id FROM t ORDER BY id DESC;"))
        assert rows == [(3,), (2,), (1,)]

    def test_limit_offset(self, db):
        db.execute(parse("CREATE TABLE t (id INT);"))
        for i in range(1, 11):
            db.execute(parse(f"INSERT INTO t VALUES ({i});"))
        rows = db.execute(parse("SELECT id FROM t ORDER BY id LIMIT 3 OFFSET 2;"))
        assert rows == [(3,), (4,), (5,)]


class TestUpdateDelete:
    def test_update_only_matching(self, db):
        db.execute(parse("CREATE TABLE t (id INT, name TEXT);"))
        db.execute(parse("INSERT INTO t VALUES (1, 'A');"))
        db.execute(parse("INSERT INTO t VALUES (2, 'B');"))
        db.execute(parse("INSERT INTO t VALUES (3, 'A');"))
        n = db.execute(parse("UPDATE t SET name = 'X' WHERE name = 'A';"))
        assert n == 2
        rows = db.execute(parse("SELECT name FROM t ORDER BY id;"))
        assert rows == [("X",), ("B",), ("X",)]

    def test_delete_without_where_rejected(self, db):
        from tinydb.types import UnsafeDeleteWithoutWhere
        db.execute(parse("CREATE TABLE t (id INT);"))
        with pytest.raises(UnsafeDeleteWithoutWhere):
            db.execute(parse("DELETE FROM t;"))


class TestAggregates:
    def test_count_star(self, db):
        db.execute(parse("CREATE TABLE t (id INT);"))
        for i in range(7):
            db.execute(parse(f"INSERT INTO t VALUES ({i});"))
        rows = db.execute(parse("SELECT COUNT(*) FROM t;"))
        assert rows == [(7,)]

    def test_group_by_sum(self, db):
        db.execute(parse("CREATE TABLE t (dept TEXT, amount INT);"))
        for d, a in [("A", 1), ("B", 2), ("A", 3)]:
            db.execute(parse(f"INSERT INTO t VALUES ('{d}', {a});"))
        rows = db.execute(parse("SELECT dept, SUM(amount) FROM t GROUP BY dept;"))
        # Ordered by dept
        assert rows == [("A", 4), ("B", 2)]
