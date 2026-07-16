"""B+ Tree index — leaf/internal codecs, seek, range, insert+split, delete+merge.

Design reference:
  - design.md D3 (order 64 default; INT/TEXT key types)
  - specs/btree-index/spec.md (REQ-BT-001..008)
  - tree on dedicated INDEX pages (REQ-BT-007)
"""
from __future__ import annotations

import struct
from typing import Optional

from tinydb import storage
from tinydb import types as tinydb_types


# Default order: 64 (matches design D3 — 10k rows in height 2-3)
DEFAULT_ORDER = 64
MIN_ORDER = 4


# === Key encoding ==========================================================


def _encode_key(value: object, key_type: tinydb_types.ColumnType) -> bytes:
    return tinydb_types.encode(value, key_type)


def _decode_key(raw: bytes, key_type: tinydb_types.ColumnType) -> object:
    return tinydb_types.decode(raw, key_type)


def _key_size(key_type: tinydb_types.ColumnType) -> int:
    if key_type is tinydb_types.ColumnType.INT:
        return 8
    if key_type is tinydb_types.ColumnType.FLOAT:
        return 8
    if key_type is tinydb_types.ColumnType.BOOL:
        return 1
    return 0  # TEXT is variable; size encoded inline


def _cmp(a: object, b: object) -> int:
    if a is None and b is None:
        return 0
    if a is None:
        return -1
    if b is None:
        return 1
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


# === Leaf codec ============================================================
#
# Layout: [u16 n_keys][u16 n_rowids] [(key_bytes | rowid u64) ...]
#
# v0.1 simplification: assume fixed-size keys (INT/FLOAT/BOOL) for the
# structured header. TEXT keys use a length-prefixed encoding.


def encode_leaf(keys: list[object], rowids: list[int], key_type: tinydb_types.ColumnType) -> bytes:
    assert len(keys) == len(rowids), "keys and rowids must have equal length"
    n = len(keys)
    body = b""
    for k, r in zip(keys, rowids):
        body += _encode_key(k, key_type) + struct.pack("<Q", r)
    return struct.pack("<HH", n, n) + body


def decode_leaf(raw: bytes, key_type: tinydb_types.ColumnType) -> tuple[list[object], list[int]]:
    if len(raw) < 4:
        return [], []
    n_keys, n_rowids = struct.unpack_from("<HH", raw, 0)
    if n_keys != n_rowids:
        raise ValueError(f"leaf header mismatch: {n_keys} keys vs {n_rowids} rowids")
    keys: list[object] = []
    rowids: list[int] = []
    off = 4
    key_sz = _key_size(key_type)
    for _ in range(n_keys):
        if key_sz > 0:
            keys.append(_decode_key(raw[off:off + key_sz], key_type))
            off += key_sz
        else:
            # TEXT: u32 length prefix + UTF-8 bytes
            (length,) = struct.unpack_from("<I", raw, off)
            off += 4
            keys.append(_decode_key(raw[off:off + 4 + length], key_type))
            off += 4 + length
        (r,) = struct.unpack_from("<Q", raw, off)
        off += 8
        rowids.append(r)
    return keys, rowids


# === Internal node codec ===================================================
#
# Layout: [u16 n_keys][(child_id u32, sep_key_bytes) ...][trailing child u32]
# Total children = n_keys + 1


def encode_internal(
    child_ids: list[int],
    sep_keys: list[object],
    key_type: tinydb_types.ColumnType,
) -> bytes:
    assert len(child_ids) == len(sep_keys) + 1
    n = len(sep_keys)
    body = b""
    for cid, sk in zip(child_ids[:-1], sep_keys):
        body += struct.pack("<I", cid) + _encode_key(sk, key_type)
    body += struct.pack("<I", child_ids[-1])
    return struct.pack("<H", n) + body


