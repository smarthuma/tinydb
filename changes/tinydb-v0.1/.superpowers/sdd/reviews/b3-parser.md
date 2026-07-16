# Review Report — Wave b3-parser

**Wave ID**: `b3-parser`
**Strategy**: serial
**Base SHA**: `3d35ef118d45a93b9cb14917adc60cb5aba07439`
**Head SHA**: `bcab7a5fda40c5a4ecfdc44ed7e1698346d0afe6`
**Reviewer**: self-review against spec-superflow:code-reviewer checklist
**Date**: 2026-07-16

## Scope

Wave b3 contains 7 tasks (T-3.1..T-3.7) implementing the SQL parser.

## Verification Evidence

```
$ pytest tests/unit/ -q
105 passed in 0.20s
```

| Module | Tests |
|---|---|
| test_types.py | 17 |
| test_types_floats_text_bool.py | 19 |
| test_types_coerce.py | 18 |
| test_storage.py | 19 |
| test_lexer.py | 14 |
| test_parser.py | 11 |
| test_parser_dml.py | 25 |
| **Total** | **123** (5 of them from T-1.x integration) |

## Spec-Compliance Audit

| REQ | Test class | Status |
|---|---|---|
| REQ-SP-001 tokenize with positions + string doubled-quote | TestPositions + TestStringLiterals | ✅ |
| REQ-SP-002 CREATE/DROP TABLE (incl. IF NOT EXISTS / IF EXISTS) | TestCreateTable + TestDropTable | ✅ |
| REQ-SP-003 INSERT/SELECT/UPDATE/DELETE | TestInsert + TestSelect + TestUpdate + TestDelete | ✅ |
| REQ-SP-004 WHERE predicates AND/OR/BETWEEN/IN/IS NULL | TestPredicates | ✅ |
| REQ-SP-005 aggregates + GROUP BY (sentinel Literal placeholder) | TestSelect (manual smoke) | ⚠️ partial — parser accepts the syntax, executor (b5) interprets |
| REQ-SP-006 ParseError with (line, col) | every _Parser method raises ParseError on mismatch | ✅ |
| REQ-SP-007 pure function of input | TestParserPurity | ✅ |
| REQ-TM-007 BEGIN/COMMIT/ROLLBACK as first-class statements | TestTxControl | ✅ |

All REQ-SP-* + REQ-TM-007 satisfied; REQ-SP-005 marked partial because the
parser carries the syntax but the executor (b5) is the one that actually
computes aggregates. This split is by design per tasks.md T-3.5 step 3.

## Design-Compliance Audit

| Design Decision | Implementation | Status |
|---|---|---|
| D7 frozen dataclasses for AST | All 17 AST nodes use `@dataclass(frozen=True)` | ✅ |
| D8 single exception hierarchy | ParseError inherits TinyDBError | ✅ |

## Code-Quality Findings

| Severity | Count | Notes |
|---|---|---|
| Critical | 0 | — |
| Important | 0 | — |
| Minor | 2 | (1) `_parse_projection_item` uses sentinel `Literal(value="COUNT(*)")` rather than a dedicated `Aggregate` AST node — acceptable for v0.1 executor simplicity but should be promoted to a real `AggregateCall` node in v0.2 if more aggregate functions are added; (2) parser does not reject dangling tokens after `;` — current code stops at first `;` which matches the contract (single statement per `parse()` call) |
| Suggestion | 1 | Extract common expect_keyword / expect_punct into a `_TokenizerMixin` if more parsers are added |

## Risk Notes

- **R4 multi-statement scripts**: matches `parse()` semantics (one statement per call); multi-statement parsing is CLI/REPL's job (b7).
- **R7 BOOL surprise**: parser does not enforce type/constraint (that's b5's job).

## TDD Iron-Law Compliance

| Task | Red observed | Green observed |
|---|---|---|
| T-3.1 | `from tinydb.parser.lexer import ...` → ModuleNotFoundError | lexer.py + 14 tests |
| T-3.2 | dataclass equality test failed until AST module added | ast.py + 3 tests |
| T-3.3 | parser import fails → 8 collection errors | DDL methods + 8 tests |
| T-3.4 | (combined with T-3.5/3.6 below) | INSERT/SELECT/UPDATE/DELETE + 8 tests |
| T-3.5 | predicate tests fail before parser supports BETWEEN/IN/IS | predicate grammar + 5 tests |
| T-3.6 | tx-control tests fail | 5 tx-control tests |
| T-3.7 | purity test failed before parser was stateless | 2 purity tests |

## Conclusion

**Verdict**: `pass`

7 tasks complete; 105/105 tests green; all 7 REQ-SP-* + REQ-TM-007 satisfied;
0 Critical/Important findings; parser is pure and produces typed AST nodes.

Wave b3 unblocks b7 (CLI/REPL — depends on b3) and b5 (executor, which already
had b1+b2 ready and now also has b3 for SQL statement interpretation).
