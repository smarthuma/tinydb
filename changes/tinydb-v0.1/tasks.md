# Tasks: tinydb v0.1

## File Structure

All paths relative to the repository root (`/home/wfj/新建文件夹/开发tinydb/`).

| Path | Responsibility | Status |
|---|---|---|
| `pyproject.toml` | Package metadata, pytest config, Python 3.10+ requirement | Create |
| `tinydb/__init__.py` | Public re-exports: `Database`, `TinyDBError`, exception subclasses | Create |
| `tinydb/types.py` | INT/FLOAT/TEXT/BOOL encoders/decoders + type-mismatch exceptions | Create |
| `tinydb/storage.py` | Page, BufferPool, free-page list, fsync, single-file open/close | Create |
| `tinydb/wal.py` | WAL record encode/decode, append, truncation, recovery replay | Create |
| `tinydb/index.py` | B+ tree node types, split/merge, seek/range, INT/TEXT ordering | Create |
| `tinydb/parser/__init__.py` | Public `parse(sql: str) -> Statement` entry point | Create |
| `tinydb/parser/ast.py` | Frozen dataclasses for every SQL node | Create |
| `tinydb/parser/lexer.py` | Tokenizer with (line, column) positions | Create |
| `tinydb/parser/parser.py` | Recursive-descent parser producing AST | Create |
| `tinydb/executor.py` | Executes AST against storage/index/tx, owns catalog | Create |
| `tinydb/tx.py` | BEGIN/COMMIT/ROLLBACK state machine, single-connection lock | Create |
| `tinydb/cli.py` | `tinydb <file.db>` REPL + `--help`, `--version`, stdin batch | Create |
| `tests/unit/test_types.py` | Type encode/decode round-trip + coercion rules | Create |
| `tests/unit/test_storage.py` | Page header, alloc/free, buffer-pool LRU, fsync durability | Create |
| `tests/unit/test_wal.py` | WAL record encode/decode + recovery replay with injected faults | Create |
| `tests/unit/test_index.py` | B+ tree insert/delete/split/merge + INT/TEXT ordering | Create |
| `tests/unit/test_parser.py` | Every REQ-SP-001..007 scenario as a parser test | Create |
| `tests/unit/test_executor.py` | Every REQ-QE-001..010 scenario as an executor test | Create |
| `tests/unit/test_tx.py` | Every REQ-TM-001..007 scenario as a tx test | Create |
| `tests/e2e/test_cli_repl.py` | REPL dot-commands, multi-line, error non-fatal, batch stdin | Create |
| `tests/e2e/test_crash_recovery.py` | Kill between WAL flush and page flush; reopen verifies state | Create |
| `README.md` | Quickstart, REPL usage, scope, design pointers | Create |
| `docs/architecture.md` | Cross-reference to design.md and the seven spec files | Create |

Total: 24 files (22 Python, 1 TOML, 1 Markdown), 0 modifications of pre-existing files.

## Interfaces

Cross-batch contracts. Each interface is consumed by every task in batches that depend on the producer batch.

```text
tinydb.types.encode(value: object, column_type: ColumnType) -> bytes
tinydb.types.decode(raw: bytes, column_type: ColumnType) -> object
tinydb.types.coerce_in(value: object, column_type: ColumnType) -> object     # raises TypeMismatch / IntegerOverflow

tinydb.storage.Page(page_id: int, page_type: int, body: bytes, lsn: int = 0)
tinydb.storage.BufferPool(capacity: int = 128)
tinydb.storage.BufferPool.get(page_id: int) -> Page       # pins the page
tinydb.storage.BufferPool.put(page: Page) -> None        # marks dirty if needed
tinydb.storage.BufferPool.flush_all() -> None            # fsyncs all dirty pages
tinydb.storage.FileStore.open(path: str, page_size: int = 4096) -> FileStore
tinydb.storage.FileStore.alloc_page(page_type: int) -> int     # returns fresh page_id
tinydb.storage.FileStore.free_page(page_id: int) -> None
tinydb.storage.FileStore.read_page(page_id: int) -> bytes
tinydb.storage.FileStore.write_page(page_id: int, body: bytes) -> None
tinydb.storage.FileStore.fsync() -> None

tinydb.wal.Wal.append(record_type: str, payload: bytes) -> Lsn     # record_type in {"MUTATE","COMMIT","ROLLBACK"}
tinydb.wal.Wal.replay(store: FileStore) -> None
tinydb.wal.Wal.truncate() -> None

tinydb.index.BPlusTree.create(store: FileStore, key_type: ColumnType) -> BPlusTree
tinydb.index.BPlusTree.seek(key: object) -> list[int]
tinydb.index.BPlusTree.range(lo: object, hi: object, inclusive: bool) -> list[int]
tinydb.index.BPlusTree.insert(key: object, rowid: int) -> None
tinydb.index.BPlusTree.delete(key: object, rowid: int) -> None

tinydb.parser.parse(sql: str) -> Statement
tinydb.parser.Statement = CreateTable | DropTable | Insert | Select | Update | Delete | Begin | Commit | Rollback

tinydb.executor.Executor(store: FileStore, wal: Wal, pool: BufferPool)
tinydb.executor.Executor.execute(stmt: Statement) -> Result
tinydb.executor.Result = RowSet(rows: list[tuple]) | Count(n: int) | Ok()

tinydb.tx.TxManager(store: FileStore, wal: Wal)
tinydb.tx.TxManager.begin() -> TxId
tinydb.tx.TxManager.commit(tx_id: TxId) -> None
tinydb.tx.TxManager.rollback(tx_id: TxId) -> None

tinydb.cli.main(argv: list[str], stdin: Readable, stdout: Writable, stderr: Writable) -> int
```

## Tasks

Tasks are grouped into nine batches (B1..B9). Each batch lists every task with exact file paths, an **Interfaces** block (consumes / produces), a 5-step TDD plan (Red / Green / Refactor / Verify / Commit), and an explicit **Depends on**. Every step is sized at 2–5 minutes.

