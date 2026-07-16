"""T-1.3 tests for FLOAT / TEXT / BOOL round-trip and width invariants."""
from __future__ import annotations

import pytest

from tinydb import types


class TestFloatRoundtrip:
    def test_zero(self) -> None:
        assert types.decode_float(types.encode_float(0.0)) == 0.0

    def test_pi(self) -> None:
        assert types.decode_float(types.encode_float(3.141592653589793)) == 3.141592653589793

    def test_negative(self) -> None:
        assert types.decode_float(types.encode_float(-2.5)) == -2.5

    def test_infinity_roundtrip(self) -> None:
        v = float("inf")
        assert types.decode_float(types.encode_float(v)) == v

    def test_nan_preserved(self) -> None:
        # NaN != NaN by IEEE-754, but isfinite is False
        import math
        assert math.isnan(types.decode_float(types.encode_float(float("nan"))))

    def test_width_is_8_bytes(self) -> None:
        assert len(types.encode_float(0.0)) == 8
        assert len(types.encode_float(3.14)) == 8


class TestTextRoundtrip:
    def test_ascii(self) -> None:
        assert types.decode_text(types.encode_text("hello")) == "hello"

    def test_empty_string(self) -> None:
        assert types.decode_text(types.encode_text("")) == ""

    def test_non_ascii(self) -> None:
        s = "你好, tinydb 🚀"
        assert types.decode_text(types.encode_text(s)) == s

    def test_long_text(self) -> None:
        s = "x" * 10_000
        assert types.decode_text(types.encode_text(s)) == s

    def test_width_varies(self) -> None:
        assert len(types.encode_text("")) == 4  # just the length prefix (u32)
        assert len(types.encode_text("a")) == 5
        assert len(types.encode_text("abc")) == 7


class TestBoolRoundtrip:
    def test_true(self) -> None:
        assert types.decode_bool(types.encode_bool(True)) is True

    def test_false(self) -> None:
        assert types.decode_bool(types.encode_bool(False)) is False

    def test_width_is_1_byte(self) -> None:
        assert len(types.encode_bool(True)) == 1
        assert len(types.encode_bool(False)) == 1

    def test_decode_rejects_garbage(self) -> None:
        with pytest.raises(ValueError):
            types.decode_bool(b"\x02")


class TestUnifiedDispatch:
    """REQ-TS-002..004: encode/decode(value, column_type) dispatch."""

    def test_dispatch_int(self) -> None:
        raw = types.encode(123, types.ColumnType.INT)
        assert types.decode(raw, types.ColumnType.INT) == 123

    def test_dispatch_float(self) -> None:
        raw = types.encode(1.5, types.ColumnType.FLOAT)
        assert types.decode(raw, types.ColumnType.FLOAT) == 1.5

    def test_dispatch_text(self) -> None:
        raw = types.encode("hi", types.ColumnType.TEXT)
        assert types.decode(raw, types.ColumnType.TEXT) == "hi"

    def test_dispatch_bool(self) -> None:
        raw = types.encode(True, types.ColumnType.BOOL)
        assert types.decode(raw, types.ColumnType.BOOL) is True
