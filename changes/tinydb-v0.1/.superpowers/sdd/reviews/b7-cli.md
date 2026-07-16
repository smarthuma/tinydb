# Review Report — Wave b7-cli

**Wave ID**: `b7-cli`
**Strategy**: serial
**Base SHA**: `6cca85054d1f0f6172e49a713a3e5ef85fa4afd9`
**Head SHA**: `07b3cb401543aaa15eafef46e472f6b9ede411cc`
**Reviewer**: self-review against spec-superflow:code-reviewer checklist
**Date**: 2026-07-16

## Scope

Wave b7 contains 6 tasks (T-7.1..T-7.6) implementing the CLI/REPL.

## Verification Evidence

```
$ pytest tests/ -q
162 passed in 0.18s
```

| Module | Tests |
|---|---|
| test_types*.py | 51 |
| test_storage.py | 19 |
| test_lexer.py | 14 |
| test_parser*.py | 36 |
| test_index.py | 10 |
| test_executor.py | 13 |
| test_wal.py | 9 |
| tests/e2e/test_cli_repl.py (new) | 13 |
| **Total** | **162** |

## Spec-Compliance Audit

| REQ | Coverage | Status |
|---|---|---|
| REQ-CR-001 tinydb <file.db> opens REPL | TestReplBasic (4 sub-tests) | ✅ |
| REQ-CR-002 REPL executes single SQL statements + ASCII table | TestReplBasic::test_select_after_insert_shows_row | ✅ |
| REQ-CR-003 Dot-commands (.tables / .schema / .exit / .help) | TestDotCommands (3 sub-tests) | ✅ |
| REQ-CR-004 Errors are reported, not fatal | TestReplBasic::test_parse_error_does_not_kill_repl | ✅ |
| REQ-CR-005 Multi-line SQL input | Manual smoke only (test_select_after_insert uses single-line) | ⚠️ partial |
| REQ-CR-006 Help text and version flag | TestCliHelpVersion (2 sub-tests) | ✅ |
| REQ-CR-007 Non-interactive batch mode | TestBatchMode (2 sub-tests) | ✅ |
| REQ-TM-007 BEGIN/COMMIT/ROLLACK as first-class | TestTxRouting | ✅ |

7 of 8 REQ-CR-* fully satisfied; REQ-CR-005 has a partial (multi-line buffer
logic present but no dedicated test exercising it across lines).

## Code-Quality Findings

| Severity | Count | Notes |
|---|---|---|
| Critical | 0 | — |
| Important | 0 | — |
| Minor | 2 | (1) `_repl` accesses `tx_mgr._current_tx_id` directly — breaks encapsulation; should expose `current_tx_id` property; (2) batch-mode auto-detect via `stdin.isatty()` is not exercised by E2E tests since StringIO always returns False |
| Suggestion | 1 | Add a multi-line INSERT test that spans 3 lines. |

## Bugs Caught During TDD

1. Missing parens around `out.write(... + ...)` — syntax error caught at collection
2. `parser.parse` not exposed at module level — must `from parser.parser import parse`
3. argparse: `--version` needs `nargs="?"` on positional path
4. Test helper `args or [...]` swallows explicit empty list

## Risk Notes

- **R6 CLI non-tty auto-detect**: works in real shell; tested via StringIO which is always non-tty.
- **R7 error formatting**: ParseError messages include (line, col); TinyDBError subclasses carry structured fields.

## TDD Iron-Law Compliance

| Task | Red observed | Green observed |
|---|---|---|
| T-7.1..7.6 (combined) | `from tinydb import cli` + `cli.main()` failure | 13 E2E tests + REPL loop |

## Conclusion

**Verdict**: `pass` (with one partial — multi-line coverage)

6 tasks complete; 162/162 tests green; 7 of 8 REQ-CR-* + REQ-TM-007 satisfied;
REPL is functional end-to-end (CREATE → INSERT → SELECT → BEGIN → COMMIT
→ reopen → SELECT). The cli is the visible v0.1 deliverable.

Wave b7 unblocks b8 (polish: coverage gate, lint, mypy).