---

### Batch B1 — Type System (foundation)

#### T-1.1 Project skeleton
- **File**: `pyproject.toml`
- **Interfaces**:
  - Consumes: none
  - Produces: `pyproject.toml` declaring `name = "tinydb"`, `requires-python = ">=3.10"`, `[project.optional-dependencies] dev = ["pytest", "pytest-cov"]`
- **Steps**:
  1. Red — `pytest --version` fails (no project yet).
  2. Green — write minimal `pyproject.toml`; `pip install -e .[dev]` succeeds.
  3. Refactor — add `[tool.pytest.ini_options]` with `testpaths = ["tests"]`.
  4. Verify — `pytest --collect-only` succeeds and finds zero tests.
  5. Commit — `chore(B1): init pyproject + pytest config (DP-2 prep)`.
- **Depends on**: none.

#### T-1.2 ColumnType enum + INT encode/decode
- **File**: `tinydb/types.py`, `tests/unit/test_types.py`
- **Interfaces**:
  - Consumes: none
  - Produces: `tinydb.types.ColumnType` enum + `encode_int(value: int) -> bytes`, `decode_int(raw: bytes) -> int`
- **Steps**:
  1. Red — write `test_encode_int_roundtrip_negative` and `test_encode_int_overflow_raises`; both fail.
  2. Green — implement `ColumnType.INT = "INT"` and the encode/decode using `int.to_bytes(8, 'little', signed=True)`.
  3. Refactor — extract `_checked_i64` helper to share between encode and overflow check.
  4. Verify — both tests pass; no other tests broken.
  5. Commit — `feat(B1): INT encode/decode + overflow check (REQ-TS-001)`.
- **Depends on**: T-1.1.

#### T-1.3 FLOAT/TEXT/BOOL encode/decode
- **File**: `tinydb/types.py`, `tests/unit/test_types.py`
- **Interfaces**:
  - Consumes: `encode_int`, `decode_int`
  - Produces: `encode_float`, `decode_float`, `encode_text`, `decode_text`, `encode_bool`, `decode_bool`
- **Steps**:
  1. Red — write round-trip tests for `3.14`, `'你好, tinydb 🚀'`, `True`, `False`; all fail.
  2. Green — implement float via `struct.pack('<d', ...)`, text via `len u32 + utf-8 bytes`, bool via single byte `0`/`1`.
  3. Refactor — unify all encoders behind `encode(value, column_type)` and `decode(raw, column_type)` dispatch tables.
  4. Verify — round-trip + boundary tests pass.
  5. Commit — `feat(B1): FLOAT/TEXT/BOOL encode/decode (REQ-TS-002..004)`.
- **Depends on**: T-1.2.

#### T-1.4 Coercion + NULL handling + exception types
- **File**: `tinydb/types.py`, `tests/unit/test_types.py`
- **Interfaces**:
  - Consumes: encode/decode dispatch
  - Produces: `coerce_in(value, column_type)`; `None` round-trip; exception classes `TypeMismatch`, `IntegerOverflow`, `NotNullViolation`, `UniqueViolation`
- **Steps**:
  1. Red — write `test_bool_to_int_coerces`, `test_int_into_text_rejected`, `test_null_roundtrip`, `test_type_mismatch_carries_column`.
  2. Green — implement coercion per REQ-TS-006 and NULL per REQ-TS-005.
  3. Refactor — collect exception classes in a single block at top of module.
  4. Verify — all tests pass.
  5. Commit — `feat(B1): coerce_in + NULL + exception hierarchy (REQ-TS-005,006 + Decision D8)`.
- **Depends on**: T-1.3.

---

### Batch B2 — Storage Engine

#### T-2.1 Page header codec
- **File**: `tinydb/storage.py`, `tests/unit/test_storage.py`
- **Interfaces**:
  - Consumes: none
  - Produces: `Page` dataclass + `_pack_header(page_id, page_type, lsn) -> bytes`, `_unpack_header(raw) -> tuple`
- **Steps**:
  1. Red — write `test_page_header_roundtrip`; fails.
  2. Green — implement header codec with little-endian `'<I B I'` struct.
  3. Refactor — name constants (`HEADER_SIZE = 9`, page-type ints).
  4. Verify — round-trip test passes; rejects wrong page_type bytes.
  5. Commit — `feat(B2): page header codec (REQ-SE-003)`.
- **Depends on**: T-1.1.

#### T-2.2 FileStore: open/close + page read/write
- **File**: `tinydb/storage.py`, `tests/unit/test_storage.py`
- **Interfaces**:
  - Consumes: `Page`, header codec
  - Produces: `FileStore.open(path, page_size=4096)`, `read_page(id)`, `write_page(id, body)`
- **Steps**:
  1. Red — write `test_open_creates_header_page` + `test_write_then_read_roundtrip`; both fail.
  2. Green — implement open (allocates page 0 as header if new), read, write using `os.pread`/`pwrite`.
  3. Refactor — wrap file descriptor in a small context manager.
  4. Verify — both tests pass; file size grows by `page_size` per alloc.
  5. Commit — `feat(B2): FileStore open/read/write (REQ-SE-001, REQ-SE-002)`.
- **Depends on**: T-2.1.

#### T-2.3 BufferPool with LRU eviction
- **File**: `tinydb/storage.py`, `tests/unit/test_storage.py`
- **Interfaces**:
  - Consumes: `FileStore`
  - Produces: `BufferPool(capacity)`, `.get(id)`, `.put(page)`, `.flush_all()`
- **Steps**:
  1. Red — `test_lru_evicts_unpinned`, `test_pinned_pages_never_evicted`, `test_dirty_pages_flushed_on_evict`; all fail.
  2. Green — implement LRU via `collections.OrderedDict`; eviction calls `FileStore.write_page` for dirty pages.
  3. Refactor — extract `_touch_lru(key)` and `_is_dirty(key)` helpers.
  4. Verify — three tests pass; add a 1000-page stress test that randomizes access patterns.
  5. Commit — `feat(B2): BufferPool LRU eviction (REQ-SE-004)`.
