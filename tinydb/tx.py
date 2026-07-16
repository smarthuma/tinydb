"""Transaction Manager — BEGIN/COMMIT/ROLLBACK state machine.

Single-connection constraint per DP-0 (D6).
"""
from __future__ import annotations

from tinydb import storage, wal
from tinydb import types as tt


class TxManager:
    """Owns the WAL and current transaction state."""

    def __init__(self, store: storage.FileStore, wal_: wal.Wal | None = None) -> None:
        self._store = store
        self._wal = wal_ if wal_ is not None else wal.Wal(store)
        self._current_tx_id: int | None = None
        self._next_tx_id = 1

    @property
    def wal(self) -> wal.Wal:
        return self._wal

    def begin(self) -> int:
        if self._current_tx_id is not None:
            raise tt.TransactionAlreadyActive()
        self._current_tx_id = self._next_tx_id
        self._next_tx_id += 1
        return self._current_tx_id

    def commit(self, tx_id: int) -> None:
        if self._current_tx_id != tx_id:
            raise tt.TinyDBError(f"no transaction {tx_id} active")
        self._wal.append("COMMIT", tx_id=tx_id)
        self._wal.fsync()
        self._current_tx_id = None

    def rollback(self, tx_id: int) -> None:
        if self._current_tx_id != tx_id:
            raise tt.TinyDBError(f"no transaction {tx_id} active")
        self._wal.append("ROLLBACK", tx_id=tx_id)
        self._wal.fsync()
        self._current_tx_id = None

    def close(self) -> None:
        self._wal.close()
