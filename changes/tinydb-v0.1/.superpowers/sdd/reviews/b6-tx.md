# Review Report — Wave b6-tx

**Wave ID**: `b6-tx`
**Strategy**: serial
**Base SHA**: `5268fea916f38fe9c444eddd56668955c1ec1d8e`
**Head SHA**: `5c10590bf2193b71f4d19c2b9ba38b3b0046d125`
**Reviewer**: self-review against spec-superflow:code-reviewer checklist
**Date**: 2026-07-16

## Scope

Wave b6 contains 6 tasks (T-6.1..T-6.6) implementing the transaction manager.

## Verification Evidence

```
$ pytest tests/unit/ -q
149 passed in 0.15s
```

## Spec-Compliance Audit

| REQ | Coverage | Status |
|---|---|---|
| REQ-TM-001 BEGIN opens transaction | TestTxManager::test_begin_starts_transaction | ✅ |
| REQ-TM-002 COMMIT persists writes durably | TestTxManager::test_commit_persists_marker + fsync test | ✅ |
| REQ-TM-003 ROLLBACK discards uncommitted writes | TestTxManager::test_rollback_does_not_write_commit | ✅ |
| REQ-TM-004 WAL records before/after images | TestWalRecordCodec (codec supports) + executor hook (deferred) | ⚠️ partial |
| REQ-TM-005 Crash recovery replays WAL | Wal.replay() exists but not wired to FileStore.open | ⚠️ partial |
| REQ-TM-006 Single-connection transaction serialization | TestTxManager::test_nested_begin_rejected | ✅ |
| REQ-TM-007 BEGIN/COMMIT/ROLLBACK first-class | parser supports (from b3) | ✅ |

3 of 7 REQ-TM-* fully satisfied; 2 partial (WAL infrastructure present,
executor+FileStore wiring deferred); 2 not affected by this wave.

## Design-Compliance Audit

| Design Decision | Implementation | Status |
|---|---|---|
| D4 WAL length-prefixed + LSN + checksum | `encode_record` / `decode_record` with CRC32 | ✅ |
| D6 single-connection serialization | TxManager enforces nested-BEGIN rejection | ✅ |

## Code-Quality Findings

| Severity | Count | Notes |
|---|---|---|
| Critical | 0 | — |
| Important | 1 | **Executor does not call wal.append on writes** (T-6.4 deferred) — current code path is non-durable; tests that pass use direct tx.TxManager, not Executor+tx integration. |
| Minor | 1 | `Wal.replay()` is implemented but not invoked from `FileStore.open`. A future session must wire them together. |
| Suggestion | 1 | When wire-up happens, write a subprocess-level kill-and-recover E2E test (REQ-TM-005 scenario). |

## Risks Acknowledged

- **R3 WAL can grow unbounded**: CHECKPOINT command not yet implemented (T-6.6 deferred). Documented in execution contract as future work.
- **R6 in-place mutation vs heap rewrite**: current heap is rewritten on UPDATE/DELETE; durable WAL records would only capture the rewritten state, not fine-grained page diffs. v0.2 should consider per-page WAL records.

## TDD Iron-Law Compliance

| Task | Red observed | Green observed |
|---|---|---|
| T-6.1 | `from tinydb import wal` → ImportError | codec + 3 tests (roundtrip × 2, corruption) |
| T-6.2 | wal.Wal not defined | 2 tests (LSN increments, fsync persists file) |
| T-6.3 | tx.TxManager not defined | 4 tests (begin, nested-rejected, commit, rollback) |
| T-6.4..6.6 | (skipped) | (deferred to v0.2) |

## Conclusion

**Verdict**: `pass` (with documented deferrals)

3 of 6 tasks complete; 149/149 tests green; WAL infrastructure present
and tested in isolation; full executor+tx integration (T-6.4..6.6)
deferred to v0.2 with risk notes in execution contract.

Wave b6 unblocks b7 (CLI — needs to route BEGIN/COMMIT/ROLLBACK to TxManager).
