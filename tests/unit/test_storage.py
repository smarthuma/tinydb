"""T-2.1 tests: page header codec — 9 bytes (page_id u32 + page_type u8 + lsn u32)."""
from __future__ import annotations

import pytest

from tinydb import storage


class TestPageHeaderRoundtrip:
    def test_basic(self) -> None:
        raw = storage.pack_header(page_id=7, page_type=2, lsn=42)
        page_id, page_type, lsn = storage.unpack_header(raw)
        assert page_id == 7
        assert page_type == 2
        assert lsn == 42

    def test_zero_values(self) -> None:
        raw = storage.pack_header(page_id=0, page_type=0, lsn=0)
        page_id, page_type, lsn = storage.unpack_header(raw)
        assert (page_id, page_type, lsn) == (0, 0, 0)

    def test_max_page_id(self) -> None:
        raw = storage.pack_header(page_id=2**32 - 1, page_type=1, lsn=0)
        assert storage.unpack_header(raw)[0] == 2**32 - 1

    def test_max_lsn(self) -> None:
        raw = storage.pack_header(page_id=0, page_type=0, lsn=2**32 - 1)
        assert storage.unpack_header(raw)[2] == 2**32 - 1


class TestPageHeaderWidth:
    def test_header_is_9_bytes(self) -> None:
        # 4 (page_id) + 1 (page_type) + 4 (lsn) = 9
        assert len(storage.pack_header(0, 0, 0)) == 9

    def test_unpack_rejects_wrong_size(self) -> None:
        with pytest.raises(ValueError):
            storage.unpack_header(b"\x00" * 8)
        with pytest.raises(ValueError):
            storage.unpack_header(b"\x00" * 10)


class TestPageClass:
    def test_page_carries_header_and_body(self) -> None:
        body = b"hello world"
        p = storage.Page(page_id=3, page_type=2, body=body, lsn=10)
        assert p.page_id == 3
        assert p.page_type == 2
        assert p.body == body
        assert p.lsn == 10

    def test_page_serialization(self) -> None:
        # 9-byte header + body, total page_size bytes (default 4096)
        p = storage.Page(page_id=5, page_type=1, body=b"\x00" * 4087, lsn=0)
        raw = p.serialize(page_size=4096)
        assert len(raw) == 4096
        # First 9 bytes are the header
        assert storage.unpack_header(raw[:9]) == (5, 1, 0)
        # Body is zero-padded
        assert raw[9:] == b"\x00" * 4087

    def test_page_serialization_short_body_pads(self) -> None:
        p = storage.Page(page_id=0, page_type=0, body=b"abc", lsn=0)
        raw = p.serialize(page_size=16)
        assert len(raw) == 16
        assert raw[9:12] == b"abc"
        assert raw[12:16] == b"\x00\x00\x00\x00"

    def test_page_serialization_rejects_oversize_body(self) -> None:
        p = storage.Page(page_id=0, page_type=0, body=b"x" * 4096, lsn=0)
        with pytest.raises(ValueError):
            p.serialize(page_size=4096)


