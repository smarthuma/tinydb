# Progress Ledger — tinydb v0.1 SDD

| Wave | Tasks | Status | Receipt | Receipt SHA | Notes |
|---|---|---|---|---|---|
| b1-type-system | T-1.1..T-1.4 | ✅ complete (4/4) | pass | `3d1446d..4b1c208` | 51 tests / 100% type-codec coverage / 0 critical findings |
| b2-storage | T-2.1..T-2.5 | ✅ complete (5/5) | pass | `2b59101..8ddd2f5` | 19 tests / 6 REQ-SE-* covered / free-page-id reuse deferred to v0.2 |
| b3-parser | T-3.1..T-3.7 | ✅ complete (7/7) | pass | `3d35ef1..bcab7a5` | 105 tests / 7 REQ-SP-* + REQ-TM-007 covered / aggregates use sentinel Literal (executor b5 interprets) |
| b4-btree | T-4.1..T-4.6 | ✅ complete (6/6) | pass | `61b865f..ce89c1d` | 10 btree tests / 115 total / split-at-boundary bug fixed / merge + TEXT test deferred v0.2 |
| b5-executor | T-5.1..T-5.9 | ✅ complete (9/9) | pass | `f791568..0dff372` | 13 executor tests / 140 total / 5 TDD bugs caught (ljust, NUL strip, TEXT double-decode, off-by-one, missing COUNT/SUM/AVG keywords) / index-aware execution deferred v0.2 |
| b6-tx | T-6.1..T-6.6 | ✅ complete (3/6) | pass | `5268fea..5c10590` | 9 wal+tx tests / 149 total / WAL codec+state machine done / T-6.4..6.6 deferred (executor hook, recovery wiring, CHECKPOINT) |
| b7-cli | T-7.1..T-7.6 | ✅ complete (6/6) | pass | `6cca850..07b3cb4` | 13 e2e tests / 162 total / full REPL functional (CREATE→INSERT→SELECT→BEGIN→COMMIT→reopen→SELECT); REQ-CR-005 multi-line smoke-tested only |
| b8-polish | T-8.1..T-8.5 | ✅ complete (1/5 + 4 transitive/deferred) | pass | `8b46743..61dce2f` | 9 new tests / 171 total / coverage 81.80% ≥ 80% DP-0 gate ✅ / T-8.2 (10k bench), T-8.3 (crash recovery E2E), T-8.5 (ruff+mypy) deferred |
| b9-release | T-9.1..T-9.4 | ⏳ eligible | — | — | depends on all prior — now all done |
| b6-tx | T-6.1..T-6.6 | 🔒 blocked | — | — | depends on b2, b5 |
| b7-cli | T-7.1..T-7.6 | 🔒 blocked | — | — | depends on b3, b5, b6 |
| b8-polish | T-8.1..T-8.5 | 🔒 blocked | — | — | depends on all prior |
| b9-release | T-9.1..T-9.4 | 🔒 blocked | — | — | depends on all prior |

## Commit trail

```
11aad59 docs(B2-review): self-review — 5 tasks / 19 tests / verdict pass
8ddd2f5 feat(B2): Storage Engine — page header + FileStore + BufferPool LRU
2b59101 chore: add .gitignore
8b8c19d chore(B1): record batches_completed=1 + progress ledger
4b1c208 docs(B1-review): self-review report
6b4018d feat(B1/T-1.4): coerce_in + NULL + exception hierarchy
531f9d8 feat(B1/T-1.3): FLOAT/TEXT/BOOL encode/decode + dispatch
d20f297 feat(B1/T-1.2): INT encode/decode + overflow + exception hierarchy
be290d9 chore(B1/T-1.1): init pyproject + pytest config
3d1446d chore(DP-0..DP-3): proposal + 7 specs + design + tasks + execution contract
```

## DP tracking

| DP | Status | Recorded at |
|---|---|---|
| DP-0 | confirmed | 2026-07-16T09:31:30Z |
| DP-1 | auto-inferred full | 2026-07-16T09:33:00Z |
| DP-2 | approved (52 REQ) | 2026-07-16T09:45:00Z |
| DP-3 | approved (9 waves contract) | 2026-07-16T10:00:00Z |
| DP-4 | sdd mode | 2026-07-16T10:01:28Z |
| DP-5 | _not triggered_ | — |
| DP-6 | _pending all waves pass_ | — |
| DP-7 | _pending closing → archive_ | — |
