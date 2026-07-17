# Design: tinydb

## Context

### Current state

- The repository `/home/wfj/新建文件夹/开发tinydb/` contains no implementation code; it holds only the proposal (`tinydb-proposal.md`) and a team communication note (`需求沟通.md`).
- This is a clean-slate v0.1 build. No migration, no legacy storage format, and no concurrent users to support.
- All seven capabilities — SQL parser, storage engine, query executor, B+ tree index, transaction manager, type system, CLI/REPL — must be implemented from scratch and then composed into a single `tinydb` Python package.

### Constraints (from DP-0)

- **Python 3.10+** runtime; the package MUST work on the standard library only (zero third-party dependencies at import time).
- **Single-file persistence**: one `.db` file holds data, catalog, indexes, and WAL records.
- **B+ tree index** keyed by column values; default order is chosen so 10k rows fit in a 2–3 level tree.
- **WAL-based ACID**; recovery replays WAL on open.
- **pytest coverage ≥ 80%** across the package, plus CLI/REPL E2E tests that drive the real `tinydb` binary.
- **git + spec-superflow discipline**: every commit traces to a DP, and all 7 decision points (`dp_0`..`dp_7`) appear in `.spec-superflow.yaml`.

### Stakeholders

- **Self / developer** learning database internals by building.
- **Future contributors** who will read the code as a teaching artifact — clarity matters as much as correctness.
- **Spec-driven agents** (this skill, build-executor, code-reviewer, release-archivist) that need every decision to be explicit and discoverable.

## Goals

1. **Correctness**: every SHALL/MUST in `specs/*/spec.md` is satisfied and verifiable by a passing pytest scenario.
2. **Teachability**: each module is small enough (≤ ~300 LOC) to be read end-to-end in one sitting, with one well-named class or function per concept.
3. **Composability**: the layers (parser → AST → executor → storage / index / tx / types) communicate through typed Python objects, not string-keyed dicts.
4. **Recoverability**: a kill -9 between any two operations leaves the database in a state equivalent to "all committed transactions applied".
5. **Operability**: the CLI/REPL behaves predictably — errors never crash the REPL, multi-line input works, and stdin batch mode is deterministic.
6. **Testability**: 80%+ line coverage, E2E coverage of every CLI/REPL requirement, no test depends on a real clock or network.
7. **Tracability**: every code change can be traced to a spec scenario; every spec scenario has at least one test; `.spec-superflow.yaml` records all 7 DPs.

## Decisions

### Decision D1: Package layout — flat `tinydb/` module tree

- **Choice**: one Python package `tinydb/` with submodules `parser`, `executor`, `storage`, `index`, `tx`, `types`, `cli`, plus a top-level `Database` class in `__init__.py`.
- **Rationale**: a flat package matches the seven capabilities one-to-one, makes imports obvious (`from tinydb.storage import Page`), and lets pytest discover tests by mirroring the tree.
- **Alternatives considered**:
  - One mega-module `tinydb.py` — rejected because it would balloon past 1000 LOC and hide layering.
  - Namespace packages across multiple top-level names (`tinydb_parser`, `tinydb_storage`) — rejected as it splits the public API and forces users to remember two import paths.

### Decision D2: Page format — 4096 bytes default, little-endian, structured header

- **Choice**: each page is exactly 4096 bytes (configurable 512–65536), starts with an 8-byte header `[page_id u32 | page_type u8 | lsn u32]`, and the remaining bytes are the page body. All multi-byte fields use little-endian.
- **Rationale**: 4 KiB matches SQLite's default and balances I/O efficiency against heap fragmentation. Little-endian is the dominant x86/ARM convention and matches Python's `int.to_bytes(..., 'little')`.
- **Alternatives considered**:
  - Variable-length pages — rejected because fixed-size pages simplify buffer-pool math and free-page lookup.
  - Big-endian — rejected for no practical benefit on the target architectures.

### Decision D3: B+ tree parameters — order 64, leaf/internal split-and-merge rebalancing

- **Choice**: the B+ tree defaults to order 64 (max 63 keys per node, 64 children per internal node). On overflow a node splits; on underflow (after delete) it merges with a sibling or redistributes keys. Both keys and child pointers live inside a single page, falling back to overflow pages only if a single value exceeds the page body.
- **Rationale**: with order 64 and 8-byte keys + 8-byte rowids, each leaf holds ~250 entries; 10k rows fit in a tree of height 2. Splits and merges are straightforward to implement and to test.
- **Alternatives considered**:
  - Order 16 (more conservative, simpler splits) — rejected because it pushes the tree to height 4 for 10k rows and doubles page-count.
  - No rebalancing (lazy deletion) — rejected because it violates the search-property invariants in REQ-BT-006 and degrades lookup time.

### Decision D4: WAL format — append-only length-prefixed records, flushed before page write

- **Choice**: each WAL record is `[len u32 | lsn u32 | page_id u32 | page_type u8 | before_image | after_image | checksum u32]`, written by appending to `<file.db>-wal`. A `commit` record `[len u32 | 'COMMIT' | tx_id u64 | checksum]` terminates a transaction.
- **Rationale**: append-only WAL gives crash recovery a single forward pass; the length prefix lets recovery skip corrupted records; the checksum lets it detect torn writes. Before/after images make both undo (for rolled-back txns) and redo (for committed txns) cheap.
- **Alternatives considered**:
  - Shadow paging (whole-page replacement) — rejected because it complicates the buffer pool and would double write amplification.
  - Logical WAL (only the operation, not the page image) — rejected because the engine is small enough that page-image WAL is simpler and easier to test.

