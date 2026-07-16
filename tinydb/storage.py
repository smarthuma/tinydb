"""Storage engine: page format, single-file persistence, buffer pool, fsync.

Design references:
  - design.md D2 (4 KiB pages, little-endian, 9-byte header)
  - design.md D4 (WAL lives elsewhere — this module only handles pages)
  - design.md D5 (catalog in header page — handled in b5, see PageType.HEADER)
  - specs/storage-engine/spec.md (REQ-SE-001..006)
"""
from __future__ import annotations

import os
import struct
from collections import OrderedDict
from dataclasses import dataclass

# === Page type constants (REQ-SE-003) ======================================
# These appear in `page_type` byte of every page header. Index 0 is reserved
# for "free" pages so that an uninitialized page is detectable as invalid.

PAGE_TYPE_FREE = 0
PAGE_TYPE_HEADER = 1
PAGE_TYPE_TABLE = 2
PAGE_TYPE_INDEX = 3
PAGE_TYPE_OVERFLOW = 4

VALID_PAGE_TYPES = frozenset(
    {PAGE_TYPE_FREE, PAGE_TYPE_HEADER, PAGE_TYPE_TABLE, PAGE_TYPE_INDEX, PAGE_TYPE_OVERFLOW}
)


# === Page header codec (REQ-SE-003) ========================================

_HEADER_STRUCT = struct.Struct("<I B I")  # page_id u32, page_type u8, lsn u32
HEADER_SIZE = _HEADER_STRUCT.size  # 9


def pack_header(page_id: int, page_type: int, lsn: int) -> bytes:
    """Encode the 9-byte page header."""
    if not (0 <= page_id <= 0xFFFFFFFF):
        raise ValueError(f"page_id {page_id} out of u32 range")
    if page_type not in VALID_PAGE_TYPES:
        raise ValueError(f"page_type {page_type} not in {VALID_PAGE_TYPES}")
    if not (0 <= lsn <= 0xFFFFFFFF):
        raise ValueError(f"lsn {lsn} out of u32 range")
    return _HEADER_STRUCT.pack(page_id, page_type, lsn)


def unpack_header(raw: bytes) -> tuple[int, int, int]:
    """Decode a 9-byte page header into (page_id, page_type, lsn)."""
    if len(raw) != HEADER_SIZE:
        raise ValueError(f"unpack_header expects {HEADER_SIZE} bytes, got {len(raw)}")
    return _HEADER_STRUCT.unpack(raw)


# === Page class (REQ-SE-001, REQ-SE-002, REQ-SE-003) =======================

@dataclass
class Page:
    """An in-memory representation of a single page."""

    page_id: int
    page_type: int
    body: bytes
    lsn: int = 0

    def __post_init__(self) -> None:
        if self.page_type not in VALID_PAGE_TYPES:
            raise ValueError(f"invalid page_type {self.page_type}")

    def serialize(self, page_size: int) -> bytes:
        """Serialize to exactly `page_size` bytes (9-byte header + zero-padded body)."""
        if len(self.body) > page_size - HEADER_SIZE:
            raise ValueError(
                f"page body {len(self.body)} exceeds capacity {page_size - HEADER_SIZE}"
            )
        header = pack_header(self.page_id, self.page_type, self.lsn)
        return header + self.body + b"\x00" * (page_size - HEADER_SIZE - len(self.body))


# === FileStore: open / close / read / write (REQ-SE-001, REQ-SE-002) ======

DEFAULT_PAGE_SIZE = 4096
MIN_PAGE_SIZE = 512
MAX_PAGE_SIZE = 65536


