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