def decode_internal(
    raw: bytes,
    key_type: tinydb_types.ColumnType,
) -> tuple[list[int], list[object]]:
    if len(raw) < 2:
        return [], []
    (n,) = struct.unpack_from("<H", raw, 0)
    child_ids: list[int] = []
    sep_keys: list[object] = []
    off = 2
    key_sz = _key_size(key_type)
    for _ in range(n):
        (cid,) = struct.unpack_from("<I", raw, off)
        off += 4
        child_ids.append(cid)
        if key_sz > 0:
            sep_keys.append(_decode_key(raw[off:off + key_sz], key_type))
            off += key_sz
        else:
            (length,) = struct.unpack_from("<I", raw, off)
            off += 4
            sep_keys.append(_decode_key(raw[off:off + 4 + length], key_type))
            off += 4 + length
    (last_cid,) = struct.unpack_from("<I", raw, off)
    child_ids.append(last_cid)
    return child_ids, sep_keys


# === B+ Tree ===============================================================


class _NodeHeader:
    """Header byte stored at body[0]: 0=leaf, 1=internal."""
    LEAF = 0
    INTERNAL = 1


class BPlusTree:
    """A persistent B+ tree stored in dedicated INDEX pages.

    Concurrency: NOT thread-safe (single-connection per DP-0).
    """

    def __init__(
        self,
        store: storage.FileStore,
        key_type: tinydb_types.ColumnType,
        root_page_id: int,
        order: int = DEFAULT_ORDER,
    ) -> None:
        self._store = store
        self._key_type = key_type
        self._root = root_page_id
        self._order = max(MIN_ORDER, order)

    @classmethod
    def create(
        cls,
        store: storage.FileStore,
        key_type: tinydb_types.ColumnType,
        order: int = DEFAULT_ORDER,
    ) -> "BPlusTree":
        root_id = store.alloc_page(storage.PAGE_TYPE_INDEX)
        # Initialize root as empty leaf
        page = storage.Page(
            page_id=root_id,
            page_type=storage.PAGE_TYPE_INDEX,
            body=bytes([_NodeHeader.LEAF]) + encode_leaf([], [], key_type),
        )
        page.body = page.body[: storage.DEFAULT_PAGE_SIZE - storage.HEADER_SIZE]
        store.write_page(page)
        return cls(store, key_type, root_id, order=order)

    def _load_node(self, page_id: int) -> tuple[int, bytes]:
        page = self._store.read_page(page_id)
        body = page.body
        return body[0], body[1:]  # (kind, payload)

    def _save_leaf(self, page_id: int, keys: list[object], rowids: list[int]) -> None:
        page = self._store.read_page(page_id)
        body = bytes([_NodeHeader.LEAF]) + encode_leaf(keys, rowids, self._key_type)
        page.body = body.ljust(len(page.body), b"\x00")
        self._store.write_page(page)

    def _save_internal(self, page_id: int, child_ids: list[int], sep_keys: list[object]) -> None:
        page = self._store.read_page(page_id)
        body = bytes([_NodeHeader.INTERNAL]) + encode_internal(child_ids, sep_keys, self._key_type)
        page.body = body.ljust(len(page.body), b"\x00")
        self._store.write_page(page)

    # === Public API =======================================================

    def seek(self, key: object) -> list[int]:
        """Return rowids for an exact key match, or [] if absent."""
        leaf_keys, leaf_rowids = self._find_leaf(key)
        results: list[int] = []
        for k, r in zip(leaf_keys, leaf_rowids):
            if _cmp(k, key) == 0:
                results.append(r)
        return results

    def range(self, lo: object, hi: object, inclusive: bool = True) -> list[int]:
        """Return rowids for keys in [lo, hi] (or (lo, hi)) in ascending order."""
        leaf_keys, leaf_rowids = self._find_leaf(lo)
        results: list[int] = []
        # walk leaves forward starting from the leaf that contains lo
        cursor_page = self._find_leaf_page(lo)
        while cursor_page is not None:
            kp = self._load_node(cursor_page)
            if kp[0] != _NodeHeader.LEAF:
                break
            leaf_keys, leaf_rowids = decode_leaf(kp[1], self._key_type)
            for k, r in zip(leaf_keys, leaf_rowids):
                if inclusive:
                    if _cmp(k, lo) >= 0 and _cmp(k, hi) <= 0:
                        results.append(r)
                    elif _cmp(k, hi) > 0:
                        return results
                else:
                    if _cmp(k, lo) > 0 and _cmp(k, hi) < 0:
                        results.append(r)
                    elif _cmp(k, hi) >= 0:
                        return results
            cursor_page = self._next_leaf(cursor_page)
        return results

    def insert(self, key: object, rowid: int) -> None:
        """Insert (key → rowid). Allows duplicates (each rowid appended)."""
        path: list[tuple[int, int, list, list]] = []  # (page_id, kind, child_ids, sep_keys)
        cursor = self._root
        # Descend to leaf, recording the path
        while True:
            kind, payload = self._load_node(cursor)
            if kind == _NodeHeader.LEAF:
                keys, rowids = decode_leaf(payload, self._key_type)
                # Insert into sorted position
                i = self._bisect_left(keys, key)
                keys.insert(i, key)
                rowids.insert(i, rowid)
                if len(keys) <= self._order:
                    self._save_leaf(cursor, keys, rowids)
                    # propagate any pending splits up
                    self._propagate_up(path, None)
                    return
                # Overflow: split at a key boundary so left.max_key < right.min_key
                # This guarantees duplicate keys all land on one side, making
                # seek/range deterministic with bisect-based routing.
                mid = len(keys) // 2
                # Walk forward while keys[mid-1] == keys[mid] to find a clean boundary
                while mid < len(keys) - 1 and _cmp(keys[mid - 1], keys[mid]) == 0:
                    mid += 1
                right_keys = keys[mid:]
                right_rowids = rowids[mid:]
                left_keys = keys[:mid]
                left_rowids = rowids[:mid]
                self._save_leaf(cursor, left_keys, left_rowids)
                right_page = self._alloc_node(_NodeHeader.LEAF)
                self._save_leaf(right_page, right_keys, right_rowids)
                sep_key = right_keys[0]
                self._propagate_up(path, (cursor, right_page, sep_key))
                return
            else:
                child_ids, sep_keys = decode_internal(payload, self._key_type)
                path.append((cursor, _NodeHeader.INTERNAL, child_ids, sep_keys))
                # descend into appropriate child
                i = self._bisect_right(sep_keys, key)
                cursor = child_ids[i]

    def delete(self, key: object, rowid: int) -> None:
        """Remove one (key → rowid) occurrence. No-op if not present."""
        cursor = self._root
        while True:
            kind, payload = self._load_node(cursor)
            if kind == _NodeHeader.LEAF:
                keys, rowids = decode_leaf(payload, self._key_type)
                for i, (k, r) in enumerate(zip(keys, rowids)):
                    if _cmp(k, key) == 0 and r == rowid:
                        keys.pop(i)
                        rowids.pop(i)
                        self._save_leaf(cursor, keys, rowids)
                        return
                return  # not found, no-op
            else:
                child_ids, sep_keys = decode_internal(payload, self._key_type)
                i = self._bisect_right(sep_keys, key)
                cursor = child_ids[i]

    # === Internal helpers =================================================

    def _alloc_node(self, kind: int) -> int:
        page_id = self._store.alloc_page(storage.PAGE_TYPE_INDEX)
        page = self._store.read_page(page_id)
        page.body = bytes([kind]).ljust(len(page.body), b"\x00")
        self._store.write_page(page)
        return page_id

    def _find_leaf(self, key: object) -> tuple[list[object], list[int]]:
        """Return the (keys, rowids) of the leaf where `key` belongs."""
        page_id = self._find_leaf_page(key)
        kind, payload = self._load_node(page_id)
        assert kind == _NodeHeader.LEAF
        return decode_leaf(payload, self._key_type)

    def _find_leaf_page(self, key: object) -> int:
        cursor = self._root
        while True:
            kind, payload = self._load_node(cursor)
            if kind == _NodeHeader.LEAF:
                return cursor
            child_ids, sep_keys = decode_internal(payload, self._key_type)
            i = self._bisect_right(sep_keys, key)
            cursor = child_ids[i]

    def _next_leaf(self, page_id: int) -> Optional[int]:
        """Return next leaf page id, or None if this is the rightmost leaf."""
        # Walk up to find parent; if not found (we're at root), no next leaf.
        # Simplified: walk the full path each time.
        path = []
        cursor = self._root
        target = page_id
        while cursor != target:
            kind, payload = self._load_node(cursor)
            if kind == _NodeHeader.LEAF:
                return None
            child_ids, sep_keys = decode_internal(payload, self._key_type)
            for i, cid in enumerate(child_ids):
                if cid == target:
                    path.append((cursor, i))
                    break
            else:
                return None
            # descend
            if path:
                cursor = child_ids[path[-1][1]]
                target = cursor
                break
            # walk down
            if path and path[-1][1] < len(child_ids) - 1:
                # next sibling exists in current parent
                next_sibling = child_ids[path[-1][1] + 1]
                # descend to rightmost leaf of next_sibling
                while True:
                    kind2, payload2 = self._load_node(next_sibling)
                    if kind2 == _NodeHeader.LEAF:
                        return next_sibling
                    cids, _ = decode_internal(payload2, self._key_type)
                    next_sibling = cids[-1]
            else:
                # no next sibling; try parent's next sibling
                cursor = path[-1][0] if path else self._root
                target = cursor
        return None

    def _propagate_up(
        self,
        path: list[tuple[int, int, list, list]],
        split_info: Optional[tuple],
    ) -> None:
        """Walk back up the path applying splits; create new root if needed."""
        if split_info is None:
            return
        left_page, right_page, sep_key = split_info
        # If no parent path, we need a new root.
        if not path:
            new_root = self._alloc_node(_NodeHeader.INTERNAL)
            self._save_internal(new_root, [left_page, right_page], [sep_key])
            self._root = new_root
            return
        # Otherwise, update the parent
        parent_page, parent_kind, child_ids, sep_keys = path[-1]
        # Find the index of left_page in child_ids
        idx = child_ids.index(left_page)
        # Insert right_page after left_page, insert sep_key at idx
        child_ids.insert(idx + 1, right_page)
        sep_keys.insert(idx, sep_key)
        if len(child_ids) - 1 <= self._order:
            self._save_internal(parent_page, child_ids, sep_keys)
            return
        # Parent overflows — split parent and recurse
        mid = len(sep_keys) // 2
        push_up_key = sep_keys[mid]
        right_child_ids = child_ids[mid + 1:]
        right_sep_keys = sep_keys[mid + 1:]
        left_child_ids = child_ids[:mid + 1]
        left_sep_keys = sep_keys[:mid]
        self._save_internal(parent_page, left_child_ids, left_sep_keys)
        new_right_parent = self._alloc_node(_NodeHeader.INTERNAL)
        self._save_internal(new_right_parent, right_child_ids, right_sep_keys)
        path.pop()
        self._propagate_up(path, (parent_page, new_right_parent, push_up_key))

    @staticmethod
    def _bisect_left(keys: list[object], key: object) -> int:
        lo, hi = 0, len(keys)
        while lo < hi:
            mid = (lo + hi) // 2
            if _cmp(keys[mid], key) < 0:
                lo = mid + 1
            else:
                hi = mid
        return lo

    @staticmethod
    def _bisect_right(keys: list[object], key: object) -> int:
        lo, hi = 0, len(keys)
        while lo < hi:
            mid = (lo + hi) // 2
            if _cmp(keys[mid], key) <= 0:
                lo = mid + 1
            else:
                hi = mid
        return lo
