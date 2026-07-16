## Purpose

The CLI / REPL capability exposes an interactive command-line interface for tinydb. It supports interactive SQL entry with result rendering, dot-commands for introspection, multi-line input, and non-interactive batch execution via stdin.

## ADDED Requirements

### Requirement: `tinydb <file.db>` opens a REPL
A top-level `tinydb` command MUST accept a single positional argument `<file>` (path to a `.db` file) and start an interactive REPL with the database open and ready to execute SQL.

#### Scenario: REPL opens an existing database
- **WHEN** the user runs `tinydb sample.db` against an existing file containing one table named `users`
- **THEN** the prompt appears and `.tables` lists `users`.

#### Scenario: REPL creates a new database if the file does not exist
- **WHEN** the user runs `tinydb fresh.db` and the file does not exist
- **THEN** the database is initialized (a header page is written) and the prompt appears without error.

### Requirement: REPL executes single SQL statements
On each prompt, the REPL MUST read a SQL statement, execute it, and display the result (rows for SELECT; row count for INSERT/UPDATE/DELETE; "OK" for DDL; error message for failures).

#### Scenario: SELECT prints rows in an ASCII table
- **WHEN** the user types `SELECT id, name FROM users;` and the table has 2 rows
- **THEN** the output is a two-column ASCII table with a header row, a separator row, and 2 data rows.

#### Scenario: INSERT prints a row count
- **WHEN** the user types `INSERT INTO users VALUES (1, 'alice');` and the insert succeeds
- **THEN** the output is `1 row inserted` and no row data is printed.

### Requirement: Dot-commands for introspection
The REPL MUST support the following dot-commands:
- `.tables` — list all table names (one per line)
- `.schema <table>` — print the `CREATE TABLE` statement for `<table>`
- `.exit` / `.quit` / EOF (Ctrl-D) — close the database and exit cleanly
- `.help` — print the list of dot-commands

#### Scenario: .schema prints CREATE TABLE
- **WHEN** the user types `.schema users` after running `CREATE TABLE users (id INT PRIMARY KEY, name TEXT);`
- **THEN** the output is the original `CREATE TABLE users (id INT PRIMARY KEY, name TEXT);` statement.

#### Scenario: Ctrl-D exits cleanly
- **WHEN** the user presses Ctrl-D at the prompt
- **THEN** the database is flushed/closed and the process exits with status `0`.

### Requirement: Errors are reported, not fatal
A SQL parse error, runtime error, or constraint violation MUST be printed to stderr in a single human-readable line and MUST NOT terminate the REPL.

#### Scenario: parse error leaves the REPL running
- **WHEN** the user types `SELEC * FROM users;` (a typo)
- **THEN** the REPL prints an error such as `ParseError: line 1, col 7: expected keyword SELECT` and shows a fresh prompt.

### Requirement: Multi-line SQL input
Statements that do not end with `;` MUST be treated as continuations; the REPL MUST accumulate lines until a `;` is seen (or `.exit` / EOF). The continuation prompt MUST be visually distinct from the main prompt.

#### Scenario: multi-line INSERT
- **WHEN** the user types the three lines `INSERT INTO users`, `  VALUES (1, 'alice'),`, and `         (2, 'bob');`
- **THEN** the REPL treats the three lines as one statement and prints `2 rows inserted`.

### Requirement: Help text and version flag
The top-level `tinydb` command MUST accept `--help` (prints usage) and `--version` (prints the package version). Both MUST exit with status `0`.

#### Scenario: --version prints the package version
- **WHEN** the user runs `tinydb --version`
- **THEN** the output is the version string of the installed `tinydb` package (for example `tinydb 0.1.0`) and the exit code is `0`.

### Requirement: Non-interactive batch execution
The CLI MUST accept SQL statements piped on stdin (for example `tinydb sample.db < script.sql`) and execute them sequentially. It MUST exit with status `0` on success and non-zero on the first error.

#### Scenario: stdin batch succeeds
- **WHEN** `printf 'CREATE TABLE t(id INT);\nINSERT INTO t VALUES (1);\n' | tinydb test.db` runs
- **THEN** the process exits with status `0` and `tinydb test.db` opened in a subsequent REPL shows the inserted row.

#### Scenario: stdin batch fails fast on error
- **WHEN** `printf 'INSERT INTO t VALUES (1);\nBAD SQL;\n' | tinydb test.db` runs against a non-existent table
- **THEN** the process exits non-zero, the error is printed to stderr, and no further statements are executed.
