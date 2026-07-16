## Purpose

The Storage Engine capability manages on-disk persistence: fixed-size pages, a single-file format, and a least-recently-used buffer pool. It exposes page-level read/write primitives to the higher layers (transaction manager, executor, indexes).

## ADDED Requirements

### Requirement: Fixed-size page layout
The storage engine MUST organize the database file as a sequence of fixed-size pages. The default page size MUST be 4096 bytes and MUST be configurable at database-open time within the range [512, 65536].

#### Scenario: default page size on open
- **WHEN** a database is opened without an explicit page size
- **THEN** the page size used is 4096 bytes and a fresh file allocates at least one header page.

#### Scenario: custom page size is honored
- **WHEN** `Database(path, page_size=8192)` is opened
- **THEN** every page read or written is exactly 8192 bytes and the page size is recorded in the header page.

### Requirement: Single-file persistence
The database MUST persist all data, indexes, and catalog metadata within a single file whose path is provided at open time. No other files or directories are required for normal operation.

#### Scenario: data survives close and reopen
- **WHEN** a row is inserted into a fresh `.db` file and the database is then closed
- **THEN** reopening the same file and querying the table returns the inserted row.

#### Scenario: no auxiliary files are created
- **WHEN** the database performs CREATE TABLE, INSERT, and SELECT inside a temporary directory
- **THEN** only the single `.db` file exists afterwards; no WAL, journal, lock, or temporary files remain on disk.

### Requirement: Page header format
Every page MUST begin with a fixed-size header containing `page_id` (uint32), `page_type` (uint8: 0=free, 1=header, 2=table, 3=index, 4=overflow), and `lsn` (uint32) used for WAL recovery.

#### Scenario: header fields are persisted
- **WHEN** a page is allocated with `page_id=7`, `page_type=2`, `lsn=42`
- **THEN** reading the page back yields exactly those three fields and the remaining bytes form the page body.

### Requirement: Buffer pool with LRU eviction
The storage engine MUST maintain an in-memory buffer pool. When the pool is full and a new page is requested, the least-recently-used unpinned page MUST be evicted (written back if dirty, then dropped from memory).

#### Scenario: LRU eviction under pressure
- **WHEN** the buffer pool is at capacity and a new page not already in the pool is requested
- **THEN** exactly one previously unpinned page is evicted; a pinned (in-use) page is never evicted until it is unpinned.

#### Scenario: dirty pages are flushed before eviction
- **WHEN** a dirty page is selected for eviction
- **THEN** its current bytes are written to disk before the in-memory copy is dropped.

### Requirement: Allocate and free pages
The storage engine MUST support allocating a new page (returning a fresh `page_id`) and freeing an existing page (returning it to the free list for reuse).

#### Scenario: freed page id is reused
- **WHEN** a page is allocated, written, freed, and then another page is allocated
- **THEN** the newly allocated page receives the just-freed `page_id` (LIFO reuse) instead of extending the file.

### Requirement: Read/write durability boundary
The storage engine MUST expose an explicit `fsync` operation so that bytes written before the call survive a power loss.

#### Scenario: fsync after commit
- **WHEN** the transaction manager calls `storage.fsync()` after writing commit records
- **THEN** a simulated process kill followed by reopening the file yields the committed on-disk state.