- **Depends on**: T-2.2.

#### T-2.4 Page alloc/free + fsync
- **File**: `tinydb/storage.py`, `tests/unit/test_storage.py`
- **Interfaces**:
  - Consumes: `FileStore`, `BufferPool`
  - Produces: `FileStore.alloc_page(type)`, `FileStore.free_page(id)`, `FileStore.fsync()`
- **Steps**:
  1. Red — `test_alloc_returns_distinct_ids`, `test_free_then_alloc_reuses_id`, `test_fsync_persists`.
  2. Green — maintain a free-page stack in the header page (load on open, persist on close).
  3. Refactor — header layout: bytes 9..12 hold free-list head (u32) or 0xFFFFFFFF.
  4. Verify — three tests pass; alloc/free stress test.
  5. Commit — `feat(B2): alloc/free/fsync (REQ-SE-005, REQ-SE-006)`.
- **Depends on**: T-2.3.

#### T-2.5 Single-file persistence integration test
- **File**: `tests/unit/test_storage.py`
- **Interfaces**:
  - Consumes: `FileStore`, `BufferPool`
  - Produces: integration test that writes a fake "row" into a fresh DB, closes, reopens, reads back
- **Steps**:
  1. Red — write test; fails (no `write_page` smoke yet).
  2. Green — write a 100-byte body into page 2, close, reopen, read, assert equality.
  3. Refactor — extract `_make_db(tmp_path)` pytest fixture.
  4. Verify — integration test passes; no extra files in `tmp_path`.
  5. Commit — `test(B2): single-file persistence E2E (REQ-SE-002)`.
- **Depends on**: T-2.4.

---

### Batch B3 — SQL Parser

#### T-3.1 Lexer
- **File**: `tinydb/parser/lexer.py`, `tests/unit/test_parser.py`
- **Interfaces**:
  - Consumes: none
  - Produces: `tokenize(sql: str) -> list[Token]` where `Token(type, value, line, col)`
- **Steps**:
  1. Red — `test_tokenize_keywords_and_idents`, `test_tokenize_string_with_doubled_quote`, `test_tokenize_position_tracking`.
  2. Green — implement state-machine lexer; handle keywords via a frozenset; strings via `'...''...'` rule.
  3. Refactor — split into `_lex_number`, `_lex_string`, `_lex_ident_or_keyword`.
  4. Verify — three tests pass; edge cases for trailing comments (skip ` -- ... \n`).
  5. Commit — `feat(B3): lexer with positions (REQ-SP-001)`.
- **Depends on**: T-1.1.

#### T-3.2 AST dataclasses
- **File**: `tinydb/parser/ast.py`
- **Interfaces**:
  - Consumes: none
  - Produces: every `Statement` / `Expr` / `Predicate` dataclass per Decision D7
- **Steps**:
  1. Red — write a `test_ast_equality_via_dataclass` that constructs two equal `CreateTable` and asserts `==`.
  2. Green — define all dataclasses with `@dataclass(frozen=True)`.
  3. Refactor — group predicates under a common base via `Expr` Union type alias.
  4. Verify — equality test passes; all dataclasses importable.
  5. Commit — `feat(B3): AST dataclasses (Decision D7)`.
- **Depends on**: T-1.1.

#### T-3.3 Recursive-descent parser — DDL
- **File**: `tinydb/parser/parser.py`, `tests/unit/test_parser.py`
- **Interfaces**:
  - Consumes: `tokenize`, AST dataclasses
  - Produces: `parse_statement(tokens) -> Statement` for CREATE/DROP TABLE
- **Steps**:
  1. Red — `test_parse_create_table_with_pk_and_not_null`, `test_parse_drop_table_if_exists`.
  2. Green — implement `_parse_create_table`, `_parse_drop_table`.
  3. Refactor — extract `_expect_keyword`, `_parse_ident`, `_parse_type_token`.
  4. Verify — both tests pass.
  5. Commit — `feat(B3): parse CREATE/DROP TABLE (REQ-SP-002)`.
- **Depends on**: T-3.1, T-3.2.

#### T-3.4 Parser — DML
- **File**: `tinydb/parser/parser.py`, `tests/unit/test_parser.py`
- **Interfaces**:
  - Consumes: AST dataclasses
  - Produces: `_parse_insert`, `_parse_select`, `_parse_update`, `_parse_delete`
- **Steps**:
  1. Red — write one scenario test per REQ-SP-003 sub-scenario.
  2. Green — implement DML methods.
  3. Refactor — share `_parse_where_clause`, `_parse_order_by`, `_parse_limit_offset`.
  4. Verify — four tests pass.
  5. Commit — `feat(B3): parse INSERT/SELECT/UPDATE/DELETE (REQ-SP-003)`.
- **Depends on**: T-3.3.

#### T-3.5 Parser — predicates, aggregates, error positions
- **File**: `tinydb/parser/parser.py`, `tests/unit/test_parser.py`
- **Interfaces**:
  - Consumes: AST dataclasses
  - Produces: full predicate grammar (AND/OR precedence, BETWEEN, IN, IS NULL), aggregates (COUNT/SUM/AVG), structured `ParseError`
- **Steps**:
  1. Red — write tests for AND-binds-tighter, BETWEEN-as-AND, COUNT(*)+GROUP BY, and parse-error-position.
  2. Green — implement predicate parser with precedence climbing, aggregate recognition in projections.
  3. Refactor — extract `_parse_atom_predicate` to keep the chain small.
  4. Verify — all tests pass.
  5. Commit — `feat(B3): predicates + aggregates + error positions (REQ-SP-004,005,006)`.
- **Depends on**: T-3.4.

