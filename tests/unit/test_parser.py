"""T-3.2 + T-3.3 tests: AST dataclasses + DDL parser (CREATE/DROP TABLE)."""
from __future__ import annotations

from tinydb.parser import ast
from tinydb.parser.parser import parse


class TestAstDataclass:
    def test_create_table_equality(self) -> None:
        a = ast.CreateTable(name="t", columns=(ast.ColumnDef("id", "INT", ()),))
        b = ast.CreateTable(name="t", columns=(ast.ColumnDef("id", "INT", ()),))
        assert a == b

    def test_select_equality(self) -> None:
        a = ast.Select(columns=(ast.ColumnRef("x"),), table="t")
        b = ast.Select(columns=(ast.ColumnRef("x"),), table="t")
        assert a == b

    def test_predicate_and_tree(self) -> None:
        # a = 1 AND b = 2
        p = ast.And(
            left=ast.Comparison(op="=", left=ast.ColumnRef("a"), right=ast.Literal(1)),
            right=ast.Comparison(op="=", left=ast.ColumnRef("b"), right=ast.Literal(2)),
        )
        assert isinstance(p, ast.And)


class TestCreateTable:
    def test_minimal(self) -> None:
        stmt = parse("CREATE TABLE users (id INT);")
        assert stmt == ast.CreateTable(
            name="users",
            columns=(ast.ColumnDef("id", "INT", ()),),
        )

    def test_two_columns(self) -> None:
        stmt = parse("CREATE TABLE users (id INT, name TEXT);")
        assert stmt == ast.CreateTable(
            name="users",
            columns=(
                ast.ColumnDef("id", "INT", ()),
                ast.ColumnDef("name", "TEXT", ()),
            ),
        )

    def test_primary_key_constraint(self) -> None:
        stmt = parse("CREATE TABLE users (id INT PRIMARY KEY);")
        assert stmt == ast.CreateTable(
            name="users",
            columns=(ast.ColumnDef("id", "INT", ("PRIMARY KEY",)),),
        )

    def test_not_null_constraint(self) -> None:
        stmt = parse("CREATE TABLE users (name TEXT NOT NULL);")
        assert stmt == ast.CreateTable(
            name="users",
            columns=(ast.ColumnDef("name", "TEXT", ("NOT NULL",)),),
        )

    def test_multiple_constraints(self) -> None:
        stmt = parse("CREATE TABLE users (id INT PRIMARY KEY, name TEXT NOT NULL);")
        assert stmt == ast.CreateTable(
            name="users",
            columns=(
                ast.ColumnDef("id", "INT", ("PRIMARY KEY",)),
                ast.ColumnDef("name", "TEXT", ("NOT NULL",)),
            ),
        )

    def test_unique_constraint(self) -> None:
        stmt = parse("CREATE TABLE users (email TEXT UNIQUE);")
        assert stmt == ast.CreateTable(
            name="users",
            columns=(ast.ColumnDef("email", "TEXT", ("UNIQUE",)),),
        )


class TestDropTable:
    def test_single(self) -> None:
        stmt = parse("DROP TABLE legacy;")
        assert stmt == ast.DropTable(names=("legacy",), if_exists=False)

    def test_if_exists(self) -> None:
        stmt = parse("DROP TABLE IF EXISTS legacy;")
        assert stmt == ast.DropTable(names=("legacy",), if_exists=True)
