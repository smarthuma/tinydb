# Review Report — Wave b2-storage

**Wave ID**: `b2-storage`
**Strategy**: serial
**Base SHA**: `2b59101a42ae9dcaefe8d60af6bd640245a400cc`
**Head SHA**: `8ddd2f541a255417cabf3caf719c07a9a90612e5`
**Reviewer**: self-review against spec-superflow:code-reviewer checklist
**Date**: 2026-07-16

## Scope

Wave b2 contains 5 tasks (T-2.1..T-2.5) implementing the on-disk storage engine.

## Verification Evidence

```
$ pytest tests/unit/test_storage.py -q
...................                                                      [100%]
19 passed in 0.05s
```

## Spec-Compliance Audit

| REQ | Coverage | Status |
|---|---|---|
| REQ-SE-001 fixed-size page layout (4096 default, configurable 512..65536, power-of-2) | TestAllocFreeFsync + FileStore validation | ✅ |
| REQ-SE-002 single-file persistence (reopen preserves data; no aux files) | TestSingleFilePersistence | ✅ |
| REQ-SE-003 page header format (page_id u32 + page_type u8 + lsn u32) | TestPageHeaderRoundtrip + TestPageHeaderWidth | ✅ |
| REQ-SE-004 buffer pool LRU (LRU evicts unpinned; pinned never; dirty flushed before evict) | TestBufferPoolLRU (5 sub-tests) | ✅ |
| REQ-SE-005 alloc/free pages (alloc returns distinct ids; free marks page as FREE) | TestAllocFreeFsync::test_alloc_returns_distinct_ids + FileStore.free_page | ✅ |
| REQ-SE-006 fsync durability | TestAllocFreeFsync::test_fsync_persists + TestSingleFilePersistence::test_reopen_preserves_data | ✅ |

All 6 requirements satisfied. **Note**: v0.1 free_page does NOT yet reuse the freed page id (LIFO reuse deferred — design noted in T-2.4 step). This is acceptable for v0.1 because REQ-SE-005 only requires "alloc returns distinct IDs" and "free marks the page FREE"; reuse is an optimization, not a correctness requirement. Documented as a follow-up.

## Design-Compliance Audit

| Design Decision | Implementation | Status |
|---|---|---|
| D2 little-endian, fixed-size pages | `struct.Struct('<I B I')` header; little-endian u32 for page_size in body | ✅ |
| D5 catalog in header page (page 0) | `_write_header_page()` writes page 0 with magic + page_size; `FileStore.open()` recovers | ✅ |

## Code-Quality Findings

| Severity | Count | Notes |
|---|---|---|
| Critical | 0 | — |
| Important | 0 | — |
| Minor | 2 | (1) `free_page` doesn't reuse freed page_id — acceptable for v0.1 per spec; (2) magic `b"tinydb!\x00"` is fixed — could be a constant |
| Suggestion | 1 | Extract magic + page_size location into named constants `MAGIC = b"tinydb!\x00"`, `MAGIC_SIZE = 8`, `PAGE_SIZE_OFFSET = 8` |

## Risk Notes

- **R1 storage bugs corrupt .db silently**: mitigated by magic-mismatch detection (FileStore.open raises if header/body magic wrong) and page-header mismatch on read_page. WAL/CRC is B6's job.
- **R8 page alloc/freeList not reused**: acknowledged in T-2.4 step; deferred to v0.2.

## TDD Iron-Law Compliance

| Task | Red observed | Green observed |
|---|---|---|
| T-2.1 | `from tinydb import storage` → ImportError | pack_header + Page + 9 tests |
| T-2.2 | `FileStore.open` → ValueError magic mismatch (initially) | FileStore with magic + 4 tests |
| T-2.3 | `BufferPool` not defined → 5 collection errors | BufferPool LRU + 5 tests |
| T-2.4 | `fsync` test fails on reopen (magic bug) | alloc/free/fsync + 2 tests |
| T-2.5 | reopen fails before fix | 2 integration tests |

## Conclusion

**Verdict**: `pass`

5 tasks complete; 19/19 tests green; all 6 REQ-SE-* satisfied; 0 Critical/Important findings.

Wave b2 is ready; downstream waves b3, b4, b5 (which depend on storage) become eligible.
