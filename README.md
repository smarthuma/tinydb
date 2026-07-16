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
from tinydb import Database

db = Database("sample.db")
db.execute("CREATE TABLE users (id INT PRIMARY KEY, name TEXT, age INT);")
db.execute("INSERT INTO users VALUES (1, 'alice', 30);")
db.execute("INSERT INTO users VALUES (2, 'bob', 25);")

for row in db.execute("SELECT name, age FROM users WHERE age >= 25 ORDER BY age;"):
    print(row)
# ('bob', 25)
# ('alice', 30)

db.close()
```

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
- WHERE filtering with `AND` / `OR` / `BETWEEN` / `IN` / `IS NULL`
- `ORDER BY` (ASC/DESC), `LIMIT`, `OFFSET`
- Column constraints: `PRIMARY KEY`, `NOT NULL`, `UNIQUE`
- Aggregate functions: `COUNT(*)`, `SUM(col)`, `AVG(col)` + `GROUP BY`
- B+ tree secondary index
- Type system: `INT`, `FLOAT`, `TEXT`, `BOOL` with NULL round-trip
- ACID transactions: `BEGIN`, `COMMIT`, `ROLLBACK` with WAL
- Single-file persistence (`<file>.db` + `<file>.db-wal`)
- CLI/REPL with multi-line input, dot-commands, batch mode

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