### Decision D5: Catalog in the header page, page 1

- **Choice**: the header page (always page id 1) holds the catalog: a list of `(table_name, schema, root_data_page_id, root_index_page_ids)`. A small free-page list is also kept here while the file fits; once it grows, a dedicated `SYSTEM` page chain takes over.
- **Rationale**: co-locating the catalog with the file header keeps open-time work to a single page read; schema is always in one well-known place.
- **Alternatives considered**:
  - Catalog as a B+ tree keyed by table name — rejected as overkill for v0.1 (a few dozen tables per database is the realistic ceiling).
  - Separate `<file.db>-catalog` file — rejected because it violates the single-file persistence constraint.

### Decision D6: Single-connection transaction serialization, no lock manager

- **Choice**: only one transaction may be open at a time per database file. A second `BEGIN` raises `TransactionAlreadyActive`. There is no lock manager, no deadlock detection, and no MVCC.
- **Rationale**: this matches the proposal's "Out of scope: concurrency control" decision and keeps the transaction manager under ~300 LOC. It is the simplest correct semantics for an embedded single-user database.
- **Alternatives considered**:
  - Reader-writer locks for shared readers — rejected as over-engineering for v0.1.
  - Optimistic MVCC — rejected because it would require a multi-version page store and complicate the WAL format.

### Decision D7: AST as dataclasses, not dicts

- **Choice**: every SQL node is a `@dataclass(frozen=True)` (e.g. `CreateTable`, `Select`, `BinaryOp`). Visitors carry a `Connection` (or `Executor`) reference and call into the storage/index/types layers through typed method signatures.
- **Rationale**: dataclasses give free `__eq__` / `__repr__`, which makes parser tests and executor tests trivial; type-checkers (mypy in CI, not runtime) catch wiring mistakes early.
- **Alternatives considered**:
  - `TypedDict` / plain `dict` — rejected because field-name typos would only surface at runtime.
  - `attrs` / `pydantic` — rejected because v0.1 sticks to stdlib.

### Decision D8: Errors as a small exception hierarchy

- **Choice**: a single base `TinyDBError(Exception)` and concrete subclasses (`ParseError`, `TypeMismatch`, `UniqueViolation`, `NotNullViolation`, `TableNotFound`, `UnsafeDeleteWithoutWhere`, `IntegerOverflow`, `TransactionAlreadyActive`, `PageCorrupt`, `TransactionLogCorrupt`).
- **Rationale**: callers can either catch `TinyDBError` for "any DB problem" or a specific subclass for precise handling. The REPL prints the message verbatim; batch mode exits non-zero.
- **Alternatives considered**:
  - Return-result-as-error — rejected because it does not compose with Python's `try/except` and forces every callsite to remember to check.
  - A single string error code — rejected because it loses type information.

## Risks And Trade-Offs

- **Risk R1**: Storage engine bugs can corrupt the `.db` file silently. **Mitigation**: every page read verifies the header magic and (where present) the page checksum; WAL recovery fails loudly if any record's checksum is bad. **Trade-off**: ~3% throughput overhead for checksumming.

- **Risk R2**: B+ tree split/merge logic is the most bug-prone code path. **Mitigation**: each operation has its own pytest file with hand-crafted trees (3, 7, 31, 255 nodes) and randomized property tests (insert N random keys, delete all, re-insert, compare with a Python `SortedDict` oracle). **Trade-off**: roughly 25% of the test suite is index tests.

- **Risk R3**: Single-file WAL can grow unbounded if the database is used heavily without `CHECKPOINT`. **Mitigation**: v0.1 ships a `CHECKPOINT` SQL command that truncates the WAL after rewriting committed pages; recovery is still possible from the truncated WAL until the next transaction. **Trade-off**: `CHECKPOINT` is single-threaded and locks the file for its duration; fine for embedded usage.

- **Risk R4**: Parser error recovery is shallow — a syntax error in the middle of a multi-statement script aborts the rest. **Mitigation**: REPL accepts single statements only, so this only matters for stdin batch mode; batch mode documents the "fail fast" semantics in REQ-CR-007.

- **Risk R5**: 80% coverage is enforced by CI but does not guarantee mutation score. **Mitigation**: code review (skill: `spec-superflow:code-reviewer`) explicitly checks for empty `except:` blocks, untested error paths, and asserts that only exercise the happy path.

- **Risk R6**: The CLI REPL uses `input()` which is not pytest-friendly. **Mitigation**: REPL reads from any `Readable` stream (`sys.stdin` by default, injectable for tests), and a dedicated `tests/e2e/test_cli_repl.py` drives it via `subprocess` with a pty where needed.

- **Risk R7**: `0` / `1` being rejected as BOOL is surprising to users coming from MySQL/Postgres. **Mitigation**: documented in `README.md` and surfaced as `TypeMismatch(column, expected='BOOL', got='INT')` with a hint to cast explicitly. **Trade-off**: a small ergonomic cost for strict typing.

- **Risk R8**: No multi-table queries / no JOINs. **Mitigation**: this is a deliberate DP-0 scope decision; v0.2 may add it. The executor's `Select` AST already carries a `from_tables` list, so the extension is local rather than a redesign.