class TestBufferPoolLRU:
    def _make_pool(self, store: storage.FileStore, capacity: int = 4) -> storage.BufferPool:
        return storage.BufferPool(store, capacity=capacity)

    def test_get_loads_from_store(self, tmp_path):
        path = tmp_path / "t.db"
        with storage.FileStore.open(str(path)) as store:
            pid = store.alloc_page(storage.PAGE_TYPE_TABLE)
            pool = self._make_pool(store, capacity=4)
            page = pool.get(pid)
            assert page.page_id == pid

    def test_lru_evicts_unpinned(self, tmp_path):
        path = tmp_path / "t.db"
        with storage.FileStore.open(str(path)) as store:
            pids = [store.alloc_page(storage.PAGE_TYPE_TABLE) for _ in range(5)]
            pool = self._make_pool(store, capacity=3)
            for pid in pids[:3]:
                pool.get(pid)
                pool.unpin(pid)
            # 5th get triggers eviction of the LRU (which is pids[0])
            pool.get(pids[3])
            # Now pids[0] should not be in pool
            assert not pool.contains(pids[0])
            # pids[3] should be in pool
            assert pool.contains(pids[3])

    def test_pinned_pages_never_evicted(self, tmp_path):
        path = tmp_path / "t.db"
        with storage.FileStore.open(str(path)) as store:
            pids = [store.alloc_page(storage.PAGE_TYPE_TABLE) for _ in range(5)]
            pool = self._make_pool(store, capacity=2)
            # Pin pids[0] and pids[1]
            pool.get(pids[0])
            pool.get(pids[1])
            # No eviction possible; trying to get pids[2] should not evict a pinned page
            pool.get(pids[2])
            # Both pinned pages must still be reachable
            assert pool.contains(pids[0])
            assert pool.contains(pids[1])

    def test_dirty_pages_flushed_on_evict(self, tmp_path):
        path = tmp_path / "t.db"
        with storage.FileStore.open(str(path)) as store:
            pid = store.alloc_page(storage.PAGE_TYPE_TABLE)
            pool = self._make_pool(store, capacity=1)
            page = pool.get(pid)
            page.body = b"DIRTY DATA" + b"\x00" * (store.page_size - 9 - 10)
            pool.mark_dirty(pid)
            pool.unpin(pid)
            # Force eviction by accessing another page
            pid2 = store.alloc_page(storage.PAGE_TYPE_TABLE)
            pool.get(pid2)
            # Read back from disk — should reflect the dirty write
            reloaded = store.read_page(pid)
            assert reloaded.body.startswith(b"DIRTY DATA")

    def test_flush_all_writes_all_dirty(self, tmp_path):
        path = tmp_path / "t.db"
        with storage.FileStore.open(str(path)) as store:
            pids = [store.alloc_page(storage.PAGE_TYPE_TABLE) for _ in range(3)]
            pool = self._make_pool(store, capacity=10)
            for i, pid in enumerate(pids):
                page = pool.get(pid)
                page.body = f"page-{i}".encode().ljust(store.page_size - 9, b"\x00")
                pool.mark_dirty(pid)
                pool.unpin(pid)
            pool.flush_all()
            for i, pid in enumerate(pids):
                reloaded = store.read_page(pid)
                assert reloaded.body.startswith(f"page-{i}".encode())


class TestAllocFreeFsync:
    def test_alloc_returns_distinct_ids(self, tmp_path):
        path = tmp_path / "t.db"
        with storage.FileStore.open(str(path)) as store:
            ids = {store.alloc_page(storage.PAGE_TYPE_TABLE) for _ in range(10)}
            assert len(ids) == 10

    def test_fsync_persists(self, tmp_path):
        path = tmp_path / "t.db"
        with storage.FileStore.open(str(path)) as store:
            pid = store.alloc_page(storage.PAGE_TYPE_TABLE)
            page = store.read_page(pid)
            page.body = b"after fsync" + b"\x00" * (store.page_size - 9 - 11)
            store.write_page(page)
            store.fsync()
        # Reopen
        with storage.FileStore.open(str(path)) as store2:
            reloaded = store2.read_page(pid)
            assert reloaded.body.startswith(b"after fsync")


class TestSingleFilePersistence:
    def test_reopen_preserves_data(self, tmp_path):
        path = tmp_path / "t.db"
        # Session 1: write a page
        with storage.FileStore.open(str(path)) as store:
            pid = store.alloc_page(storage.PAGE_TYPE_TABLE)
            page = store.read_page(pid)
            payload = b"PERSISTED-DATA"
            page.body = payload + b"\x00" * (store.page_size - 9 - len(payload))
            store.write_page(page)
            store.fsync()
        # Session 2: reopen and read back
        with storage.FileStore.open(str(path)) as store2:
            reloaded = store2.read_page(pid)
            assert reloaded.body.startswith(payload)

    def test_no_extra_files_created(self, tmp_path):
        path = tmp_path / "t.db"
        with storage.FileStore.open(str(path)) as store:
            pid = store.alloc_page(storage.PAGE_TYPE_TABLE)
            page = store.read_page(pid)
            page.body = b"x" * 100 + b"\x00" * (store.page_size - 9 - 100)
            store.write_page(page)
            store.fsync()
        siblings = sorted(p.name for p in tmp_path.iterdir())
        # Only the .db file should be present (no WAL, no journal, no lock, no tmp)
        assert siblings == ["t.db"]
