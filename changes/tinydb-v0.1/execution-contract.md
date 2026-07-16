# 执行合同 — tinydb v0.1

## Intent Lock

- **变更名称**：`tinydb-v0.1`（目录：`changes/tinydb-v0.1/`）
- **要解决的问题**：用造轮子的方式从零构建一个 Python 嵌入式关系型数据库，让开发者既能学透数据库核心原理（存储引擎 / SQL 解析 / 查询优化 / 索引 / 事务），又能把它作为可嵌入库用在真实项目里。
- **范围内**：纯 SQL 字符串接口；DDL（DROP/CREATE TABLE）+ DML（INSERT/SELECT/UPDATE/DELETE）；WHERE + AND/OR；ORDER BY/LIMIT/OFFSET；列约束（PRIMARY KEY / NOT NULL / UNIQUE）；COUNT/SUM/AVG + GROUP BY；B+ Tree 索引；INT/FLOAT/TEXT/BOOL 类型系统；基于 WAL 的 ACID 事务；单文件磁盘持久化；CLI/REPL（含 stdin 批处理）。
- **范围外**：多表 JOIN；并发控制（多线程/多进程）；ALTER TABLE、视图、触发器、外键；网络/客户端-服务器模式；任何第三运行时依赖；任何对网络、时钟、`subprocess` 的运行时依赖（仅 CLI E2E 测试使用）。

## Approved Behavior

- **已批准需求摘要**：7 个能力、49 条 `### Requirement:` 块、≥ 90 个 `#### Scenario:` 子句；每条都包含 `SHALL` 或 `MUST` 关键词，每条 scenario 都给出 WHEN/THEN。详见 `specs/sql-parser/spec.md`（7 REQ）、`specs/storage-engine/spec.md`（6 REQ）、`specs/query-executor/spec.md`（10 REQ）、`specs/btree-index/spec.md`（8 REQ）、`specs/transaction-manager/spec.md`（7 REQ）、`specs/type-system/spec.md`（7 REQ）、`specs/cli-repl/spec.md`（7 REQ）。
- **关键场景**（selection — 每个 capability 至少 1 个端到端代表）：
  - SQL Parser：`SELECT id, name FROM users WHERE age >= 18 ORDER BY name ASC LIMIT 10 OFFSET 5` → AST 含 columns/where/order_by/limit/offset 五个结构字段。
  - Storage Engine：4 KiB 页 + 8 字节 header（page_id u32 + page_type u8 + lsn u32）+ LRU 缓冲池 + alloc/free page id 复用。
  - Query Executor：插入 3 行 → UPDATE WHERE name='A' → 表变 `(1,X),(2,B),(3,X)`，返回 change_count=2；DELETE 无 WHERE 抛出 `UnsafeDeleteWithoutWhere`。
  - B+ Tree：10k 行 INT 索引，删除后 underflow 触发 merge 或 redistribute；TEXT 索引按 UTF-8 字节序排列（`Banana` < `apple`）。
  - Transaction Manager：`BEGIN; INSERT; COMMIT;` 后即使 kill -9 重启也保留该行；`BEGIN; INSERT; ROLLBACK;` 之后查不到。
  - Type System：BOOL 列插入 `0`（Python int）→ `TypeMismatch(expected='BOOL', got='INT')`；INT 列插入 `2**63` → `IntegerOverflow`。
  - CLI/REPL：`printf 'CREATE TABLE t(id INT);\nINSERT INTO t VALUES (1);\n' | tinydb test.db` 退出码 0，`tinydb test.db` 进入 REPL 后 `.tables` 列出 `t`。
- **验收检查**（DP-6 发布门 4 项）：
  1. `pytest tests/ -q` 全绿，无 skip/xfail。
  2. `pytest --cov=tinydb --cov-fail-under=80` 报告 ≥ 80% 行覆盖。
  3. `scripts/scope_audit.py`（自写小脚本，≈ 50 LOC）对比 proposal.md 的 Out-of-Scope 列表 vs git diff，零违规。
  4. `pip install -e .` 后 `python -c "import tinydb, sys; print([m for m in sys.modules if m.startswith('tinydb')])"` 不引入任何第三方包（仅 stdlib + 测试期 pytest/pytest-cov/mypy/ruff）。

## Design Constraints

