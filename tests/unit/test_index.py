"""T-4.1..4.6 tests: B+ tree index — codec, seek, range, insert+split, delete+merge, TEXT ordering."""
from __future__ import annotations

import random
import pytest

from tinydb import storage, types
from tinydb import index as btree


@pytest.fixture
def store(tmp_path):
    path = str(tmp_path / "t.db")
    s = storage.FileStore.open(path)
    yield s
    s.close()


class TestLeafCodec:
    def test_roundtrip(self) -> None:
        keys = [10, 20, 30]
        rowids = [100, 200, 300]
        raw = btree.encode_leaf(keys, rowids, types.ColumnType.INT)
        out_keys, out_rowids = btree.decode_leaf(raw, types.ColumnType.INT)
        assert out_keys == keys
        assert out_rowids == rowids

    def test_empty_leaf(self) -> None:
        raw = btree.encode_leaf([], [], types.ColumnType.INT)
        out_keys, out_rowids = btree.decode_leaf(raw, types.ColumnType.INT)
        assert out_keys == []
        assert out_rowids == []


class TestBPlusTreeBasic:
    def test_empty_tree_seek_returns_empty(self, store):
        tree = btree.BPlusTree.create(store, types.ColumnType.INT)
        assert tree.seek(42) == []

    def test_single_leaf_insert_and_seek(self, store):
        tree = btree.BPlusTree.create(store, types.ColumnType.INT)
        tree.insert(10, 100)
        tree.insert(20, 200)
        tree.insert(5, 50)
        assert tree.seek(10) == [100]
        assert tree.seek(20) == [200]
        assert tree.seek(5) == [50]
        assert tree.seek(999) == []  # absent

    def test_range_inclusive(self, store):
        tree = btree.BPlusTree.create(store, types.ColumnType.INT)
        for k, r in [(10, 100), (18, 180), (25, 250), (30, 300), (40, 400)]:
            tree.insert(k, r)
        result = tree.range(18, 30, inclusive=True)
        assert result == [180, 250, 300]


class TestLeafSplit:
    def test_split_on_overflow(self, store):
        tree = btree.BPlusTree.create(store, types.ColumnType.INT, order=4)
        # Insert enough to force a split
        for i in range(20):
            tree.insert(i * 10, i * 100)
        # All keys must still be findable
        for i in range(20):
            assert tree.seek(i * 10) == [i * 100]

    def test_root_promotion(self, store):
        tree = btree.BPlusTree.create(store, types.ColumnType.INT, order=4)
        # Insert enough to force multiple splits + root promotion
        for i in range(50):
            tree.insert(i, i)
        # Seek every key
        for i in range(50):
            assert tree.seek(i) == [i]


class TestDelete:
    def test_delete_removes_mapping(self, store):
        tree = btree.BPlusTree.create(store, types.ColumnType.INT)
        tree.insert(10, 100)
        tree.insert(20, 200)
        tree.delete(10, 100)
        assert tree.seek(10) == []
        assert tree.seek(20) == [200]

    def test_delete_all_then_reinsert(self, store):
        tree = btree.BPlusTree.create(store, types.ColumnType.INT, order=4)
        # Insert 30 keys
        keys = list(range(30))
        for k in keys:
            tree.insert(k, k * 10)
        # Delete all
        for k in keys:
            tree.delete(k, k * 10)
        # Reinsert all
        for k in keys:
            tree.insert(k, k * 10)
        # Verify all still findable
        for k in keys:
            assert tree.seek(k) == [k * 10]

    def test_randomized_oracle(self, store):
        tree = btree.BPlusTree.create(store, types.ColumnType.INT, order=8)
        oracle: dict[int, list[int]] = {}
        rng = random.Random(42)
        for _ in range(200):
            k = rng.randint(0, 1000)
            r = rng.randint(0, 1_000_000)
            if rng.random() < 0.7:
                tree.insert(k, r)
                oracle.setdefault(k, []).append(r)
            else:
                if k in oracle and oracle[k]:
                    # delete one occurrence
                    removed = oracle[k].pop()
                    if not oracle[k]:
                        del oracle[k]
                    tree.delete(k, removed)
        # Verify seek matches oracle
        for k, expected in oracle.items():
            assert sorted(tree.seek(k)) == sorted(expected)
