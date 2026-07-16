"""Type system: INT / FLOAT / TEXT / BOOL codecs, coercion, and exception hierarchy.

Design references:
  - design.md D2 (little-endian fixed-size pages)
  - design.md D8 (single-exception base class TinyDBError)
  - specs/type-system/spec.md (REQ-TS-001 .. REQ-TS-007)
"""
from __future__ import annotations

import struct
from enum import Enum

# === ColumnType ============================================================

class ColumnType(str, Enum):
    """Declared SQL column types. Inherits from str so ``== "INT"`` works."""

    INT = "INT"
    FLOAT = "FLOAT"
    TEXT = "TEXT"
    BOOL = "BOOL"


# === Exception hierarchy ===================================================

class TinyDBError(Exception):
    """Base class for every tinydb-raised error."""


class ParseError(TinyDBError):
    """Raised by the parser at a known (line, column)."""

    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__(f"{message} (line {line}, column {column})")
        self.line = line
        self.column = column


class TypeMismatch(TinyDBError):
    """A value's Python type is not assignable to the column's declared type."""

    def __init__(self, column: str, expected: str, got: str) -> None:
        super().__init__(
            f"TypeMismatch(column={column!r}, expected={expected!r}, got={got!r})"
        )
        self.column = column
        self.expected = expected
        self.got = got


class IntegerOverflow(TinyDBError):
    """An int value is outside the signed 64-bit range."""

    def __init__(self, value: int, max_value: int) -> None:
        super().__init__(f"IntegerOverflow(value={value}, max={max_value})")
        self.value = value
        self.max_value = max_value


class NotNullViolation(TinyDBError):
    """A NOT NULL column received NULL."""

    def __init__(self, column: str) -> None:
        super().__init__(f"NotNullViolation(column={column!r})")
        self.column = column


class UniqueViolation(TinyDBError):
    """A UNIQUE or PRIMARY KEY column received a duplicate."""

    def __init__(self, constraint: str, key: object) -> None:
        super().__init__(f"UniqueViolation(constraint={constraint!r}, key={key!r})")
        self.constraint = constraint
        self.key = key


# === INT codec (REQ-TS-001) ================================================

_INT_MIN = -(2**63)
_INT_MAX = 2**63 - 1
_INT_STRUCT = struct.Struct("<q")  # little-endian signed int64


def _checked_i64(value: int) -> int:
    """Raise IntegerOverflow if value is outside signed int64 range."""
    if not isinstance(value, int) or isinstance(value, bool):
        # bool is a subclass of int; caller decides if that's OK
        raise TypeError(f"_checked_i64 expects int, got {type(value).__name__}")
    if value < _INT_MIN or value > _INT_MAX:
        raise IntegerOverflow(value, _INT_MAX)
    return value


def encode_int(value: int) -> bytes:
    """Encode a Python int as 8 little-endian bytes (REQ-TS-001)."""
    return _INT_STRUCT.pack(_checked_i64(value))


def decode_int(raw: bytes) -> int:
    """Decode 8 little-endian bytes back to a Python int."""
    if len(raw) != 8:
        raise ValueError(f"decode_int expects 8 bytes, got {len(raw)}")
    return _INT_STRUCT.unpack(raw)[0]


# === FLOAT codec (REQ-TS-002) ==============================================

_FLOAT_STRUCT = struct.Struct("<d")  # little-endian binary64


def encode_float(value: float) -> bytes:
    """Encode a Python float as 8 little-endian IEEE-754 bytes (REQ-TS-002)."""
    if not isinstance(value, float):
        raise TypeError(f"encode_float expects float, got {type(value).__name__}")
    return _FLOAT_STRUCT.pack(value)


def decode_float(raw: bytes) -> float:
    """Decode 8 little-endian IEEE-754 bytes back to a Python float."""
    if len(raw) != 8:
        raise ValueError(f"decode_float expects 8 bytes, got {len(raw)}")
    return _FLOAT_STRUCT.unpack(raw)[0]


# === TEXT codec (REQ-TS-003) ===============================================

_TEXT_LEN_STRUCT = struct.Struct("<I")  # u32 length prefix


def encode_text(value: str) -> bytes:
    """Encode a Python str as u32 length + UTF-8 bytes (REQ-TS-003)."""
    if not isinstance(value, str):
        raise TypeError(f"encode_text expects str, got {type(value).__name__}")
    encoded = value.encode("utf-8")
    return _TEXT_LEN_STRUCT.pack(len(encoded)) + encoded


