## Purpose

The SQL Parser capability transforms a SQL string into an executable AST. It owns three sub-capabilities: tokenization, grammar parsing, and structured error reporting. The parser MUST be a pure function of its input, holding no shared state between invocations.

## ADDED Requirements

### Requirement: Tokenize SQL into a typed token stream
The SQL parser MUST tokenize an input SQL string into an ordered list of tokens, where each token carries a type (one of KEYWORD, IDENT, NUMBER, STRING, OPERATOR, PUNCT, EOF) and a 1-based (line, column) source position.

#### Scenario: tokenizer yields typed tokens with positions
- **WHEN** the parser receives `CREATE TABLE users (id INT, name TEXT);`
- **THEN** the tokenizer produces tokens in source order including CREATE, TABLE, users, (, id, INT, ,, name, TEXT, ), ;, EOF, each with a (line, column) tuple, and EOF is the last token.

#### Scenario: string literal preserves embedded single quotes by doubling
- **WHEN** the parser receives the literal text `'O''Brien'`
- **THEN** the tokenizer produces a single STRING token whose decoded value is `O'Brien`.

### Requirement: Parse DDL — CREATE TABLE and DROP TABLE
The parser MUST produce a CreateTable AST for `CREATE TABLE [IF NOT EXISTS] <ident> (<col_def>[, ...])` and a DropTable AST for `DROP TABLE [IF EXISTS] <ident>[, ...]`. Column definitions MUST carry the column name, the declared type token, and the list of constraints.

#### Scenario: CREATE TABLE with primary key and NOT NULL constraints
- **WHEN** the parser receives `CREATE TABLE users (id INT PRIMARY KEY, name TEXT NOT NULL);`
- **THEN** the resulting AST is `CreateTable(name='users', columns=[(id, INT, [PRIMARY KEY]), (name, TEXT, [NOT NULL])])`.

#### Scenario: DROP TABLE IF EXISTS is accepted at parse time
- **WHEN** the parser receives `DROP TABLE IF EXISTS legacy;`
- **THEN** the resulting AST is `DropTable(names=['legacy'], if_exists=True)` and no parse error is raised; the executor decides whether the table exists.

### Requirement: Parse DML — INSERT, SELECT, UPDATE, DELETE
The parser MUST produce an Insert, Select, Update, and Delete AST for their respective statements. The Select AST MUST carry optional where, order_by, limit, offset, and group_by clauses as structured fields.

#### Scenario: SELECT with WHERE, ORDER BY, LIMIT, OFFSET
- **WHEN** the parser receives `SELECT id, name FROM users WHERE age >= 18 ORDER BY name ASC LIMIT 10 OFFSET 5;`
- **THEN** the AST contains the column list `[id, name]`, the WHERE predicate tree, `order_by=[(name, ASC)]`, `limit=10`, `offset=5`.

#### Scenario: UPDATE with WHERE
- **WHEN** the parser receives `UPDATE users SET name = 'alice' WHERE id = 1;`
- **THEN** the AST contains the assignment list `[(name, 'alice')]` and the WHERE predicate `id = 1`.

#### Scenario: DELETE without WHERE is accepted at parse time but rejected at runtime
- **WHEN** the parser receives `DELETE FROM users;`
- **THEN** the AST is `Delete(table='users', where=None)`; the executor MUST reject this statement at runtime with an `UnsafeDeleteWithoutWhere` error.

### Requirement: Parse WHERE predicates with AND and OR
The parser MUST build a binary predicate tree for AND (higher precedence than OR) and MUST support the operators `=`, `<>`, `<`, `<=`, `>`, `>=`, `IS NULL`, `IS NOT NULL`, `IN (...)`, and `BETWEEN a AND b`.

#### Scenario: AND binds tighter than OR
- **WHEN** the parser receives `WHERE a = 1 OR b = 2 AND c = 3`
- **THEN** the predicate tree is `OR(EQ(a,1), AND(EQ(b,2), EQ(c,3)))`, not `AND(OR(...), ...)`.

#### Scenario: BETWEEN produces a synthetic AND predicate
- **WHEN** the parser receives `WHERE age BETWEEN 18 AND 65`
- **THEN** the AST predicate is `AND(GE(age,18), LE(age,65))`.

### Requirement: Parse aggregate functions and GROUP BY
The parser MUST recognize `COUNT(*)`, `COUNT(<expr>)`, `SUM(<expr>)`, `AVG(<expr>)` inside SELECT projections and MUST parse an optional `GROUP BY <expr>[, ...]` clause into the Select AST.

#### Scenario: SELECT with COUNT(*) and GROUP BY
- **WHEN** the parser receives `SELECT dept, COUNT(*) FROM employees GROUP BY dept;`
- **THEN** the AST projections are `[(dept, COL), (COUNT(*), AGG)]` and `group_by=[dept]`.

### Requirement: Emit parse errors with position information
On any syntax error, the parser MUST raise a ParseError whose message includes the offending (line, column) and either the unexpected token or the expected token set.

#### Scenario: unexpected token reports position
- **WHEN** the parser receives `CREATE users (id INT);` (missing TABLE keyword)
- **THEN** it raises a ParseError that mentions (line=1, column=8) and the phrase "expected keyword TABLE".

### Requirement: Parser is a pure function of its input
The parser MUST NOT perform any I/O, MUST NOT mutate global state, and MUST be safe to invoke from multiple threads on the same instance.

#### Scenario: repeated parses on the same instance are independent
- **WHEN** the same parser instance parses `SELECT 1;` twice in succession
- **THEN** both calls return identical ASTs and the parser holds no residual state between the calls.