#### T-3.6 Parser — transaction-control statements
- **File**: `tinydb/parser/parser.py`, `tests/unit/test_parser.py`
- **Interfaces**:
  - Consumes: AST dataclasses
  - Produces: `_parse_begin`, `_parse_commit`, `_parse_rollback`
- **Steps**:
  1. Red — `test_parse_begin`, `test_parse_commit`, `test_parse_rollback`.
  2. Green — implement three trivial parsers.
  3. Refactor — fold all three into a single `_parse_tx_control` dispatch.
  4. Verify — three tests pass.
  5. Commit — `feat(B3): parse BEGIN/COMMIT/ROLLBACK (REQ-TM-007)`.
- **Depends on**: T-3.3.

#### T-3.7 Parser purity test
- **File**: `tests/unit/test_parser.py`
- **Interfaces**:
  - Consumes: `parse`
  - Produces: regression test that two consecutive parses do not share state
- **Steps**:
  1. Red — write `test_parser_pure_function` (fails if state leaks).
  2. Green — fix any leaked state found.
  3. Refactor — turn the test into a pytest fixture.
  4. Verify — test passes.
  5. Commit — `test(B3): parser purity (REQ-SP-007)`.
- **Depends on**: T-3.5, T-3.6.

---

### Batch B4 — B+ Tree Index

#### T-4.1 Leaf node codec
- **File**: `tinydb/index.py`, `tests/unit/test_index.py`
- **Interfaces**:
  - Consumes: `encode` / `decode` from B1
  - Produces: `_pack_leaf(keys: list, rowids: list) -> bytes`, `_unpack_leaf(raw) -> tuple`
- **Steps**:
  1. Red — round-trip test for a leaf with 3 INT keys + 3 rowids.
  2. Green — implement codec with `len u16 + keys + rowids` for v0.1.
  3. Refactor — share `key_codec` between INT and TEXT.
  4. Verify — round-trip test passes; ordering test (keys must be ascending).
  5. Commit — `feat(B4): leaf node codec (REQ-BT-001)`.
- **Depends on**: T-1.3, T-2.4.

#### T-4.2 Internal node codec + single-leaf tree
- **File**: `tinydb/index.py`, `tests/unit/test_index.py`
- **Interfaces**:
  - Consumes: leaf codec
  - Produces: internal-node codec, `BPlusTree.create`, `seek(key)`, `range(...)`
- **Steps**:
  1. Red — write `test_seek_on_single_leaf_returns_correct_rowids`, `test_range_inclusive`.
  2. Green — implement internal codec (`[child_ids..., separator_keys...]`) and tree operations that degenerate to scanning the single leaf.
  3. Refactor — encapsulate "tree state = root_page_id + key_type".
  4. Verify — both tests pass.
  5. Commit — `feat(B4): internal codec + seek/range on single-leaf (REQ-BT-002,003)`.
- **Depends on**: T-4.1.

#### T-4.3 Insert + leaf split
- **File**: `tinydb/index.py`, `tests/unit/test_index.py`
- **Interfaces**:
  - Consumes: leaf codec, internal codec
  - Produces: `BPlusTree.insert`, leaf-split routine that returns `(new_page_id, separator_key)`
- **Steps**:
  1. Red — `test_insert_into_full_leaf_triggers_split`, `test_seek_after_split_finds_all_keys`.
  2. Green — implement insert with overflow check + split-and-promote.
  3. Refactor — factor `_split_leaf` into its own method.
  4. Verify — both tests pass; add a 1000-key insert+seek test.
  5. Commit — `feat(B4): insert + leaf split (REQ-BT-005)`.
- **Depends on**: T-4.2.

#### T-4.4 Root promotion + recursive internal splits
- **File**: `tinydb/index.py`, `tests/unit/test_index.py`
- **Interfaces**:
  - Consumes: leaf split
  - Produces: full-tree insert with root promotion and internal-node splits
- **Steps**:
  1. Red — `test_root_promotion_creates_internal_root`, `test_randomized_5000_keys_match_sorted_dict`.
  2. Green — implement recursive insert that propagates `(new_page_id, sep_key)` upward.
  3. Refactor — share `_handle_overflow(page_id)` between leaf and internal cases.
  4. Verify — both tests pass.
  5. Commit — `feat(B4): root promotion + internal splits (REQ-BT-005 end-to-end)`.
- **Depends on**: T-4.3.

#### T-4.5 Delete + merge / redistribute
- **File**: `tinydb/index.py`, `tests/unit/test_index.py`
- **Interfaces**:
  - Consumes: full insert
  - Produces: `BPlusTree.delete`, underflow handling (merge or redistribute)
- **Steps**:
  1. Red — `test_delete_underflow_triggers_merge`, `test_delete_underflow_triggers_redistribute`.
  2. Green — implement delete with `try_rebalance` post-step.
  3. Refactor — extract `_is_underflow(page_id)`, `_merge_or_redistribute(left, right, parent_sep_idx)`.
  4. Verify — both tests pass; randomized insert-all-delete-all-insert-all test.
  5. Commit — `feat(B4): delete + merge/redistribute (REQ-BT-006)`.
- **Depends on**: T-4.4.

#### T-4.6 Index on dedicated pages + TEXT ordering
- **File**: `tinydb/index.py`, `tests/unit/test_index.py`
- **Interfaces**:
  - Consumes: full insert/delete
  - Produces: `BPlusTree` that always allocates pages of type `INDEX`; TEXT-order seek
- **Steps**:
  1. Red — `test_index_pages_have_correct_type`, `test_text_index_orders_utf8`.
  2. Green — call `FileStore.alloc_page(INDEX)` instead of TABLE; pass `ColumnType.TEXT` to codec dispatch.
  3. Refactor — store key_type in tree state; codec reads from there.
  4. Verify — both tests pass.
  5. Commit — `feat(B4): dedicated index pages + TEXT ordering (REQ-BT-007,008)`.