class FileStore:
    """A single-file page store. Owns the file descriptor; closes on `close()`.

    Concurrency: NOT thread-safe (matches DP-0 single-connection constraint).
    """

    def __init__(
        self,
        path: str,
        page_size: int = DEFAULT_PAGE_SIZE,
        *,
        _pre_existing: bool = False,
    ) -> None:
        if not (MIN_PAGE_SIZE <= page_size <= MAX_PAGE_SIZE):
            raise ValueError(
                f"page_size {page_size} out of range [{MIN_PAGE_SIZE}, {MAX_PAGE_SIZE}]"
            )
        if page_size & (page_size - 1) != 0:
            raise ValueError(f"page_size {page_size} must be a power of 2")
        self.path = path
        self.page_size = page_size
        if _pre_existing:
            # Re-open: keep existing file, do not truncate
            self._fd = os.open(path, os.O_RDWR)
        else:
            # Fresh open: create or truncate
            self._fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o644)
            self._write_header_page()
        self._file_size = os.fstat(self._fd).st_size

    def _write_header_page(self) -> None:
        """Write page 0 (header page) on a fresh file."""
        body = bytearray(self.page_size - HEADER_SIZE)
        # Magic bytes at the start of body so we can detect tinydb files
        body[0:8] = b"tinydb!\x00"
        # Store page_size at body[8:12] (u32 little-endian)
        struct.pack_into("<I", body, 8, self.page_size)
        page = Page(page_id=0, page_type=PAGE_TYPE_HEADER, body=bytes(body))
        os.pwrite(self._fd, page.serialize(self.page_size), 0)
        self._file_size = self.page_size

    @classmethod
    def open(cls, path: str, page_size: int = DEFAULT_PAGE_SIZE) -> "FileStore":
        """Open an existing file, preserving its page_size from the header."""
        try:
            st = os.stat(path)
        except FileNotFoundError:
            return cls(path, page_size, _pre_existing=False)
        if st.st_size == 0:
            return cls(path, page_size, _pre_existing=False)
        # Read header to recover page_size
        with open(path, "rb") as f:
            header_raw = f.read(HEADER_SIZE)
            body_prefix = f.read(8 + 4)
        if len(header_raw) < HEADER_SIZE or len(body_prefix) < 12:
            raise ValueError(f"{path} is not a valid tinydb file (truncated header)")
        # Header must be page 0 of type HEADER
        page_id, page_type, _lsn = unpack_header(header_raw)
        if page_id != 0 or page_type != PAGE_TYPE_HEADER:
            raise ValueError(f"{path} is not a tinydb file (header magic mismatch)")
        # Body must start with "tinydb!\0" (the magic)
        if body_prefix[:8] != b"tinydb!\x00":
            raise ValueError(f"{path} is not a tinydb file (body magic mismatch)")
        (stored_page_size,) = struct.unpack_from("<I", body_prefix, 8)
        return cls(path, stored_page_size, _pre_existing=True)

    def close(self) -> None:
        if self._fd != -1:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = -1

    def __enter__(self) -> "FileStore":
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fd != -1:
            self.close()

    @property
    def file_size(self) -> int:
        return self._file_size

    @property
    def page_count(self) -> int:
        return self._file_size // self.page_size

    def read_page(self, page_id: int) -> Page:
        """Read a page from disk. Raises if page_id out of range."""
        if page_id < 0 or page_id >= self.page_count:
            raise IndexError(f"page_id {page_id} out of range [0, {self.page_count})")
        offset = page_id * self.page_size
        raw = os.pread(self._fd, self.page_size, offset)
        if len(raw) != self.page_size:
            raise IOError(f"short read on page {page_id}: got {len(raw)} bytes")
        page_id_hdr, page_type, lsn = unpack_header(raw[:HEADER_SIZE])
        if page_id_hdr != page_id:
            raise IOError(
                f"page header mismatch: requested {page_id}, header says {page_id_hdr}"
            )
        return Page(page_id=page_id, page_type=page_type, body=raw[HEADER_SIZE:], lsn=lsn)

    def write_page(self, page: Page) -> None:
        """Write a page to disk. Page body is truncated/padded to page_size."""
        offset = page.page_id * self.page_size
        os.pwrite(self._fd, page.serialize(self.page_size), offset)
        # Track file growth
        new_end = offset + self.page_size
        if new_end > self._file_size:
            self._file_size = new_end

    def alloc_page(self, page_type: int) -> int:
        """Allocate a fresh page of the given type. Returns the new page_id.

        v0.1 simple policy: always extend the file (no free-list reuse yet —
        see T-2.4 for the upgrade).
        """
        new_page_id = self.page_count
        page = Page(page_id=new_page_id, page_type=page_type, body=b"", lsn=0)
        self.write_page(page)
        return new_page_id

    def free_page(self, page_id: int) -> None:
        """Mark a page as free. v0.1 stub: just overwrites with a FREE page.

        Upgrade to free-list reuse in T-2.4.
        """
        page = Page(page_id=page_id, page_type=PAGE_TYPE_FREE, body=b"", lsn=0)
        self.write_page(page)

    def fsync(self) -> None:
        """Flush file data + metadata to disk."""
        os.fsync(self._fd)


