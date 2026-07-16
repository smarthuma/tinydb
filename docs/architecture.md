# Architecture — tinydb v0.1

Cross-reference between each spec scenario and the implementing module.
For design rationale, see `changes/tinydb-v0.1/design.md`.

## Layer Map

```
SQL text
   │
   ▼
tinydb.parser.lexer    → Token stream
tinydb.parser.parser   → AST (frozen dataclasses)
tinydb.parser.ast      → AST node types
   │
   ▼
tinydb.executor        → catalog / heap / predicates / aggregates
   │
   ├─→ tinydb.types        (INT/FLOAT/TEXT/BOOL encode/decode)
   ├─→ tinydb.storage      (4 KiB pages, BufferPool LRU, fsync)
   ├─→ tinydb.index        (B+ tree on dedicated INDEX pages)
   └─→ tinydb.tx + wal     (BEGIN/COMMIT/ROLLBACK + WAL records)
   │
   ▼
Single .db file (+ .db-wal sibling)
```

## Spec-to-Module Cross-Reference

| Spec | Scenarios | Module(s) |
|---|---|---|
| `specs/sql-parser/spec.md` | REQ-SP-001..007 | `tinydb/parser/lexer.py`, `parser/parser.py`, `parser/ast.py` |
| `specs/storage-engine/spec.md` | REQ-SE-001..006 | `tinydb/storage.py` |
| `specs/query-executor/spec.md` | REQ-QE-001..010 | `tinydb/executor.py` (+ heap in same file) |
| `specs/btree-index/spec.md` | REQ-BT-001..008 | `tinydb/index.py` |
| `specs/transaction-manager/spec.md` | REQ-TM-001..007 | `tinydb/tx.py`, `wal.py` (tx-control AST in `parser/ast.py`) |
| `specs/type-system/spec.md` | REQ-TS-001..007 | `tinydb/types.py` |
| `specs/cli-repl/spec.md` | REQ-CR-001..007 | `tinydb/cli.py` (entry point in `__main__`) |

## Files

```
tinydb/
├── __init__.py             re-exports Database, TinyDBError, etc.
├── types.py                INT/FLOAT/TEXT/BOOL codec + exception hierarchy
├── storage.py              Page, FileStore, BufferPool LRU
├── index.py                BPlusTree (leaf/internal codec + seek/range/split/merge)
├── wal.py                  WalRecord codec + append + replay
├── tx.py                   TxManager BEGIN/COMMIT/ROLLBACK
├── executor.py             catalog (header-page JSON) + heap + DDL/DML/aggregates
├── cli.py                  argparse entry + REPL loop + dot-commands
└── parser/
    ├── __init__.py
    ├── lexer.py            tokenize() with (line, col) + string + comments
    ├── parser.py           recursive-descent parser
    └── ast.py              frozen dataclasses for every Statement/Expr/Predicate

tests/
├── unit/                   pytest test_*.py
└── e2e/                    subprocess + in-process CLI tests
```

## Known Gaps (deferred to v0.2)

- `Wal.replay()` is implemented but not invoked from `FileStore.open()`
- B+ Tree leaf-level delete does not trigger merge / redistribute
- `SELECT *` projection not implemented (explicit columns only)
- Index-aware execution path is not wired (executor always heap-scans)
- `CHECKPOINT` SQL command not yet parsed
- TEXT B+ tree ordering test missing (codec path exists)
