"""T-3.4..3.6 tests: DML + predicates + tx-control."""
from __future__ import annotations

from tinydb.parser import ast
from tinydb.parser.parser import parse


class TestInsert:
    def test_single_row(self) -> None:
        stmt = parse("INSERT INTO users VALUES (1, 'alice');")
        assert stmt == ast.Insert(
            table="users",
            values=((ast.Literal(1), ast.Literal("alice")),),
        )

    def test_multi_row(self) -> None:
        stmt = parse("INSERT INTO users VALUES (1, 'a'), (2, 'b');")
        assert stmt == ast.Insert(
            table="users",
            values=(
                (ast.Literal(1), ast.Literal("a")),
                (ast.Literal(2), ast.Literal("b")),
            ),
        )


class TestSelect:
    def test_minimal(self) -> None:
        stmt = parse("SELECT id FROM users;")
        assert stmt == ast.Select(
            columns=(ast.ColumnRef("id"),), table="users",
        )

    def test_where(self) -> None:
        stmt = parse("SELECT id FROM users WHERE id = 1;")
        assert stmt.where == ast.Comparison(
            op="=", left=ast.ColumnRef("id"), right=ast.Literal(1),
        )

    def test_order_by_limit_offset(self) -> None:
        stmt = parse("SELECT id FROM t ORDER BY id DESC LIMIT 10 OFFSET 5;")
        assert stmt.order_by == (ast.OrderByItem(column="id", descending=True),)
        assert stmt.limit == 10
        assert stmt.offset == 5

    def test_multiple_columns(self) -> None:
        stmt = parse("SELECT id, name FROM users;")
        assert stmt.columns == (ast.ColumnRef("id"), ast.ColumnRef("name"))


class TestUpdate:
    def test_with_where(self) -> None:
        stmt = parse("UPDATE users SET name = 'alice' WHERE id = 1;")
        assert stmt == ast.Update(
            table="users",
            assignments=(ast.Assignment(column="name", value=ast.Literal("alice")),),
            where=ast.Comparison(op="=", left=ast.ColumnRef("id"), right=ast.Literal(1)),
        )

    def test_multiple_assignments(self) -> None:
        stmt = parse("UPDATE users SET a = 1, b = 2 WHERE id = 0;")
        assert len(stmt.assignments) == 2


class TestDelete:
    def test_with_where(self) -> None:
        stmt = parse("DELETE FROM users WHERE id = 1;")
        assert stmt == ast.Delete(
            table="users",
            where=ast.Comparison(op="=", left=ast.ColumnRef("id"), right=ast.Literal(1)),
        )

    def test_without_where(self) -> None:
        stmt = parse("DELETE FROM users;")
        assert stmt == ast.Delete(table="users", where=None)


class TestPredicates:
    def test_and_or_precedence(self) -> None:
        # AND binds tighter than OR
        stmt = parse("SELECT * FROM t WHERE a = 1 OR b = 2 AND c = 3;")
        # Expected: OR(EQ(a,1), AND(EQ(b,2), EQ(c,3)))
        assert isinstance(stmt.where, ast.Or)
        assert isinstance(stmt.where.right, ast.And)

    def test_between_as_and(self) -> None:
        stmt = parse("SELECT * FROM t WHERE age BETWEEN 18 AND 65;")
        assert stmt.where == ast.Between(
            expr=ast.ColumnRef("age"),
            lo=ast.Literal(18),
            hi=ast.Literal(65),
        )

    def test_is_null(self) -> None:
        stmt = parse("SELECT * FROM t WHERE x IS NULL;")
        assert stmt.where.op == "IS NULL"

    def test_is_not_null(self) -> None:
        stmt = parse("SELECT * FROM t WHERE x IS NOT NULL;")
        assert stmt.where.op == "IS NOT NULL"

    def test_in_list(self) -> None:
        stmt = parse("SELECT * FROM t WHERE id IN (1, 2, 3);")
        assert stmt.where.expr == ast.ColumnRef("id")
        assert len(stmt.where.values) == 3


class TestTxControl:
    def test_begin(self) -> None:
        assert parse("BEGIN;") == ast.Begin()

    def test_begin_transaction(self) -> None:
        assert parse("BEGIN TRANSACTION;") == ast.Begin()

    def test_commit(self) -> None:
        assert parse("COMMIT;") == ast.Commit()

    def test_end_is_commit(self) -> None:
        assert parse("END;") == ast.Commit()

    def test_rollback(self) -> None:
        assert parse("ROLLBACK;") == ast.Rollback()


class TestParserPurity:
    """T-3.7: two consecutive parses do not share state."""

    def test_two_parses_independent(self) -> None:
        a = parse("SELECT id FROM t;")
        b = parse("SELECT name FROM u;")
        # Different tables/columns — proves the parser instance did not retain state
        assert a.table == "t"
        assert a.columns == (ast.ColumnRef("id"),)
        assert b.table == "u"
        assert b.columns == (ast.ColumnRef("name"),)

    def test_module_level_purity(self) -> None:
        # Calling parse repeatedly at module level does not break
        for i in range(50):
            stmt = parse(f"SELECT {i} FROM t;")
            assert stmt.columns == (ast.Literal(i),)