# === BufferPool with LRU eviction (REQ-SE-004) ============================


class BufferPool:
    """In-memory cache of pages with LRU eviction.

    Concurrency: NOT thread-safe (DP-0 single-connection). All operations
    assume a single caller.
    """

    def __init__(self, store: FileStore, capacity: int = 128) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be ≥ 1, got {capacity}")
        self._store = store
        self._capacity = capacity
        # OrderedDict preserves insertion order; we move entries to the end on touch
        self._pages: OrderedDict[int, Page] = OrderedDict()
        self._dirty: set[int] = set()
        self._pin_count: dict[int, int] = {}

    def contains(self, page_id: int) -> bool:
        return page_id in self._pages

    def is_pinned(self, page_id: int) -> bool:
        return self._pin_count.get(page_id, 0) > 0

    def get(self, page_id: int) -> Page:
        """Return the page, loading from disk if necessary. Pins the page."""
        if page_id in self._pages:
            self._pages.move_to_end(page_id)  # mark as most-recently-used
            self._pin_count[page_id] = self._pin_count.get(page_id, 0) + 1
            return self._pages[page_id]
        # Not in cache — may need to evict first
        if len(self._pages) >= self._capacity:
            self._evict_one()
        page = self._store.read_page(page_id)
        self._pages[page_id] = page
        self._pin_count[page_id] = 1
        return page

    def unpin(self, page_id: int, *, dirty: bool = False) -> None:
        """Release one pin on the page. Optionally mark it dirty."""
        if self._pin_count.get(page_id, 0) <= 0:
            raise ValueError(f"page {page_id} is not pinned")
        self._pin_count[page_id] -= 1
        if dirty:
            self._dirty.add(page_id)

    def mark_dirty(self, page_id: int) -> None:
        """Mark a currently-pinned page as dirty without unpinning."""
        if self._pin_count.get(page_id, 0) <= 0:
            raise ValueError(f"page {page_id} is not pinned — cannot mark dirty")
        self._dirty.add(page_id)

    def _evict_one(self) -> None:
        """Evict the LRU page that is not currently pinned. Writes it back if dirty.

        If every cached page is pinned (over-capacity by intent), the new page
        is allowed to live temporarily beyond capacity; eviction is deferred
        until something is unpinned.
        """
        for pid in list(self._pages.keys()):
            if self._pin_count.get(pid, 0) > 0:
                continue
            # Found a candidate
            if pid in self._dirty:
                self._store.write_page(self._pages[pid])
                self._dirty.discard(pid)
            del self._pages[pid]
            self._pin_count.pop(pid, None)
            return
        # All pages are pinned — allow over-capacity temporarily; no eviction

    def flush_all(self) -> None:
        """Write every dirty page back to disk (REQ-SE-004 dirty-flush invariant)."""
        for pid in list(self._dirty):
            if pid in self._pages:
                self._store.write_page(self._pages[pid])
        self._dirty.clear()