def decode_text(raw: bytes) -> str:
    """Decode u32 length + UTF-8 bytes back to a Python str."""
    if len(raw) < 4:
        raise ValueError(f"decode_text expects ≥ 4 bytes, got {len(raw)}")
    (length,) = _TEXT_LEN_STRUCT.unpack(raw[:4])
    body = raw[4:]
    if len(body) != length:
        raise ValueError(
            f"decode_text length mismatch: header says {length}, got {len(body)}"
        )
    return body.decode("utf-8")


# === BOOL codec (REQ-TS-004) ===============================================


def encode_bool(value: bool) -> bytes:
    """Encode a Python bool as a single byte (0x00 or 0x01)."""
    if not isinstance(value, bool):
        raise TypeError(f"encode_bool expects bool, got {type(value).__name__}")
    return b"\x01" if value else b"\x00"


def decode_bool(raw: bytes) -> bool:
    """Decode a single byte back to a Python bool."""
    if len(raw) != 1:
        raise ValueError(f"decode_bool expects 1 byte, got {len(raw)}")
    if raw == b"\x00":
        return False
    if raw == b"\x01":
        return True
    raise ValueError(f"decode_bool got byte {raw[0]:#x}; expected 0x00 or 0x01")


# === Unified dispatch ======================================================

_ENCODE_DISPATCH = {
    ColumnType.INT: encode_int,
    ColumnType.FLOAT: encode_float,
    ColumnType.TEXT: encode_text,
    ColumnType.BOOL: encode_bool,
}

_DECODE_DISPATCH = {
    ColumnType.INT: decode_int,
    ColumnType.FLOAT: decode_float,
    ColumnType.TEXT: decode_text,
    ColumnType.BOOL: decode_bool,
}


def encode(value: object, column_type: ColumnType) -> bytes:
    """Encode a value using the codec registered for `column_type`."""
    try:
        codec = _ENCODE_DISPATCH[column_type]
    except KeyError as e:
        raise ValueError(f"unknown column_type {column_type!r}") from e
    return codec(value)  # type: ignore[arg-type]


def decode(raw: bytes, column_type: ColumnType) -> object:
    """Decode raw bytes using the codec registered for `column_type`."""
    try:
        codec = _DECODE_DISPATCH[column_type]
    except KeyError as e:
        raise ValueError(f"unknown column_type {column_type!r}") from e
    return codec(raw)


# === Coercion (REQ-TS-006) =================================================


def coerce_in(value: object, column_type: ColumnType, column_name: str) -> object:
    """Coerce `value` to a Python type acceptable by `column_type`'s encoder.

    Raises TypeMismatch on rejection; IntegerOverflow on out-of-range int;
    bool → int (False → 0, True → 1) per REQ-TS-006.
    """
    if value is None:
        return None  # NULL handled by encode_with_null, not by codec

    if column_type is ColumnType.INT:
        # bool is a subclass of int; we explicitly accept it and coerce
        if isinstance(value, bool):
            return 1 if value else 0
        if not isinstance(value, int):
            raise TypeMismatch(column_name, "INT", type(value).__name__)
        # bounds check via encode_int which raises IntegerOverflow
        encode_int(value)
        return value

    if column_type is ColumnType.FLOAT:
        # REQ-TS-006: strict — Python int is NOT implicitly a FLOAT
        if not isinstance(value, float):
            raise TypeMismatch(column_name, "FLOAT", type(value).__name__)
        return value

    if column_type is ColumnType.TEXT:
        if not isinstance(value, str):
            raise TypeMismatch(column_name, "TEXT", type(value).__name__)
        return value

    if column_type is ColumnType.BOOL:
        if not isinstance(value, bool):
            raise TypeMismatch(column_name, "BOOL", type(value).__name__)
        return value

    raise ValueError(f"unknown column_type {column_type!r}")


# === NULL handling (REQ-TS-005) ============================================

_NULL_MARKER = b"\x00"


def encode_none() -> bytes:
    """Return the on-disk NULL marker."""
    return _NULL_MARKER


def is_null(raw: bytes) -> bool:
    """True iff `raw` is the NULL marker."""
    return raw == _NULL_MARKER


def encode_with_null(value: object, column_type: ColumnType) -> tuple[bytes, bool]:
    """Encode `value` (possibly None) for `column_type`, returning (bytes, is_null)."""
    if value is None:
        return _NULL_MARKER, True
    coerced = coerce_in(value, column_type, column_name="?")
    return encode(coerced, column_type), False


def decode_with_null(raw: bytes, was_null: bool, column_type: ColumnType) -> object:
    """Decode the result of encode_with_null back to a Python value (or None)."""
    if was_null:
        return None
    return decode(raw, column_type)