- **Depends on**: T-4.5.

---

### Batch B5 — Query Executor

#### T-5.1 Catalog in header page
- **File**: `tinydb/executor.py`, `tests/unit/test_executor.py`
- **Interfaces**:
  - Consumes: `FileStore`, `BufferPool`
  - Produces: `_Catalog` class with `create_table`, `drop_table`, `get_table`
- **Steps**:
  1. Red — `test_catalog_create_then_get`, `test_catalog_drop_removes_table`.
  2. Green — implement catalog backed by page 0 (header page); schema serialized as JSON-ish string.
  3. Refactor — split schema serialization into `_SchemaCodec` helper.
  4. Verify — both tests pass.
  5. Commit — `feat(B5): catalog in header page (Decision D5, REQ-QE-001,002)`.
- **Depends on**: T-2.4, T-1.3.

#### T-5.2 Row storage in heap pages
- **File**: `tinydb/executor.py`, `tests/unit/test_executor.py`
- **Interfaces**:
  - Consumes: catalog, type codec
  - Produces: `_Heap.append_row(schema, values) -> rowid`, `_Heap.scan() -> Iterator[(rowid, tuple)]`
- **Steps**:
  1. Red — `test_append_and_scan_returns_rows_in_order`.
  2. Green — implement heap using one or more pages of type TABLE; rows encoded as `[len u32 | rowid u64 | values...]`.
  3. Refactor — extract `_encode_row`, `_decode_row`.
  4. Verify — round-trip test passes; 10k-row scan completes in < 1 s.
  5. Commit — `feat(B5): heap append + scan (REQ-QE-004)`.
- **Depends on**: T-5.1.

#### T-5.3 INSERT + SELECT no-WHERE
- **File**: `tinydb/executor.py`, `tests/unit/test_executor.py`
- **Interfaces**:
  - Consumes: `_Heap`, type codec
  - Produces: `Executor.execute(Insert)`, `Executor.execute(Select)` with no WHERE
- **Steps**:
  1. Red — write REQ-QE-003 type-mismatch / NOT-NULL / PK-uniqueness scenarios; write REQ-QE-004 heap-order test.
  2. Green — implement INSERT validation + persistence; SELECT scans heap and projects columns.
  3. Refactor — extract `_validate_row_against_schema(row, schema)`.
  4. Verify — four tests pass.
  5. Commit — `feat(B5): INSERT + SELECT no-WHERE (REQ-QE-003,004)`.
- **Depends on**: T-5.2.

#### T-5.4 WHERE evaluator
- **File**: `tinydb/executor.py`, `tests/unit/test_executor.py`
- **Interfaces**:
  - Consumes: heap scan
  - Produces: `_evaluate_predicate(predicate, row) -> bool` supporting AND/OR, comparisons, BETWEEN, IS NULL, IN
- **Steps**:
  1. Red — write compound-predicate test (REQ-QE-005 scenario).
  2. Green — implement recursive predicate evaluator; comparisons dispatch on column type.
  3. Refactor — short-circuit AND/OR.
  4. Verify — test passes; add NULL-excluded test (REQ-TS-007).
  5. Commit — `feat(B5): WHERE evaluator (REQ-QE-005, REQ-TS-007)`.
- **Depends on**: T-5.3.

#### T-5.5 UPDATE + DELETE
- **File**: `tinydb/executor.py`, `tests/unit/test_executor.py`
- **Interfaces**:
  - Consumes: WHERE evaluator, heap
  - Produces: `Executor.execute(Update)`, `Executor.execute(Delete)`; reject unsafe DELETE without WHERE
- **Steps**:
  1. Red — write REQ-QE-006 scenarios for UPDATE-with-WHERE and DELETE-without-WHERE-rejected.
  2. Green — implement UPDATE (rewrite matching rows in place) and DELETE (mark free); reject bare DELETE.
  3. Refactor — extract `_mutate_matching_rows(predicate, mutator)`.
  4. Verify — two tests pass.
  5. Commit — `feat(B5): UPDATE + safe DELETE (REQ-QE-006)`.
- **Depends on**: T-5.4.

#### T-5.6 ORDER BY + LIMIT/OFFSET
- **File**: `tinydb/executor.py`, `tests/unit/test_executor.py`
- **Interfaces**:
  - Consumes: heap scan, WHERE
  - Produces: ORDER BY single column + LIMIT/OFFSET pipeline
- **Steps**:
  1. Red — write REQ-QE-007 and REQ-QE-008 scenarios.
  2. Green — implement sort + slice; column-extraction helper.
  3. Refactor — split into `_sort_rows(rows, key_fn, desc)` and `_slice_rows(rows, limit, offset)`.
  4. Verify — two tests pass; LIMIT 0 returns empty.
  5. Commit — `feat(B5): ORDER BY + LIMIT/OFFSET (REQ-QE-007,008)`.
- **Depends on**: T-5.5.

#### T-5.7 Aggregates + GROUP BY
- **File**: `tinydb/executor.py`, `tests/unit/test_executor.py`
- **Interfaces**:
  - Consumes: filtered rows
  - Produces: aggregate evaluator `COUNT`, `SUM`, `AVG` with optional GROUP BY
- **Steps**:
  1. Red — write REQ-QE-009 COUNT(*) and GROUP-BY-with-SUM scenarios.
  2. Green — implement projection over grouped rows; AVG = SUM / COUNT.
  3. Refactor — extract `_group_by(rows, keys)` using `itertools.groupby` after sort.
  4. Verify — two tests pass.
  5. Commit — `feat(B5): aggregates + GROUP BY (REQ-QE-009)`.
- **Depends on**: T-5.6.

#### T-5.8 Index-aware executor
- **File**: `tinydb/executor.py`, `tests/unit/test_index.py`, `tests/unit/test_executor.py`
- **Interfaces**:
  - Consumes: B+ tree, executor
  - Produces: WHERE planner that picks `index_seek` or `heap_scan`