- **架构约束**：7 capability → 7 子模块（`tinydb/{parser,storage,wal,index,executor,tx,cli,types}.py`），层间只通过 typed dataclass AST 与 storage 接口通信（design D1, D7）。
- **接口约束**：见 `tasks.md` ## Interfaces 块。`Parser → Executor` 走 `@dataclass(frozen=True)` AST；`Executor → Storage/Index/Tx` 走显式方法签名（无 string-keyed dict，无全局状态）。
- **依赖约束**：运行时 = Python 3.10 标准库。开发期依赖（pytest / pytest-cov / ruff / mypy）通过 `[project.optional-dependencies] dev` 隔离，不进入 wheel。
- **数据约束**：单文件 `.db`；页大小 4096（configurable 512..65536）；little-endian；B+ Tree order 64（10k 行高度 2–3）；WAL 长度前缀 + LSN + checksum；catalog 固定在 header page（page 0）；UTF-8 文本存储；int64 INT；IEEE-754 binary64 FLOAT；bool = 1 byte（design D2..D5）。

## Execution Plan

走 **full** workflow。9 个 batch，对应 tasks.md 的 B1..B9。**不**在 contract 中固执行模式 — DP-4 时由 build-executor 调用 `ssf execution recommend <change-dir>` 列出 inline / batch-inline / sdd 三种候选模式与推荐理由，由用户选择；本 contract 留占位等 DP-4 回填。

## Execution Waves

按 tasks.md 的 9 个 batch 划分；wave 编号与 batch 一致。每完成一个 wave 必须用 `ssf execution review` 写 review receipt（`pass` 或 `fail`），下一 wave 才能开始。

### Wave 1 (B1 — Type System)

- **Wave ID**：`b1-type-system`
- **任务**：T-1.1..T-1.4 — `pyproject.toml` + `tinydb/types.py` + `tinydb/__init__.py`（仅 exception 重导出）+ `tests/unit/test_types.py`
- **依赖 wave**：无
- **策略**：`serial`（B1 太小，并行无收益）
- **目标**：4 种类型的 encode/decode 往返 + coerce_in + NULL + exception hierarchy 全部单测绿。
- **输入**：无
- **输出**：`tinydb/types.py` 提供 `encode/decode/coerce_in` + 8 个异常类；`test_types.py` 至少 12 个测试全过。
- **完成标准**：`pytest tests/unit/test_types.py -q` 全绿；无 mypy 错误。
- **Review gate**：`reports/b1-review.md`；base/head SHA 取自 `git rev-parse HEAD~1..HEAD`；review receipt 写入 `execution review b1-type-system ... --verdict pass`。

### Wave 2 (B2 — Storage Engine)

- **Wave ID**：`b2-storage`
- **任务**：T-2.1..T-2.5 — page header codec、FileStore、BufferPool LRU、alloc/free/fsync、单文件持久化集成测试。
- **依赖 wave**：b1-type-system
- **策略**：`serial`
- **目标**：4 KiB 页固定布局，alloc/free 复用，LRU 驱逐脏页前 fsync。
- **输入**：B1 的 `types.py`（仅为字节序参考）
- **输出**：`tinydb/storage.py` + `tests/unit/test_storage.py`（含 1000-page 压力测试）
- **完成标准**：`pytest tests/unit/test_storage.py -q` 全绿；reopen 后字节级一致。
- **Review gate**：同上模式。

### Wave 3 (B3 — SQL Parser)

- **Wave ID**：`b3-parser`
- **任务**：T-3.1..T-3.7 — lexer、AST dataclasses、CREATE/DROP/INSERT/SELECT/UPDATE/DELETE 解析、predicate/aggregate/parse-error、tx-control、purity test。
- **依赖 wave**：b1-type-system（仅 enum 共享约定）
- **策略**：`serial`
- **目标**：每个 REQ-SP-* 子句至少有 1 个 pytest 解析测试覆盖；两次连续 parse 无状态泄漏。
- **输入**：B1 的 exception 类（ParseError）
- **输出**：`tinydb/parser/{__init__,ast,lexer,parser}.py` + `tests/unit/test_parser.py`
- **完成标准**：REQs → 至少 7 个 REQ × ≥1 测试 = 7+ 测试通过；pure-function 测试通过。
- **Review gate**：同上模式。

### Wave 4 (B4 — B+ Tree Index)

- **Wave ID**：`b4-btree`
- **任务**：T-4.1..T-4.6 — leaf/internal codec、seek/range、insert+leaf-split、root promotion+internal split、delete+merge/redistribute、dedicated index pages+TEXT ordering。
- **依赖 wave**：b2-storage
- **策略**：`serial`
- **目标**：5000 随机 key 插入/删除往返与 `SortedDict` 神谕一致；TEXT 索引按 UTF-8 字节序；所有页 `page_type=INDEX`。
- **输入**：B1 encode/decode、B2 FileStore/BufferPool
- **输出**：`tinydb/index.py` + `tests/unit/test_index.py`
- **完成标准**：所有 B4 测试绿；indexed-page-type 测试通过；randomized 5000-key 测试通过。
- **Review gate**：同上模式。

