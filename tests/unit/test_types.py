"""Unit tests for tinydb.types — INT / FLOAT / TEXT / BOOL codecs and coercion."""
from __future__ import annotations

import pytest

from tinydb import types


class TestColumnTypeEnum:
    def test_int_is_str(self) -> None:
        assert types.ColumnType.INT == "INT"

    def test_float_is_str(self) -> None:
        assert types.ColumnType.FLOAT == "FLOAT"

    def test_text_is_str(self) -> None:
        assert types.ColumnType.TEXT == "TEXT"

    def test_bool_is_str(self) -> None:
        assert types.ColumnType.BOOL == "BOOL"


class TestIntRoundtrip:
    def test_zero(self) -> None:
        assert types.decode_int(types.encode_int(0)) == 0

    def test_positive(self) -> None:
        assert types.decode_int(types.encode_int(1234567890)) == 1234567890

    def test_negative(self) -> None:
        assert types.decode_int(types.encode_int(-1234567890)) == -1234567890

    def test_max_int64(self) -> None:
        assert types.decode_int(types.encode_int(2**63 - 1)) == 2**63 - 1

    def test_min_int64(self) -> None:
        assert types.decode_int(types.encode_int(-(2**63))) == -(2**63)

    def test_roundtrip_negative(self) -> None:
        raw = types.encode_int(-1)
        assert types.decode_int(raw) == -1


class TestIntOverflow:
    def test_too_large_raises(self) -> None:
        with pytest.raises(types.IntegerOverflow):
            types.encode_int(2**63)

    def test_too_small_raises(self) -> None:
        with pytest.raises(types.IntegerOverflow):
            types.encode_int(-(2**63) - 1)


class TestEncodeLength:
    def test_int_is_exactly_8_bytes(self) -> None:
        # little-endian int64 fixed-width
        assert len(types.encode_int(0)) == 8
        assert len(types.encode_int(-1)) == 8
        assert len(types.encode_int(2**63 - 1)) == 8