- **Steps**:
  1. Red — write indexed-equality and unindexed-fallback scenarios (REQ-QE-010).
  2. Green — implement `_plan_where(stmt) -> Plan` that consults the table's indexes.
  3. Refactor — represent Plan as a small dataclass (`IndexSeek` / `HeapScan`).
  4. Verify — two tests pass; verify execution count via a counter injected into the B+ tree.
  5. Commit — `feat(B5): index-aware executor (REQ-QE-010)`.
- **Depends on**: T-4.6, T-5.4.

#### T-5.9 DROP TABLE frees pages
- **File**: `tinydb/executor.py`, `tests/unit/test_executor.py`
- **Interfaces**:
  - Consumes: catalog, heap, indexes
  - Produces: `Executor.execute(DropTable)` that frees data and index pages
- **Steps**:
  1. Red — `test_drop_table_frees_pages_and_removes_from_catalog`.
  2. Green — implement free-page loop and catalog update.
  3. Refactor — extract `_free_table_pages(table_meta)`.
  4. Verify — test passes; verify file size does not grow on `CREATE; DROP; CREATE` cycle.
  5. Commit — `feat(B5): DROP TABLE frees pages (REQ-QE-002)`.
- **Depends on**: T-5.8.

---

### Batch B6 — Transaction Manager (WAL)

#### T-6.1 WAL record codec
- **File**: `tinydb/wal.py`, `tests/unit/test_wal.py`
- **Interfaces**:
  - Consumes: `FileStore`
  - Produces: `_WalRecord` dataclass + `encode(record) -> bytes`, `decode(raw) -> _WalRecord`
- **Steps**:
  1. Red — `test_record_roundtrip_mutation`, `test_record_roundtrip_commit`.
  2. Green — implement codec per Decision D4; compute CRC32 for checksum.
  3. Refactor — share `_pack_with_checksum` between record types.
  4. Verify — two tests pass; corrupted checksum raises `TransactionLogCorrupt`.
  5. Commit — `feat(B6): WAL record codec (Decision D4)`.
- **Depends on**: T-2.4.

#### T-6.2 WAL append + fsync ordering
- **File**: `tinydb/wal.py`, `tests/unit/test_wal.py`
- **Interfaces**:
  - Consumes: `_WalRecord`
  - Produces: `Wal.append(record_type, payload) -> Lsn`, `Wal.fsync() -> None`
- **Steps**:
  1. Red — `test_wal_appends_in_order`, `test_wal_fsync_persists`.
  2. Green — append to `<file>-wal`; fsync calls `os.fsync`.
  3. Refactor — wrap wal file in a small context manager.
  4. Verify — two tests pass; byte offsets grow monotonically.
  5. Commit — `feat(B6): WAL append + fsync (REQ-TM-004)`.
- **Depends on**: T-6.1.

#### T-6.3 BEGIN / COMMIT / ROLLBACK state machine
- **File**: `tinydb/tx.py`, `tests/unit/test_tx.py`
- **Interfaces**:
  - Consumes: `Wal`, `FileStore`
  - Produces: `TxManager.begin()`, `commit(tx_id)`, `rollback(tx_id)`; raises `TransactionAlreadyActive` on nested BEGIN
- **Steps**:
  1. Red — write REQ-TM-001/002/003/006 scenarios.
  2. Green — implement TxManager with one slot for current tx_id; COMMIT appends `COMMIT` record and fsyncs WAL before page flush; ROLLBACK discards buffered writes.
  3. Refactor — introduce `_TxState` dataclass.
  4. Verify — four tests pass.
  5. Commit — `feat(B6): BEGIN/COMMIT/ROLLBACK state machine (REQ-TM-001,002,003,006)`.
- **Depends on**: T-6.2.

#### T-6.4 Hook WAL into Executor writes
- **File**: `tinydb/executor.py`, `tests/unit/test_tx.py`
- **Interfaces**:
  - Consumes: `TxManager`, `Executor`
  - Produces: Executor that writes a MUTATE record before every page write inside an open transaction
- **Steps**:
  1. Red — write `test_commit_persists_through_kill` (REQ-TM-002).
  2. Green — wrap heap writes with `Wal.append('MUTATE', before+after)`; ensure WAL fsync precedes page flush.
  3. Refactor — extract `_write_with_wal(page_id, before, after)`.
  4. Verify — test passes; an injected fault between WAL flush and page flush is recovered by T-6.5.
  5. Commit — `feat(B6): executor writes via WAL (REQ-TM-004)`.
- **Depends on**: T-6.3, T-5.5.

#### T-6.5 Crash recovery
- **File**: `tinydb/wal.py`, `tests/e2e/test_crash_recovery.py`
- **Interfaces**:
  - Consumes: `Wal`, `FileStore`, `BufferPool`
  - Produces: `Wal.replay(store, pool)` that redoes committed mutations and undoes uncommitted ones on open
- **Steps**:
  1. Red — write `test_crash_between_wal_and_page_write_recovers` (REQ-TM-005 scenario).
  2. Green — implement forward-only WAL replay: track set of committed tx_ids; apply MUTATE if its tx_id is committed, skip otherwise.
  3. Refactor — split replay into `_scan_commits`, `_apply_mutation`.
  4. Verify — test passes; add a "kill mid-transaction" scenario.
  5. Commit — `feat(B6): WAL replay / crash recovery (REQ-TM-005)`.
- **Depends on**: T-6.4.

#### T-6.6 CHECKPOINT command
- **File**: `tinydb/executor.py`, `tinydb/tx.py`, `tests/unit/test_tx.py`
- **Interfaces**:
  - Consumes: parser AST (extended), TxManager
  - Produces: `CHECKPOINT` SQL command that flushes all dirty pages and truncates the WAL
