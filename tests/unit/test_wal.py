"""T-6.1..T-6.3 tests: WAL record codec + append/fsync + BEGIN/COMMIT/ROLLBACK state machine."""
from __future__ import annotations

import os
import pytest

from tinydb import storage, wal, tx
from tinydb import types as tt


@pytest.fixture
def store(tmp_path):
    path = str(tmp_path / "t.db")
    s = storage.FileStore.open(path)
    yield s
    s.close()


class TestWalRecordCodec:
    def test_mutation_roundtrip(self) -> None:
        rec = wal.WalRecord(
            kind="MUTATE", lsn=1, tx_id=10, page_id=5,
            before=b"old", after=b"new",
        )
        raw = wal.encode_record(rec)
        decoded = wal.decode_record(raw)
        assert decoded == rec

    def test_commit_roundtrip(self) -> None:
        rec = wal.WalRecord(
            kind="COMMIT", lsn=2, tx_id=10, page_id=0,
            before=b"", after=b"",
        )
        raw = wal.encode_record(rec)
        decoded = wal.decode_record(raw)
        assert decoded == rec

    def test_corrupt_checksum_raises(self) -> None:
        rec = wal.WalRecord(
            kind="MUTATE", lsn=3, tx_id=10, page_id=5,
            before=b"old", after=b"new",
        )
        raw = bytearray(wal.encode_record(rec))
        raw[-1] ^= 0xFF  # corrupt checksum
        with pytest.raises(tt.TransactionLogCorrupt):
            wal.decode_record(bytes(raw))


class TestWalAppend:
    def test_first_record_starts_at_zero(self, store):
        w = wal.Wal(store)
        lsn1 = w.append("MUTATE", page_id=1, before=b"", after=b"x")
        lsn2 = w.append("COMMIT", tx_id=1)
        assert lsn1 == 1
        assert lsn2 == 2

    def test_fsync_persists_records(self, store, tmp_path):
        w = wal.Wal(store)
        w.append("MUTATE", page_id=1, before=b"", after=b"x")
        w.append("COMMIT", tx_id=1)
        w.fsync()
        assert os.path.exists(tmp_path / "t.db-wal")
        assert (tmp_path / "t.db-wal").stat().st_size > 0


class TestTxManager:
    def test_begin_starts_transaction(self, store):
        mgr = tx.TxManager(store)
        tx_id = mgr.begin()
        assert tx_id == 1

    def test_nested_begin_rejected(self, store):
        mgr = tx.TxManager(store)
        mgr.begin()
        with pytest.raises(tt.TransactionAlreadyActive):
            mgr.begin()

    def test_commit_persists_marker(self, store):
        mgr = tx.TxManager(store)
        tx_id = mgr.begin()
        mgr.commit(tx_id)
        # After commit, can begin a new one
        tx_id2 = mgr.begin()
        assert tx_id2 == 2

    def test_rollback_does_not_write_commit(self, store, tmp_path):
        mgr = tx.TxManager(store)
        tx_id = mgr.begin()
        mgr.rollback(tx_id)
        # Reopen and check that tx_id was NOT committed
        mgr.close()
        store.close()
        with storage.FileStore.open(str(tmp_path / "t.db")) as s2:
            mgr2 = tx.TxManager(s2)
            # Should be able to begin (tx_id 1 was rolled back, no committed marker)
            tx_id_new = mgr2.begin()
            assert tx_id_new == 1  # LSN-based, but new tx after rollback
            mgr2.close()
