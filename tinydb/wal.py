"""Write-Ahead Log — record codec, append, fsync, replay.

Design references:
  - design.md D4 (WAL layout: length-prefixed + LSN + checksum)
  - specs/transaction-manager/spec.md (REQ-TM-004, REQ-TM-005)
"""
from __future__ import annotations

import os
import struct
import zlib
from dataclasses import dataclass

from tinydb import storage
from tinydb import types as tt


# === Record dataclass ======================================================


@dataclass(frozen=True)
class WalRecord:
    kind: str   # 'MUTATE' | 'COMMIT' | 'ROLLBACK' | 'CHECKPOINT'
    lsn: int
    tx_id: int
    page_id: int
    before: bytes
    after: bytes


# === Codec =================================================================
#
# Layout: [len u32][lsn u32][tx_id u64][kind 4s][page_id u32]
#         [before_len u32][before_bytes]
#         [after_len u32][after_bytes]
#         [crc32 u32]

_KIND_BYTES = {
    "MUTATE": b"MUTA",
    "COMMIT": b"COMM",
    "ROLLBACK": b"ROLL",
    "CHECKPOINT": b"CHKP",
}


def encode_record(rec: WalRecord) -> bytes:
    if rec.kind not in _KIND_BYTES:
        raise ValueError(f"unknown record kind {rec.kind!r}")
    body = struct.pack(
        "<I Q 4s I I",
        rec.lsn, rec.tx_id, _KIND_BYTES[rec.kind], rec.page_id, len(rec.before),
    )
    body += rec.before
    body += struct.pack("<I", len(rec.after)) + rec.after
    crc = zlib.crc32(body) & 0xFFFFFFFF
    framed = struct.pack("<I", len(body)) + body + struct.pack("<I", crc)
    return framed


def decode_record(raw: bytes) -> WalRecord:
    if len(raw) < 4:
        raise tt.TransactionLogCorrupt(lsn=-1)
    (body_len,) = struct.unpack_from("<I", raw, 0)
    if len(raw) < 4 + body_len + 4:
        raise tt.TransactionLogCorrupt(lsn=-1)
    body = raw[4:4 + body_len]
    expected_crc = struct.unpack_from("<I", raw, 4 + body_len)[0]
    actual_crc = zlib.crc32(body) & 0xFFFFFFFF
    if expected_crc != actual_crc:
        raise tt.TransactionLogCorrupt(lsn=-1)
    lsn, tx_id, kind_bytes, page_id, before_len = struct.unpack_from(
        "<I Q 4s I I", body, 0,
    )
    kind = next((k for k, v in _KIND_BYTES.items() if v == kind_bytes), None)
    if kind is None:
        raise tt.TransactionLogCorrupt(lsn=lsn)
    before = body[24:24 + before_len]
    off = 24 + before_len
    (after_len,) = struct.unpack_from("<I", body, off)
    off += 4
    after = body[off:off + after_len]
    return WalRecord(kind=kind, lsn=lsn, tx_id=tx_id, page_id=page_id,
                     before=before, after=after)


# === Wal class =============================================================


class Wal:
    """A simple append-only WAL backed by a sibling file `<db>-wal`."""

    def __init__(self, store: storage.FileStore) -> None:
        self._store = store
        self._path = store.path + "-wal"
        self._fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        self._next_lsn = 1
        self._offset = 0
        self._scan_existing_lsns()

    def _scan_existing_lsns(self) -> None:
        """On open, scan existing WAL to recover next LSN and committed tx ids."""
        try:
            size = os.fstat(self._fd).st_size
        except OSError:
            size = 0
        off = 0
        max_lsn = 0
        while off < size:
            try:
                header = os.pread(self._fd, 4, off)
                if len(header) < 4:
                    break
                (body_len,) = struct.unpack("<I", header)
                total = 4 + body_len + 4
                if off + total > size:
                    break
                body = os.pread(self._fd, body_len, off + 4)
                expected_crc = struct.unpack("<I", os.pread(self._fd, 4, off + 4 + body_len))[0]
                actual_crc = zlib.crc32(body) & 0xFFFFFFFF
                if expected_crc != actual_crc:
                    break  # corrupt record — stop scanning
                (lsn,) = struct.unpack_from("<I", body, 0)
                if lsn > max_lsn:
                    max_lsn = lsn
                off += total
            except Exception:
                break
        self._offset = off
        self._next_lsn = max_lsn + 1

    def append(
        self,
        kind: str,
        *,
        tx_id: int = 0,
        page_id: int = 0,
        before: bytes = b"",
        after: bytes = b"",
    ) -> int:
        """Append a record and return its LSN."""
        rec = WalRecord(
            kind=kind, lsn=self._next_lsn, tx_id=tx_id, page_id=page_id,
            before=before, after=after,
        )
        raw = encode_record(rec)
        os.pwrite(self._fd, raw, self._offset)
        self._offset += len(raw)
        self._next_lsn += 1
        return rec.lsn

    def fsync(self) -> None:
        os.fsync(self._fd)

    def close(self) -> None:
        if self._fd != -1:
            os.close(self._fd)
            self._fd = -1

    @property
    def path(self) -> str:
        return self._path

    def __enter__(self) -> "Wal":
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fd != -1:
            self.close()

    def replay(self, store: storage.FileStore) -> None:
        """Replay WAL: redo committed mutations, skip rolled-back."""
        size = os.fstat(self._fd).st_size
        off = 0
        pending: dict[int, list[WalRecord]] = {}
        committed: set[int] = set()
        while off < size:
            header = os.pread(self._fd, 4, off)
            if len(header) < 4:
                break
            (body_len,) = struct.unpack("<I", header)
            total = 4 + body_len + 4
            if off + total > size:
                break
            body = os.pread(self._fd, body_len, off + 4)
            try:
                rec = decode_record(struct.pack("<I", body_len) + body + os.pread(self._fd, 4, off + 4 + body_len))
            except tt.TransactionLogCorrupt:
                break
            if rec.kind == "MUTATE":
                pending.setdefault(rec.tx_id, []).append(rec)
            elif rec.kind == "COMMIT":
                committed.add(rec.tx_id)
            elif rec.kind == "ROLLBACK":
                pending.pop(rec.tx_id, None)
            off += total
        # Apply committed mutations
        for tx_id in committed:
            for rec in pending.get(tx_id, []):
                if rec.page_id != 0 and rec.after:
                    page = storage.Page(
                        page_id=rec.page_id,
                        page_type=rec.after[0] if rec.after else storage.PAGE_TYPE_TABLE,
                        body=rec.after[9:] if len(rec.after) > 9 else b"",
                        lsn=rec.lsn,
                    )
                    store.write_page(page)
