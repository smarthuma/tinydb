"""T-3.1 tests: lexer — tokenize SQL with (line, col) positions + string literal handling."""
from __future__ import annotations

import pytest

from tinydb.parser.lexer import Token, TokenType, tokenize


class TestBasicTokens:
    def test_keywords_recognized(self) -> None:
        toks = tokenize("CREATE TABLE")
        assert [t.value for t in toks[:2]] == ["CREATE", "TABLE"]
        assert toks[0].type == TokenType.KEYWORD
        assert toks[1].type == TokenType.KEYWORD

    def test_identifiers(self) -> None:
        toks = tokenize("users user_id _priv")
        assert [t.value for t in toks[:3]] == ["users", "user_id", "_priv"]
        assert all(t.type == TokenType.IDENT for t in toks[:3])

    def test_numbers(self) -> None:
        toks = tokenize("42 3.14")
        assert toks[0].type == TokenType.NUMBER and toks[0].value == "42"
        assert toks[1].type == TokenType.NUMBER and toks[1].value == "3.14"

    def test_punctuation(self) -> None:
        toks = tokenize("( ) , ;")
        assert [t.type for t in toks[:4]] == [TokenType.PUNCT] * 4
        assert [t.value for t in toks[:4]] == ["(", ")", ",", ";"]

    def test_operators(self) -> None:
        toks = tokenize("= <> < <= > >=")
        assert all(t.type == TokenType.OPERATOR for t in toks[:6])
        assert [t.value for t in toks[:6]] == ["=", "<>", "<", "<=", ">", ">="]


class TestPositions:
    def test_first_token_line_col(self) -> None:
        toks = tokenize("SELECT")
        assert toks[0].line == 1
        assert toks[0].col == 1

    def test_multiline_positions(self) -> None:
        toks = tokenize("SELECT\n  name")
        # name is on line 2, col 3
        assert toks[1].line == 2
        assert toks[1].col == 3


class TestStringLiterals:
    def test_basic_string(self) -> None:
        toks = tokenize("'hello'")
        assert toks[0].type == TokenType.STRING
        assert toks[0].value == "hello"

    def test_doubled_quote_means_embedded_quote(self) -> None:
        # 'O''Brien' decodes to O'Brien
        toks = tokenize("'O''Brien'")
        assert toks[0].type == TokenType.STRING
        assert toks[0].value == "O'Brien"

    def test_empty_string(self) -> None:
        toks = tokenize("''")
        assert toks[0].type == TokenType.STRING
        assert toks[0].value == ""


class TestEOF:
    def test_eof_token_last(self) -> None:
        toks = tokenize("SELECT 1;")
        assert toks[-1].type == TokenType.EOF

    def test_eof_on_empty_input(self) -> None:
        toks = tokenize("")
        assert len(toks) == 1
        assert toks[0].type == TokenType.EOF


class TestComments:
    def test_line_comment_skipped(self) -> None:
        toks = tokenize("SELECT 1; -- this is a comment\nSELECT 2;")
        # Should get: SELECT, 1, ;, SELECT, 2, ;, EOF
        assert toks[-1].type == TokenType.EOF
        # SELECT appears twice
        assert sum(1 for t in toks if t.value == "SELECT") == 2


class TestDataclass:
    def test_token_is_namedtuple(self) -> None:
        t = Token(TokenType.IDENT, "x", 1, 1)
        assert t.type == TokenType.IDENT
        assert t.value == "x"
        assert t.line == 1
        assert t.col == 1
