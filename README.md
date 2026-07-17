# tinydb

A tiny embedded relational database in Python — a teaching artifact for
database internals (storage engine, SQL parsing, query optimization,
indexes, transactions).

- **Version**: 0.1.0
- **Python**: 3.10+
- **Runtime dependencies**: none (stdlib only)
- **Development dependencies**: pytest, pytest-cov, ruff, mypy

## Quickstart

### Install (editable)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Use as a library

```python
from tinydb.executor import Executor

db = Executor.open("sample.db")
db.execute("CREATE TABLE users (id INT PRIMARY KEY, name TEXT, age INT);")
db.execute("INSERT INTO users VALUES (1, 'alice');")
db.execute("INSERT INTO users VALUES (2, 'bob');")

rows = db.execute("SELECT name FROM users WHERE id >= 1 ORDER BY id;")
print(rows)
# [(1, 'alice'), (2, 'bob')]

db.close()
```

> 注：v0.1.0 直接使用 `Executor` 类（无 `Database` 包装层、无 context manager、无 `transaction()` 方法）。
> 这些便利 API 计划在 v0.2 实现。

### Transactions (low-level)

v0.1.0 的事务 API 是低层的 `TxManager`：

```python
from tinydb import storage, wal, tx

store = storage.FileStore.open("tx.db")
tx_mgr = tx.TxManager(store)
tx_id = tx_mgr.begin()
# ... operations ...
tx_mgr.commit(tx_id)   # or tx_mgr.rollback(tx_id)
```

REPL 单条 SQL 走 autocommit；显式事务块 API 计划在 v0.2 添加。

### Use the CLI / REPL

```bash
python -m tinydb.cli sample.db
```

```
tinydb v0.1.0 — type .help for commands
> CREATE TABLE t (id INT, name TEXT);
OK
> INSERT INTO t VALUES (1, 'alice'), (2, 'bob');
2 row(s) affected
> SELECT id, name FROM t WHERE id >= 1 ORDER BY id;
id | name
---+-------
1  | alice
2  | bob
2 row(s)
> .tables
t
> .exit
```

### Batch mode (stdin)

```bash
printf 'CREATE TABLE t (id INT);\nINSERT INTO t VALUES (1);\n' | python -m tinydb.cli batch.db
```

## What's in scope (v0.1)

- Pure SQL string interface (`db.execute("SELECT ...")`)
- DDL: `CREATE TABLE`, `DROP TABLE`
- DML: `INSERT`, `SELECT`, `UPDATE`, `DELETE`
- WHERE filtering with `AND` / `OR` / `BETWEEN` / `IN` / `IS NULL` / `IS NOT NULL`
- `ORDER BY` (ASC/DESC), `LIMIT`, `OFFSET`
- Column constraints: `PRIMARY KEY`, `NOT NULL`, `UNIQUE`
- Aggregate functions: `COUNT(*)`, `SUM(col)`, `AVG(col)` + `GROUP BY` (no MIN/MAX in v0.1)
- B+ tree secondary index (split only; no merge in v0.1)
- Type system: `INT`, `FLOAT`, `TEXT`, `BOOL` with NULL round-trip
- ACID transactions: Python `db.transaction():` block (REPL is autocommit)
- Single-file persistence (`<file>.db` + `<file>.db-wal` recorded; WAL crash recovery wired in v0.2)
- CLI/REPL with multi-line input, dot-commands, stdin batch mode

## What's explicitly out of scope (v0.1)

- Multi-table JOIN queries
- Concurrency control (multi-thread / multi-process)
- `ALTER TABLE`, views, triggers, foreign keys
- Network / client-server mode
- Any third-party runtime dependency

## Development

```bash
# Run all tests
pytest tests/ -q

# Run with coverage gate (DP-0 hard constraint: ≥ 80%)
pytest --cov=tinydb --cov-fail-under=80 tests/

# E2E tests only
pytest tests/e2e/ -q
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for cross-references between
each spec scenario and the implementing module.

## Design Decisions

See `changes/tinydb-v0.1/design.md` for the 8 architectural decisions
(D1..D8) and 8 risks (R1..R8) tracked during planning.

## License

MIT
