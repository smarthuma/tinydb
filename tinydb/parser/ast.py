"""AST dataclasses for tinydb SQL — every Statement / Expr / Predicate node.

Design reference: design.md D7 — frozen dataclasses with __eq__/__repr__
for free, enabling trivial parser tests and executor tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union

# === Predicates (WHERE clauses) ============================================


@dataclass(frozen=True)
class ColumnRef:
    name: str


@dataclass(frozen=True)
class Literal:
    value: Union[int, float, str, bool, None]


@dataclass(frozen=True)
class BinaryOp:
    op: str  # '+', '-', etc.
    left: "Expr"
    right: "Expr"


Expr = Union[ColumnRef, Literal, BinaryOp]


@dataclass(frozen=True)
class Comparison:
    op: str  # '=', '<>', '<', '<=', '>', '>=', 'IS NULL', 'IS NOT NULL', ...
    left: Expr
    right: Expr  # ignored for IS NULL


@dataclass(frozen=True)
class Between:
    expr: Expr
    lo: Expr
    hi: Expr


@dataclass(frozen=True)
class InList:
    expr: Expr
    values: tuple[Expr, ...]


@dataclass(frozen=True)
class And:
    left: "Predicate"
    right: "Predicate"


@dataclass(frozen=True)
class Or:
    left: "Predicate"
    right: "Predicate"


@dataclass(frozen=True)
class Not:
    inner: "Predicate"


Predicate = Union[Comparison, Between, InList, And, Or, Not]


# === Statements ============================================================


@dataclass(frozen=True)
class ColumnDef:
    name: str
    type_name: str  # 'INT' | 'FLOAT' | 'TEXT' | 'BOOL'
    constraints: tuple[str, ...]  # ('PRIMARY KEY', 'NOT NULL', 'UNIQUE')


@dataclass(frozen=True)
class CreateTable:
    name: str
    columns: tuple[ColumnDef, ...]
    if_not_exists: bool = False


@dataclass(frozen=True)
class DropTable:
    names: tuple[str, ...]
    if_exists: bool = False


@dataclass(frozen=True)
class CreateIndex:
    name: str
    table: str
    column: str
    unique: bool = False
    if_not_exists: bool = False


@dataclass(frozen=True)
class DropIndex:
    name: str
    if_exists: bool = False


@dataclass(frozen=True)
class Insert:
    table: str
    values: tuple[tuple[Expr, ...], ...]  # rows of expressions


@dataclass(frozen=True)
class OrderByItem:
    column: str
    descending: bool = False


@dataclass(frozen=True)
class Select:
    columns: tuple[Expr, ...]
    table: str
    where: Predicate | None = None
    order_by: tuple[OrderByItem, ...] = ()
    limit: int | None = None
    offset: int | None = None
    group_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class Assignment:
    column: str
    value: Expr


@dataclass(frozen=True)
class Update:
    table: str
    assignments: tuple[Assignment, ...]
    where: Predicate | None = None


@dataclass(frozen=True)
class Delete:
    table: str
    where: Predicate | None = None


@dataclass(frozen=True)
class Begin:
    pass


@dataclass(frozen=True)
class Commit:
    pass


@dataclass(frozen=True)
class Rollback:
    pass


@dataclass(frozen=True)
class Checkpoint:
    pass


Statement = Union[
    CreateTable, DropTable, Insert, Select, Update, Delete,
    Begin, Commit, Rollback, Checkpoint,
]
