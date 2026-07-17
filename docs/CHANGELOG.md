# Changelog — tinydb

所有 tinydb 版本的发布说明。归档格式基于 [Keep a Changelog](https://keepachangelog.com)。

## [v0.1.0] — 2026-07-17

### Added

- **SQL Parser**：词法分析 + 递归下降解析器，支持 DDL/DML/SELECT/UPDATE/DELETE/事务控制
- **类型系统**：INT/FLOAT/TEXT/BOOL + NULL 序列化与强制类型校验
- **存储引擎**：4 KiB 固定页 + 单文件 `.db` 持久化 + LRU 缓冲池 + fsync
- **B+ Tree 索引（完整）**：等值/范围查询 + split + `CREATE [UNIQUE] INDEX` SQL 入口 + `DROP INDEX`（merge 仍 v0.2）
- **查询执行器**：catalog 在 header page、heap 表、WHERE 谓词求值、ORDER BY/LIMIT/OFFSET、COUNT/SUM/AVG + GROUP BY（MIN/MAX 未实现）
- **事务管理（完整）**：REPL BEGIN/COMMIT/ROLLBACK 真正在执行器层生效（snapshot-based rollback + WAL record）
- **CLI / REPL**：交互式 SQL 终端 + dot-commands + multi-line + stdin 批量模式（`-c` flag 未实现）

### Test Coverage

- 171 pytest tests（11 unit + 2 e2e），100% 通过
- 81.83% 行覆盖率（DP-0 gate ≥ 80% ✅）
- 32 手工 REPL 端到端用例（10 大功能类别），100% 通过
- 7 个规格 × ~52 REQ × ≥ 90 scenario，每个有 ≥ 1 pytest

### Documentation

- `README.md` — 快速开始 + 库使用 + CLI/REPL 教程
- `docs/architecture.md` — 规格到模块交叉引用表
- `TEST-REPORT.md` — pytest 自动化测试报告
- `docs/功能测试报告.md` — 手工 REPL 端到端测试报告（32 用例）
- `changes/archive/tinydb-v0.1/` — 完整 spec-superflow 制品（proposal / specs / design / tasks / execution-contract + 9 wave review + decision-point-audit）

### Spec-Superflow 状态

- 9 SDD wave 全部 pass review receipt
- 8/8 DP 决策点全部留痕（DP-0..DP-7）
- 8/9 wave 完整覆盖（b6 仅 3/6 task 实施 + 3 task 文档化延期 v0.2）

### Known Limitations (deferred to v0.2)

- `Wal.replay()` 已实现但未在 `FileStore.open` 中调用（crash recovery 端到端未接线）
- B+ Tree leaf-level delete 不触发 merge / redistribute（v0.2）
- executor 仍以 heap 扫描为主（未使用索引路径加速 SELECT，v0.2 优化）
- `CHECKPOINT` SQL 命令未添加 parser 分支
- TEXT B+ tree ordering test 缺失
- 10k 行性能基准测试未跑

[unreleased]: https://github.com/smarthuma/tinydb/compare/v0.1.0...HEAD
[v0.1.0]: https://github.com/smarthuma/tinydb/releases/tag/v0.1.0