## Purpose

The B+ Tree Index capability provides secondary indexes over table columns to accelerate equality and range lookups. It maintains the index in sync with the heap and supports split/merge rebalancing.

## ADDED Requirements

### Requirement: Node types — internal and leaf
A B+ tree node MUST be either `internal` (holds separator keys and child page ids) or `leaf` (holds key→rowid mappings in ascending key order). The tree order MUST be configurable at index creation time with a default that yields a tree height of 2–3 for 10,000 rows.

#### Scenario: freshly created tree has a single leaf root
- **WHEN** an empty index is created
- **THEN** the tree consists of exactly one leaf root page with `is_leaf=True` and `key_count=0`.

### Requirement: Point lookup via index
The index MUST support `seek(key)` returning the rowid (or rowids, for non-unique indexes) of the matching rows, or an empty list if the key is absent.

#### Scenario: point lookup on a unique index
- **WHEN** the unique index on `users.id` contains key `42` mapped to rowid `7`
- **THEN** `seek(42)` returns `[7]` and `seek(43)` returns `[]`.

### Requirement: Range scan via index
The index MUST support `range(lo, hi, inclusive)` returning rowids in ascending key order.

#### Scenario: inclusive range
- **WHEN** the index on `users.age` contains keys `10, 18, 25, 30, 40`
- **THEN** `range(18, 30, inclusive=True)` returns the rowids for `18, 25, 30` in that order.

### Requirement: Maintain index on INSERT, UPDATE, DELETE
The index MUST be kept consistent with the table: every successful INSERT adds the key→rowid mapping, every UPDATE removes the old mapping and inserts the new one, and every DELETE removes the mapping.

#### Scenario: DELETE removes the mapping
- **WHEN** a row with `id=42` is deleted
- **THEN** `seek(42)` on the index returns `[]`.

#### Scenario: UPDATE changes the mapping
- **WHEN** a row's `id` changes from `42` to `99`
- **THEN** `seek(42)` returns `[]` and `seek(99)` returns the row's new rowid.

### Requirement: Node split on overflow
When a leaf or internal node exceeds the configured maximum key count, the index MUST split it into two nodes and propagate the separator key upward. The split MUST preserve key ordering and completeness of the search property.

#### Scenario: leaf split when full
- **WHEN** a leaf at maximum capacity receives one more key
- **THEN** the leaf is split into two leaves whose key ranges partition the original range and the parent receives the new separator key.

### Requirement: Node merge or redistribute on underflow
When a node's key count falls below the configured minimum after a delete, the index MUST merge it with a sibling or redistribute keys from a sibling so the search property holds.

#### Scenario: underflow triggers merge or redistribution
- **WHEN** deleting brings a leaf below the minimum key count and its sibling has room
- **THEN** either the two leaves are merged into one or keys are redistributed so both nodes are within `[min, max]` key count.

### Requirement: Index lives in dedicated pages
Index nodes MUST be stored in pages whose `page_type` equals `INDEX`. Heap pages and index pages MUST NOT share a single page.

#### Scenario: index page is recognizable
- **WHEN** the storage engine enumerates all pages
- **THEN** every index page's header byte `page_type` equals `INDEX` and every heap page's header byte equals `TABLE`.

### Requirement: Index supports INT and TEXT keys
The index MUST support both INT and TEXT key types with correct ordering (INT numeric; TEXT byte-wise UTF-8 codepoint).

#### Scenario: TEXT index orders lexicographically
- **WHEN** TEXT keys `["apple", "Banana", "cherry"]` are inserted (case-sensitive UTF-8)
- **THEN** a full scan returns rowids in order `["Banana", "apple", "cherry"]` (uppercase `B` = 0x42 sorts before lowercase `a` = 0x61).