### Wave 5 (B5 — Query Executor)

- **Wave ID**：`b5-executor`
- **任务**：T-5.1..T-5.9 — catalog、heap、INSERT/SELECT-no-WHERE、WHERE evaluator、UPDATE/DELETE-safe、ORDER BY+LIMIT/OFFSET、aggregates+GROUP BY、index-aware executor、DROP TABLE frees pages。
- **依赖 wave**：b1-type-system、b2-storage、b4-btree
- **策略**：`serial`
- **目标**：每个 REQ-QE-* 子句至少 1 个 executor 测试；索引路径与全表扫描路径都有覆盖。
- **输入**：B1 types、B2 storage、B4 index
- **输出**：`tinydb/executor.py` + `tests/unit/test_executor.py`
- **完成标准**：REQs → 10 REQ × ≥1 测试 = 10+ 测试通过；DROP TABLE 文件大小不增长。
- **Review gate**：同上模式。

### Wave 6 (B6 — Transaction Manager / WAL)

- **Wave ID**：`b6-tx`
- **任务**：T-6.1..T-6.6 — WAL record codec、append+fsync、BEGIN/COMMIT/ROLLBACK 状态机、Executor 写 WAL、crash recovery、CHECKPOINT。
- **依赖 wave**：b2-storage、b5-executor
- **策略**：`serial`
- **目标**：`BEGIN; INSERT; kill -9; reopen` 一致恢复；`BEGIN; INSERT; ROLLBACK;` 后行不可见；`CHECKPOINT` 后 WAL 为 0 字节。
- **输入**：B5 executor
- **输出**：`tinydb/{wal,tx}.py` + `tests/unit/test_tx.py` + `tests/e2e/test_crash_recovery.py`（首版）
- **完成标准**：所有 B6 测试绿；crash recovery subprocess 测试 3 次连续不 flake。
- **Review gate**：同上模式。

### Wave 7 (B7 — CLI / REPL)

- **Wave ID**：`b7-cli`
- **任务**：T-7.1..T-7.6 — CLI entry、REPL loop、dot-commands、multi-line + non-fatal errors、stdin batch、CLI ↔ TxManager。
- **依赖 wave**：b3-parser、b5-executor、b6-tx
- **策略**：`serial`
- **目标**：`tinydb sample.db` 启动 REPL；`.tables` / `.schema` / EOF 行为正确；stdin batch 失败时非零退出。
- **输入**：B3 parser、B5 executor、B6 tx
- **输出**：`tinydb/cli.py` + `tests/e2e/test_cli_repl.py`
- **完成标准**：所有 REQ-CR-* 子句有 subprocess 测试覆盖；typo 不终止 REPL；`--version` 退出 0。
- **Review gate**：同上模式。

### Wave 8 (B8 — E2E & Polish)

- **Wave ID**：`b8-polish`
- **任务**：T-8.1..T-8.5 — 完整 SQL tour E2E、10k-row benchmark、crash recovery subprocess、coverage ≥ 80%、ruff+mypy 干净。
- **依赖 wave**：b1..b7 全部
- **策略**：`serial`
- **目标**：CI 5 步（pytest / cov / scope-audit / external-deps / lint+mypy）全绿。
- **输入**：完整 tinydb 包
- **输出**：`tests/e2e/*` + `pyproject.toml` 增加 ruff/mypy 配置
- **完成标准**：5 个 CI 命令全绿；10k-row benchmark 平均 < 1 ms/lookup。
- **Review gate**：同上模式；额外要求 `pytest --cov=tinydb --cov-fail-under=80` 通过。

### Wave 9 (B9 — Docs & Release)

- **Wave ID**：`b9-release`
- **任务**：T-9.1..T-9.4 — README quickstart、architecture 交叉引用表、`v0.1.0` tag、DP-7 audit 报告。
- **依赖 wave**：b1..b8 全部
- **策略**：`serial`
- **目标**：所有 7 个 DP 字段在 `.spec-superflow.yaml` 都有时间戳；release notes 列出 7 个能力的对应 spec 文件。
- **输入**：完整 tinydb + 全套测试 + design.md + specs/
- **输出**：`README.md`、`docs/architecture.md`、`docs/decision-point-audit.md`、git tag `v0.1.0`
- **完成标准**：`ssf audit .` 列出 dp_0..dp_7 全部条目；git tag 存在；archive 脚本能正常移动 `changes/tinydb-v0.1/` 到 `changes/archive/`（DP-7 触发）。
- **Review gate**：同上模式。