- **Steps**:
  1. Red — `test_checkpoint_truncates_wal_after_flush`.
  2. Green — add parser branch for `CHECKPOINT`; add `TxManager.checkpoint()`.
  3. Refactor — checkpoint acquires single-connection lock during flush.
  4. Verify — test passes; WAL file size is 0 after checkpoint (in v0.1, all pages are flushed first).
  5. Commit — `feat(B6): CHECKPOINT (Risk R3 mitigation)`.
- **Depends on**: T-6.5.

---

### Batch B7 — CLI / REPL

#### T-7.1 CLI entry point + `--help` / `--version`
- **File**: `tinydb/cli.py`, `tests/e2e/test_cli_repl.py`
- **Interfaces**:
  - Consumes: `Database`, parser
  - Produces: `tinydb <file.db>` opens REPL; `--help` and `--version` exit 0 (REQ-CR-001, REQ-CR-006)
- **Steps**:
  1. Red — `test_help_exits_zero`, `test_version_exits_zero`.
  2. Green — implement `main()` with `argparse`; `--version` reads `tinydb.__version__`.
  3. Refactor — extract `_build_parser()`.
  4. Verify — two tests pass via `subprocess.run`.
  5. Commit — `feat(B7): CLI --help/--version (REQ-CR-006)`.
- **Depends on**: T-1.1.

#### T-7.2 REPL loop + single-statement execution
- **File**: `tinydb/cli.py`, `tests/e2e/test_cli_repl.py`
- **Interfaces**:
  - Consumes: `Executor`, parser, REPL print helpers
  - Produces: REPL that reads one line, parses, executes, prints result (REQ-CR-002)
- **Steps**:
  1. Red — write ASCII-table-rendering and `1 row inserted` scenarios (REQ-CR-002 sub-scenarios).
  2. Green — implement REPL loop with `_print_result`; ASCII table builder for SELECT.
  3. Refactor — extract `_render_table(rows, columns)`.
  4. Verify — two tests pass via subprocess.
  5. Commit — `feat(B7): REPL single-statement (REQ-CR-002)`.
- **Depends on**: T-7.1, T-5.3.

#### T-7.3 Dot-commands
- **File**: `tinydb/cli.py`, `tests/e2e/test_cli_repl.py`
- **Interfaces**:
  - Consumes: `Executor`, catalog
  - Produces: `.tables`, `.schema <name>`, `.exit`, `.quit`, `.help`, EOF handling (REQ-CR-003)
- **Steps**:
  1. Red — write `.tables`, `.schema`, EOF scenarios.
  2. Green — implement `_handle_dot_command(line)`; catch `EOFError` and exit cleanly.
  3. Refactor — small dispatch table mapping `.foo` → handler.
  4. Verify — three tests pass; exit code is 0 after EOF.
  5. Commit — `feat(B7): dot-commands (REQ-CR-003)`.
- **Depends on**: T-7.2.

#### T-7.4 Multi-line input + non-fatal errors
- **File**: `tinydb/cli.py`, `tests/e2e/test_cli_repl.py`
- **Interfaces**:
  - Consumes: REPL loop
  - Produces: continuation buffer until `;`; errors printed to stderr, REPL keeps running (REQ-CR-004, REQ-CR-005)
- **Steps**:
  1. Red — write multi-line INSERT and typo-does-not-kill-REPL scenarios.
  2. Green — buffer lines until `;`; on exception print to stderr and clear buffer.
  3. Refactor — extract `_read_statement(stdin, prompt)`.
  4. Verify — two tests pass; the second script confirms a follow-up `SELECT` still works.
  5. Commit — `feat(B7): multi-line + non-fatal errors (REQ-CR-004,005)`.
- **Depends on**: T-7.3.

#### T-7.5 Stdin batch mode
- **File**: `tinydb/cli.py`, `tests/e2e/test_cli_repl.py`
- **Interfaces**:
  - Consumes: `main(argv, stdin, stdout, stderr)`
  - Produces: detect non-tty stdin → batch mode (REQ-CR-007)
- **Steps**:
  1. Red — write success-batch and fail-fast scenarios.
  2. Green — `main` checks `stdin.isatty()`; if False, runs `_run_batch(stdin)`.
  3. Refactor — `_run_batch` reuses `_execute_one(sql)`.
  4. Verify — two tests pass via subprocess pipe.
  5. Commit — `feat(B7): stdin batch mode (REQ-CR-007)`.
- **Depends on**: T-7.4.

#### T-7.6 Wire CLI to TxManager
- **File**: `tinydb/cli.py`, `tests/unit/test_tx.py`
- **Interfaces**:
  - Consumes: parser, TxManager
  - Produces: BEGIN/COMMIT/ROLLBACK routed through TxManager (REQ-TM-007)
- **Steps**:
  1. Red — `test_cli_begin_commit_insert_persists`, `test_cli_rollback_discards`.
  2. Green — dispatch `Begin | Commit | Rollback` AST to `TxManager`.
  3. Refactor — keep executor unaware of CLI; TxManager owned by CLI.
  4. Verify — two tests pass.
  5. Commit — `feat(B7): REPL wires BEGIN/COMMIT/ROLLBACK (REQ-TM-007)`.
- **Depends on**: T-7.4, T-6.3.

---

### Batch B8 — E2E Tests & Polish

#### T-8.1 E2E: SQL tour through REPL
- **File**: `tests/e2e/test_cli_repl.py`
- **Interfaces**:
  - Consumes: full CLI
  - Produces: a single subprocess test that runs CREATE → INSERT×N → SELECT with WHERE/ORDER BY/LIMIT → UPDATE → DELETE → DROP
- **Steps**:
  1. Red — write the tour test; fails (modules not all integrated yet).
  2. Green — fix any wiring bugs found by the test.
  3. Refactor — split into a parameterized pytest with a helper script.
  4. Verify — test passes.
  5. Commit — `test(B8): full SQL tour through REPL`.
- **Depends on**: T-7.6, T-5.8.

