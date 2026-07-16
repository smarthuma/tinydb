"""Recursive-descent parser for tinydb SQL.

Public entry point: `parse(sql: str) -> Statement`
"""
from __future__ import annotations

from tinydb.parser.ast import (
    And,
    Assignment,
    Begin,
    Between,
    BinaryOp,
    Checkpoint,
    ColumnDef,
    ColumnRef,
    Commit,
    Comparison,
    CreateTable,
    Delete,
    DropTable,
    Expr,
    InList,
    Insert,
    Literal,
    Not,
    OrderByItem,
    Or,
    Predicate,
    Rollback,
    Select,
    Update,
)
from tinydb.parser.lexer import Token, TokenType, tokenize
from tinydb.types import ParseError

_TYPE_NAMES = frozenset({"INT", "FLOAT", "TEXT", "BOOL"})


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self, offset: int = 0) -> Token:
        return self.tokens[self.pos + offset]

    def advance(self) -> Token:
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def at_end(self) -> bool:
        return self.peek().type is TokenType.EOF

    def expect_keyword(self, kw: str) -> Token:
        t = self.peek()
        if t.type is TokenType.KEYWORD and t.value.upper() == kw:
            return self.advance()
        raise ParseError(f"expected keyword {kw}", t.line, t.col)

    def expect_punct(self, p: str) -> Token:
        t = self.peek()
        if t.type is TokenType.PUNCT and t.value == p:
            return self.advance()
        raise ParseError(f"expected '{p}'", t.line, t.col)

    def expect_operator(self, op: str) -> Token:
        t = self.peek()
        if t.type is TokenType.OPERATOR and t.value == op:
            return self.advance()
        raise ParseError(f"expected operator '{op}'", t.line, t.col)

    def match_keyword(self, kw: str) -> Token | None:
        t = self.peek()
        if t.type is TokenType.KEYWORD and t.value.upper() == kw:
            return self.advance()
        return None

    def match_punct(self, p: str) -> Token | None:
        t = self.peek()
        if t.type is TokenType.PUNCT and t.value == p:
            return self.advance()
        return None

    def parse_statement(self) -> object:
        t = self.peek()
        if t.type is TokenType.KEYWORD:
            kw = t.value.upper()
            if kw == "CREATE":
                return self._parse_create_table()
            if kw == "DROP":
                return self._parse_drop_table()
            if kw == "INSERT":
                return self._parse_insert()
            if kw == "SELECT":
                return self._parse_select()
            if kw == "UPDATE":
                return self._parse_update()
            if kw == "DELETE":
                return self._parse_delete()
            if kw in {"BEGIN", "COMMIT", "END", "ROLLBACK", "CHECKPOINT"}:
                return self._parse_tx_control()
        raise ParseError(f"unexpected token {t.value!r}", t.line, t.col)

    # === DDL ================================================================

    def _parse_create_table(self) -> CreateTable:
        self.expect_keyword("CREATE")
        self.expect_keyword("TABLE")
        if_not_exists = self.match_keyword("IF") is not None
        if if_not_exists:
            self.expect_keyword("NOT")
            self.expect_keyword("EXISTS")
        name = self._parse_ident()
        self.expect_punct("(")
        columns = [self._parse_column_def()]
        while self.match_punct(","):
            columns.append(self._parse_column_def())
        self.expect_punct(")")
        self.expect_punct(";")
        return CreateTable(name=name, columns=tuple(columns), if_not_exists=if_not_exists)

    def _parse_column_def(self) -> ColumnDef:
        col_name = self._parse_ident()
        type_tok = self.advance()
        if type_tok.type is not TokenType.KEYWORD or type_tok.value.upper() not in _TYPE_NAMES:
            raise ParseError(f"expected type name, got {type_tok.value!r}", type_tok.line, type_tok.col)
        type_name = type_tok.value.upper()
        constraints: list[str] = []
        while True:
            t = self.peek()
            if t.type is TokenType.KEYWORD and t.value.upper() in {"PRIMARY", "NOT", "UNIQUE"}:
                upper = t.value.upper()
                if upper == "PRIMARY":
                    self.advance()
                    self.expect_keyword("KEY")
                    constraints.append("PRIMARY KEY")
                elif upper == "NOT":
                    self.advance()
                    self.expect_keyword("NULL")
                    constraints.append("NOT NULL")
                elif upper == "UNIQUE":
                    self.advance()
                    constraints.append("UNIQUE")
            else:
                break
        return ColumnDef(name=col_name, type_name=type_name, constraints=tuple(constraints))

    def _parse_drop_table(self) -> DropTable:
        self.expect_keyword("DROP")
        self.expect_keyword("TABLE")
        if_exists = self.match_keyword("IF") is not None
        if if_exists:
            self.expect_keyword("EXISTS")
        names = [self._parse_ident()]
        while self.match_punct(","):
            names.append(self._parse_ident())
        self.expect_punct(";")
        return DropTable(names=tuple(names), if_exists=if_exists)

    # === DML — INSERT / SELECT / UPDATE / DELETE ===========================

    def _parse_insert(self) -> Insert:
        self.expect_keyword("INSERT")
        self.expect_keyword("INTO")
        table = self._parse_ident()
        self.expect_keyword("VALUES")
        rows: list[tuple[Expr, ...]] = []
        rows.append(self._parse_value_row())
        while self.match_punct(","):
            rows.append(self._parse_value_row())
        self.expect_punct(";")
        return Insert(table=table, values=tuple(rows))

    def _parse_value_row(self) -> tuple[Expr, ...]:
        self.expect_punct("(")
        values = [self._parse_expr()]
        while self.match_punct(","):
            values.append(self._parse_expr())
        self.expect_punct(")")
        return tuple(values)

    def _parse_select(self) -> Select:
        self.expect_keyword("SELECT")
        columns = self._parse_projection_list()
        self.expect_keyword("FROM")
        table = self._parse_ident()
        where = None
        if self.match_keyword("WHERE"):
            where = self._parse_predicate()
        group_by: tuple[str, ...] = ()
        if self.match_keyword("GROUP"):
            self.expect_keyword("BY")
            group_by = (self._parse_ident(),)
            while self.match_punct(","):
                group_by = group_by + (self._parse_ident(),)
        order_by: tuple[OrderByItem, ...] = ()
        if self.match_keyword("ORDER"):
            self.expect_keyword("BY")
            items = [self._parse_order_item()]
            while self.match_punct(","):
                items.append(self._parse_order_item())
            order_by = tuple(items)
        limit = None
        offset = None
        if self.match_keyword("LIMIT"):
            limit = self._parse_int_literal()
            if self.match_keyword("OFFSET"):
                offset = self._parse_int_literal()
        elif self.match_keyword("OFFSET"):
            offset = self._parse_int_literal()
        self.expect_punct(";")
        return Select(
            columns=columns, table=table, where=where,
            order_by=order_by, limit=limit, offset=offset, group_by=group_by,
        )

    def _parse_projection_list(self) -> tuple[Expr, ...]:
        if self.match_operator("*"):
            return (ColumnRef("*"),)
        cols = [self._parse_projection_item()]
        while self.match_punct(","):
            cols.append(self._parse_projection_item())
        return tuple(cols)

    def _parse_projection_item(self) -> Expr:
        t = self.peek()
        if t.type is TokenType.KEYWORD and t.value.upper() in {"COUNT", "SUM", "AVG"}:
            agg = self.advance().value.upper()
            self.expect_punct("(")
            if self.match_operator("*"):
                self.expect_punct(")")
                return Literal(value=f"{agg}:*")
            inner = self._parse_expr()
            self.expect_punct(")")
            # Sentinel: "{agg}:{column_name}" — executor extracts via split(':', 1)
            from tinydb.parser.ast import ColumnRef
            col_name = inner.name if isinstance(inner, ColumnRef) else "?"
            return Literal(value=f"{agg}:{col_name}")
        return self._parse_expr()

    def _parse_order_item(self) -> OrderByItem:
        col = self._parse_ident()
        desc = False
        if self.match_keyword("ASC"):
            pass
        elif self.match_keyword("DESC"):
            desc = True
        return OrderByItem(column=col, descending=desc)

    def _parse_update(self) -> Update:
        self.expect_keyword("UPDATE")
        table = self._parse_ident()
        self.expect_keyword("SET")
        assignments = [self._parse_assignment()]
        while self.match_punct(","):
            assignments.append(self._parse_assignment())
        where = None
        if self.match_keyword("WHERE"):
            where = self._parse_predicate()
        self.expect_punct(";")
        return Update(table=table, assignments=tuple(assignments), where=where)

    def _parse_assignment(self) -> Assignment:
        col = self._parse_ident()
        self.expect_operator("=")
        return Assignment(column=col, value=self._parse_expr())

    def _parse_delete(self) -> Delete:
        self.expect_keyword("DELETE")
        self.expect_keyword("FROM")
        table = self._parse_ident()
        where = None
        if self.match_keyword("WHERE"):
            where = self._parse_predicate()
        self.expect_punct(";")
        return Delete(table=table, where=where)

    # === TX control ========================================================

    def _parse_tx_control(self) -> object:
        kw = self.advance().value.upper()
        if kw in {"BEGIN", "COMMIT", "END", "ROLLBACK"}:
            if kw in {"BEGIN", "COMMIT", "END"}:
                # optional TRANSACTION after BEGIN
                if kw == "BEGIN":
                    self.match_keyword("TRANSACTION")
                self.expect_punct(";")
                if kw == "BEGIN":
                    return Begin()
                if kw == "COMMIT" or kw == "END":
                    return Commit()
            else:  # ROLLBACK
                self.expect_punct(";")
                return Rollback()
        if kw == "CHECKPOINT":
            self.expect_punct(";")
            return Checkpoint()
        # Unreachable
        raise ParseError(f"unknown tx control {kw}", 0, 0)

    # === Predicates ========================================================

    def _parse_predicate(self) -> Predicate:
        return self._parse_or()

    def _parse_or(self) -> Predicate:
        left = self._parse_and()
        while self.match_keyword("OR"):
            right = self._parse_and()
            left = Or(left=left, right=right)
        return left

    def _parse_and(self) -> Predicate:
        left = self._parse_atom_predicate()
        while self.match_keyword("AND"):
            right = self._parse_atom_predicate()
            left = And(left=left, right=right)
        return left

    def _parse_atom_predicate(self) -> Predicate:
        # parenthesized
        if self.match_punct("("):
            p = self._parse_predicate()
            self.expect_punct(")")
            return p
        left = self._parse_expr()
        # IS [NOT] NULL
        if self.peek_keyword("IS"):
            self.advance()
            negated = self.match_keyword("NOT") is not None
            self.expect_keyword("NULL")
            op = "IS NOT NULL" if negated else "IS NULL"
            return Comparison(op=op, left=left, right=left)  # right ignored
        # NOT IN
        if self.peek_keyword("NOT"):
            self.advance()
            self.expect_keyword("IN")
            self.expect_punct("(")
            values = self._parse_expr_list()
            self.expect_punct(")")
            return Not(inner=InList(expr=left, values=tuple(values)))
        # IN
        if self.match_keyword("IN"):
            self.expect_punct("(")
            values = self._parse_expr_list()
            self.expect_punct(")")
            return InList(expr=left, values=tuple(values))
        # BETWEEN a AND b
        if self.match_keyword("BETWEEN"):
            lo = self._parse_expr()
            self.expect_keyword("AND")
            hi = self._parse_expr()
            return Between(expr=left, lo=lo, hi=hi)
        # standard comparison
        op_tok = self.advance()
        if op_tok.type is not TokenType.OPERATOR:
            raise ParseError(f"expected comparison operator, got {op_tok.value!r}", op_tok.line, op_tok.col)
        right = self._parse_expr()
        return Comparison(op=op_tok.value, left=left, right=right)

    def _parse_expr_list(self) -> list[Expr]:
        items = [self._parse_expr()]
        while self.match_punct(","):
            items.append(self._parse_expr())
        return items

    def peek_keyword(self, kw: str) -> bool:
        t = self.peek()
        return t.type is TokenType.KEYWORD and t.value.upper() == kw

    def match_operator(self, op: str) -> Token | None:
        t = self.peek()
        if t.type is TokenType.OPERATOR and t.value == op:
            return self.advance()
        return None

    # === Expressions =======================================================

    def _parse_expr(self) -> Expr:
        return self._parse_additive()

    def _parse_additive(self) -> Expr:
        left = self._parse_primary()
        while self.peek().type is TokenType.OPERATOR and self.peek().value in {"+", "-"}:
            op = self.advance().value
            right = self._parse_primary()
            left = BinaryOp(op=op, left=left, right=right)
        return left

    def _parse_primary(self) -> Expr:
        t = self.peek()
        if t.type is TokenType.NUMBER:
            self.advance()
            raw = t.value
            if "." in raw:
                return Literal(value=float(raw))
            return Literal(value=int(raw))
        if t.type is TokenType.STRING:
            self.advance()
            return Literal(value=t.value)
        if t.type is TokenType.KEYWORD and t.value.upper() == "NULL":
            self.advance()
            return Literal(value=None)
        if t.type is TokenType.KEYWORD and t.value.upper() == "TRUE":
            self.advance()
            return Literal(value=True)
        if t.type is TokenType.KEYWORD and t.value.upper() == "FALSE":
            self.advance()
            return Literal(value=False)
        if t.type is TokenType.IDENT:
            self.advance()
            return ColumnRef(name=t.value)
        if self.match_punct("("):
            inner = self._parse_expr()
            self.expect_punct(")")
            return inner
        raise ParseError(f"expected expression, got {t.value!r}", t.line, t.col)

    # === Identifiers =======================================================

    def _parse_ident(self) -> str:
        t = self.advance()
        if t.type is not TokenType.IDENT:
            raise ParseError(f"expected identifier, got {t.value!r}", t.line, t.col)
        return t.value

    def _parse_int_literal(self) -> int:
        t = self.advance()
        if t.type is not TokenType.NUMBER or "." in t.value:
            raise ParseError(f"expected integer literal, got {t.value!r}", t.line, t.col)
        return int(t.value)


def parse(sql: str) -> object:
    """Parse a single SQL statement into an AST. Raises ParseError on failure."""
    tokens = tokenize(sql)
    parser = _Parser(tokens)
    stmt = parser.parse_statement()
    return stmt
