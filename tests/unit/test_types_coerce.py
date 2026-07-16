"""T-1.4 tests: coerce_in rules, NULL handling, NULL encoding round-trip."""
from __future__ import annotations

import pytest

from tinydb import types


class TestCoerceIn:
    """REQ-TS-006: INT accepts bool; all other cross-types rejected."""

    def test_int_accepts_int(self) -> None:
        assert types.coerce_in(42, types.ColumnType.INT, "col") == 42

    def test_int_accepts_true(self) -> None:
        assert types.coerce_in(True, types.ColumnType.INT, "col") == 1

    def test_int_accepts_false(self) -> None:
        assert types.coerce_in(False, types.ColumnType.INT, "col") == 0

    def test_int_rejects_str(self) -> None:
        with pytest.raises(types.TypeMismatch) as exc:
            types.coerce_in("not an int", types.ColumnType.INT, "col")
        assert exc.value.column == "col"
        assert exc.value.expected == "INT"
        assert exc.value.got == "str"

    def test_int_rejects_float(self) -> None:
        with pytest.raises(types.TypeMismatch):
            types.coerce_in(1.5, types.ColumnType.INT, "col")

    def test_text_accepts_str(self) -> None:
        assert types.coerce_in("hi", types.ColumnType.TEXT, "col") == "hi"

    def test_text_rejects_int(self) -> None:
        with pytest.raises(types.TypeMismatch) as exc:
            types.coerce_in(42, types.ColumnType.TEXT, "col")
        assert exc.value.expected == "TEXT"
        assert exc.value.got == "int"

    def test_bool_accepts_bool(self) -> None:
        assert types.coerce_in(True, types.ColumnType.BOOL, "col") is True
        assert types.coerce_in(False, types.ColumnType.BOOL, "col") is False

    def test_bool_rejects_int_0(self) -> None:
        with pytest.raises(types.TypeMismatch) as exc:
            types.coerce_in(0, types.ColumnType.BOOL, "col")
        assert exc.value.expected == "BOOL"
        assert exc.value.got == "int"

    def test_bool_rejects_int_1(self) -> None:
        with pytest.raises(types.TypeMismatch):
            types.coerce_in(1, types.ColumnType.BOOL, "col")

    def test_float_accepts_float(self) -> None:
        assert types.coerce_in(3.14, types.ColumnType.FLOAT, "col") == 3.14

    def test_float_rejects_int(self) -> None:
        # strict: int != float, must reject
        with pytest.raises(types.TypeMismatch):
            types.coerce_in(42, types.ColumnType.FLOAT, "col")


class TestNullEncoding:
    """REQ-TS-005: NULL round-trip via Python None."""

    def test_encode_none(self) -> None:
        assert types.encode_none() == b"\x00"

    def test_decode_none_marker(self) -> None:
        assert types.is_null(b"\x00") is True

    def test_decode_non_null(self) -> None:
        assert types.is_null(b"\x01") is False
        assert types.is_null(b"hello") is False

    def test_null_roundtrip(self) -> None:
        # user code path: encode(value, type) returns encoded bytes + a null marker
        encoded, is_null = types.encode_with_null("hi", types.ColumnType.TEXT)
        assert is_null is False
        assert types.decode_with_null(encoded, is_null, types.ColumnType.TEXT) == "hi"

    def test_actual_null_roundtrip(self) -> None:
        encoded, is_null = types.encode_with_null(None, types.ColumnType.INT)
        assert is_null is True
        assert types.decode_with_null(encoded, is_null, types.ColumnType.INT) is None


class TestExceptionHierarchy:
    """D8: single base TinyDBError + concrete subclasses."""

    def test_all_inherit_from_tinydb_error(self) -> None:
        for cls in (
            types.ParseError,
            types.TypeMismatch,
            types.IntegerOverflow,
            types.NotNullViolation,
            types.UniqueViolation,
        ):
            assert issubclass(cls, types.TinyDBError)

    def test_catch_via_base(self) -> None:
        try:
            raise types.TypeMismatch("c", "INT", "str")
        except types.TinyDBError as e:
            assert e.column == "c"
