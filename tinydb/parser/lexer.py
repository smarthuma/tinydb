"""Lexer for tinydb SQL.

Supports: keywords, identifiers, integers, floats, single-quoted strings
(doubled '' = embedded quote), punctuation, operators, line comments.
Tracks 1-based (line, col) positions. Single module, no external deps.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TokenType(str, Enum):
    KEYWORD = "KEYWORD"
    IDENT = "IDENT"
    NUMBER = "NUMBER"
    STRING = "STRING"
    OPERATOR = "OPERATOR"
    PUNCT = "PUNCT"
    EOF = "EOF"


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str
    line: int
    col: int


KEYWORDS = frozenset({
    "CREATE", "TABLE", "DROP", "IF", "EXISTS", "INSERT", "INTO", "VALUES",
    "SELECT", "FROM", "WHERE", "UPDATE", "SET", "DELETE", "ORDER", "BY",
    "ASC", "DESC", "LIMIT", "OFFSET", "GROUP", "PRIMARY", "KEY", "NOT",
    "NULL", "UNIQUE", "AND", "OR", "IS", "BETWEEN", "IN", "AS", "INT",
    "FLOAT", "TEXT", "BOOL", "BEGIN", "TRANSACTION", "COMMIT", "END",
    "ROLLBACK", "TRUE", "FALSE", "CHECKPOINT",
})

# Single-character punctuation
PUNCT_CHARS = frozenset("(),;.[]")

# Operators (sorted longest first for greedy match)
OPERATORS = (
    "<=", ">=", "<>", "!=",
    "<", ">", "=", "+", "-", "*", "/",
)


def tokenize(sql: str) -> list[Token]:
    """Lex `sql` into a list of tokens, ending with EOF."""
    tokens: list[Token] = []
    line = 1
    col = 1
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        # Whitespace
        if ch in " \t\r":
            i += 1
            col += 1
            continue
        if ch == "\n":
            i += 1
            line += 1
            col = 1
            continue
        # Line comment
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            j = sql.find("\n", i)
            if j == -1:
                break  # comment to end of input
            i = j
            continue
        # String literal
        if ch == "'":
            start_line, start_col = line, col
            j = i + 1
            buf: list[str] = []
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        buf.append("'")
                        j += 2
                        col += 2
                        continue
                    # end of string
                    j += 1
                    col += 1
                    tokens.append(Token(TokenType.STRING, "".join(buf), start_line, start_col))
                    break
                if sql[j] == "\n":
                    line += 1
                    col = 1
                else:
                    col += 1
                buf.append(sql[j])
                j += 1
            else:
                raise ValueError(f"unterminated string literal at line {start_line}, col {start_col}")
            i = j
            continue
        # Punctuation
        if ch in PUNCT_CHARS:
            tokens.append(Token(TokenType.PUNCT, ch, line, col))
            i += 1
            col += 1
            continue
        # Operator (greedy)
        matched_op = False
        for op in OPERATORS:
            if sql.startswith(op, i):
                tokens.append(Token(TokenType.OPERATOR, op, line, col))
                i += len(op)
                col += len(op)
                matched_op = True
                break
        if matched_op:
            continue
        # Number
        if ch.isdigit() or (ch == "." and i + 1 < n and sql[i + 1].isdigit()):
            start_line, start_col = line, col
            j = i
            seen_dot = False
            while j < n and (sql[j].isdigit() or (sql[j] == "." and not seen_dot)):
                if sql[j] == ".":
                    seen_dot = True
                j += 1
                col += 1
            tokens.append(Token(TokenType.NUMBER, sql[i:j], start_line, start_col))
            i = j
            continue
        # Identifier / keyword
        if ch.isalpha() or ch == "_":
            start_line, start_col = line, col
            j = i
            while j < n and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
                col += 1
            word = sql[i:j]
            ttype = TokenType.KEYWORD if word.upper() in KEYWORDS else TokenType.IDENT
            tokens.append(Token(ttype, word, start_line, start_col))
            i = j
            continue
        # Unknown character
        raise ValueError(f"unexpected character {ch!r} at line {line}, col {col}")
    tokens.append(Token(TokenType.EOF, "", line, col))
    return tokens