#### T-8.2 E2E: 10k-row index lookup benchmark
- **File**: `tests/e2e/test_crash_recovery.py` (or new `test_perf.py`)
- **Interfaces**:
  - Consumes: B+ tree, executor
  - Produces: insert 10k rows, run 100 indexed lookups, assert all correct and mean latency < 1 ms
- **Steps**:
  1. Red — write test (likely fails on first run due to split bugs).
  2. Green — fix any bugs surfaced.
  3. Refactor — pull the workload into a helper module to reuse in the README example.
  4. Verify — test passes.
  5. Commit — `test(B8): 10k-row index benchmark`.
- **Depends on**: T-5.8, T-4.6.

#### T-8.3 E2E: crash mid-transaction, recovery
- **File**: `tests/e2e/test_crash_recovery.py`
- **Interfaces**:
  - Consumes: TxManager, WAL
  - Produces: subprocess that opens DB, BEGIN, INSERT, kill -9, reopen, assert consistent
- **Steps**:
  1. Red — write the test using `subprocess.Popen` + `os.kill`.
  2. Green — fix any bugs surfaced.
  3. Refactor — extract `_kill_and_reopen(proc, db_path)` helper.
  4. Verify — test passes on three consecutive runs (no flake).
  5. Commit — `test(B8): crash-recovery subprocess E2E (REQ-TM-005)`.
- **Depends on**: T-6.5.

#### T-8.4 Coverage gate
- **File**: `pyproject.toml`, `tests/`
- **Interfaces**:
  - Consumes: pytest, pytest-cov
  - Produces: `pytest --cov=tinydb --cov-fail-under=80` passes
- **Steps**:
  1. Red — run coverage; observe gaps.
  2. Green — add tests for any uncovered branches until ≥ 80%.
  3. Refactor — delete dead code if found.
  4. Verify — coverage gate passes locally.
  5. Commit — `chore(B8): coverage ≥ 80% (DP-0 constraint)`.
- **Depends on**: T-8.3.

#### T-8.5 Lint + mypy pass
- **File**: `pyproject.toml`, `tinydb/`
- **Interfaces**:
  - Consumes: ruff, mypy (dev-only)
  - Produces: zero lint errors, zero mypy errors
- **Steps**:
  1. Red — run `ruff check .` and `mypy tinydb/`; observe issues.
  2. Green — fix issues (mostly missing type hints, unused imports).
  3. Refactor — add `[[tool.mypy.overrides]]` for `tests/` to allow untyped defs.
  4. Verify — both pass.
  5. Commit — `chore(B8): ruff + mypy clean (Risk R5)`.
- **Depends on**: T-8.4.

---

### Batch B9 — Docs & Release

#### T-9.1 README quickstart + scope statement
- **File**: `README.md`
- **Interfaces**:
  - Consumes: CLI, executor, design.md
  - Produces: 5-minute quickstart; explicit Out-of-Scope list mirroring proposal.md
- **Steps**:
  1. Red — write README skeleton; commit message must reference DP-0 constraints.
  2. Green — install instructions (`pip install -e .[dev]`); minimal Python example; REPL example.
  3. Refactor — link from README to `docs/architecture.md`.
  4. Verify — render preview by `cat README.md`; ensure no broken markdown.
  5. Commit — `docs(B9): README quickstart + scope (DP-0 traceability)`.
- **Depends on**: T-8.5.

#### T-9.2 Architecture doc
- **File**: `docs/architecture.md`
- **Interfaces**:
  - Consumes: design.md, specs/
  - Produces: cross-reference table mapping each spec scenario to the implementing module
- **Steps**:
  1. Red — write the table from a script (auto-generated from specs + a `module:` frontmatter field).
  2. Green — hand-edit any missing entries.
  3. Refactor — store the script as `scripts/gen_arch_table.py`.
  4. Verify — `python scripts/gen_arch_table.py` regenerates the table without drift.
  5. Commit — `docs(B9): architecture cross-reference`.
- **Depends on**: T-9.1.

#### T-9.3 Tag v0.1.0 + release notes
- **File**: git tag `v0.1.0`
- **Interfaces**:
  - Consumes: full test suite green
  - Produces: annotated tag `v0.1.0` with release notes
- **Steps**:
  1. Red — `git tag -n v0.1.0` reports no tag.
  2. Green — write `RELEASE.md` listing every capability shipped; cut tag.
  3. Refactor — none.
  4. Verify — `git tag --list` shows `v0.1.0`; `pytest` still passes.
  5. Commit — `release(B9): v0.1.0 (DP-7 prep)`.
- **Depends on**: T-9.2.

#### T-9.4 Final DP-7 audit
- **File**: `.spec-superflow.yaml`, `docs/decision-point-audit.md`
- **Interfaces**:
  - Consumes: full state machine
  - Produces: audit report from `ssf audit`
- **Steps**:
  1. Red — `ssf audit .` shows missing DP-7 fields.
  2. Green — run `ssf audit .` and fill every DP entry referencing a commit SHA.
  3. Refactor — save audit under `docs/`.
  4. Verify — audit report lists all 7 DPs with timestamps.
  5. Commit — `chore(B9): DP-7 audit report`.
- **Depends on**: T-9.3.

---

## Cross-cutting acceptance gates

- [ ] All 9 batches completed with their T-commit messages containing `(DP-X)` references.
- [ ] `pytest --cov=tinydb --cov-fail-under=80` passes.
- [ ] E2E tests in `tests/e2e/` pass on three consecutive runs (no flake).
- [ ] `python -m tinydb sample.db` opens a REPL; `.tables` works.
- [ ] `printf 'CREATE TABLE t(id INT);\nINSERT INTO t VALUES (1);\n' | python -m tinydb batch.db` exits 0.
- [ ] `.spec-superflow.yaml` shows `state: closing`, all 7 DP fields populated, `batches_completed: 9`, `test_result: pass`.