## Test Obligations

- **必须先从失败测试开始的行为**：每个 task 的 TDD 步骤 1（Red）必须先生成 pytest failure 才能 commit。CI 在 pre-commit hook 强制：`pytest --collect-only` 通过 + `git diff HEAD~1` 中无 `.pyc`、无 `__pycache__`。
- **必需的边界情况**：
  - INT 溢出（`2**63`、`-2**63 - 1`）
  - TEXT 空字符串 + 非 ASCII（`''`、`'你好, tinydb 🚀'`）
  - BOOL 拒绝 `0`/`1`/`'true'`/`'false'`
  - WHERE NULL 比较不命中（`NULL = NULL` 为 false）
  - BETWEEN 边界（inclusive 两端）
  - IN 空列表 → 零行
  - LIMIT 0 → 零行
  - ORDER BY 列类型不匹配 → TypeError
  - B+ Tree 删除到 underflow 触发 merge 或 redistribute
  - WAL 校验和损坏 → `TransactionLogCorrupt`
  - REPL EOF (Ctrl-D) 退出码 0
  - REPL 多行 SQL 中含 `;` 的字符串字面量
- **回归敏感区域**：
  - `tinydb/storage.py` — 任何 IO 路径改动都必须重跑 `tests/e2e/test_crash_recovery.py` 3 次。
  - `tinydb/wal.py` — 任何 record layout 改动都必须重跑全部 B6 测试 + 1 次手工 `kill -9` 演练。
  - `tinydb/parser/parser.py` — predicate precedence 改动必须保留现有测试并增加 corner-case。
  - `tinydb/index.py` — split/merge 改动必须跑 randomized 5000-key 测试 10 次。

## Execution Mode

- **可用方式与推荐**：`ssf execution recommend /home/wfj/新建文件夹/开发tinydb/changes/tinydb-v0.1`（将在 DP-4 阶段由 build-executor 调用并把结果回填到本节）。候选：`inline` / `batch-inline` / `sdd`。
- **用户确认的模式**：_Pending DP-4_
- **推荐理由 / 项目事实**：_Pending DP-4_
- **非推荐选择的风险确认**：_Pending DP-4_
- **执行计划命令**：_Pending DP-4_
- **允许的修订**：升级 `sdd` 用 `ssf execution revise`；不允许降级。
- **计划 revision / artifact hash**：_Pending DP-4_

## Verification Dimensions

| 维度 | 状态 | 发现 |
|------|------|------|
| Completeness | Pending | 每个 SHALL/MUST 至少一个 pytest 覆盖；49 REQ × ≥1 = ≥ 49 测试目标 |
| Correctness | Pending | B+ Tree 神谕测试 + WAL crash recovery + REQ-CR-* subprocess 测试 |
| Coherence | Pending | design.md 8 Decisions ↔ 代码命名一致；catalog 在 header page 等 |

**总体结论**：Pending

## Review Gates

- **强制审查点**：每个 Execution Wave 完成后调用 `ssf execution review <change-dir> --wave <wave-id> --base <sha> --head <sha> --report <path> --verdict pass|fail`。`pass` 是后续 wave 与最终 closing 的硬门槛。
- **阻塞类别**：依赖 wave 未通过；review receipt 缺失；review receipt 为 `fail`；execution plan revision 与当前 artifacts_hash 不一致。
- **收口条件**：b1..b9 共 9 个 review receipt 全部 `pass`；`execution_plan_hash` 与 `artifacts_hash` 一致；CI 5 命令全绿。

## Escalation Rules

- **何时回退到 `specifying`**：
  - 任何 REQ 的 scenario 描述与实现语义出现不可调和的分歧（例如 `BETWEEN` 实测为半开）。
  - `pytest -q` 失败且定位到 spec 本身错误（不是实现错误）。
  - 新增一个能力（增加第 8 个 `specs/*/spec.md`）。
- **何时回退到 `bridging`**：
  - 任何 Design Decision 改变（页大小 / B+ 树 order / WAL 格式 / catalog 位置 / 错误层次）。
  - batch 切分需要重组（9 个 batch → 不同粒度），且 `tasks.md` 必须重写。
  - scope fence 变化（In/Out 列表加减项）。
- **何时不得继续实现**：
  - 当前 wave 的 review receipt 为 `fail` 且两轮内未修复。
  - 连续 2 个 batch 触发 `bug-investigator` 而非 `build-executor`。
  - 覆盖率连续 2 个 wave 下降且低于 70%（DP-0 强约束是 80%）。
  - 引入任何运行时第三方依赖（违反 DP-0 constraints）。
