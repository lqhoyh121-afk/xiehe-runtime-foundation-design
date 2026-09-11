# M1 本机隔离运行说明

署名：Laiqh。状态：本机候选，待主控独立复核；不代表共享架构冻结或生产许可。

## 能做什么

真实前台 CLI 注册、显式启用、创建 Case，运行一个获准的纯 CODE 节点，SQLite 原子保存状态、幂等结果、事件和证据；所有旧命令进程退出后，新进程读取同一 Case。输出始终标记 `contract_status=DRAFT`、`synthetic_only=true`、`production_authorized=false`。

本机只有合成试件，不访问网络、EAM、钉钉、AI 模型或真实业务账号。`message/echo` 字段和规则全部在 `synthetic_providers.py`，不是运行核心内置业务。测试宿主的权威 JSON、当前权限、时钟、撤销下界和 SQLite 不是生产安全边界；控制同一 OS 的人仍能改文件，不能拿本工具冒充跨机权威。

## 运行前

在正式 assignment 对应工作树根目录运行。沿用已核验解释器及现有 `jsonschema`，不修改共享依赖文件；验收器内部统一使用 `sys.executable`。本轮使用 Python 3.11、SQLite；确切版本和测试数量以本机证据为准。

```bash
python -B tools/verify_workspace.py --assignment .local/assignment.json
```

沙箱必须是**本工作树 `.local/` 内尚不存在的子目录**。任何已存在沙箱、越界路径、符号链接/junction 都拒绝。不能以删除旧沙箱的方式“恢复授权”；新验证使用不同的新目录和报告名。

## 一条命令看完整链路

```bash
python -B tools/verify_runtime_m1.py --sandbox .local/m1-demo-run --scenario normal --report .local/m1-demo-report.json --show-commands
```

这不是拼出来的演示输出：验收器逐个启动真实 CLI、打印实际 argv/PID/退出码/stdout，读回真实 registration_id/Case ID，再构造后续请求；运行结束按 manifest 清理自建沙箱，新进程核对路径不存在。报告保留在沙箱外，不覆盖既有报告。

`normal` 验收过程会自动清理沙箱。若要留下 Case 手动查，按下一节使用 CLI；手动建立的沙箱不会由其他验证运行清理。

## 手动 CLI

```bash
python -B tools/runtime_core_cli.py --sandbox .local/m1-manual host-init
python -B tools/runtime_core_cli.py --sandbox .local/m1-manual register --request .local/m1-manual/requests/register.json
```

从返回值取得 `registration_id`。在 `requests` 下写启用请求，外形仅允许 `request_id,idempotency_key,payload`；payload 是实际 `registration_id`、`expected_revision:1`、`target_state:"ENABLED"`。ID 必须符合共享 Id 约束，不能抄用示例单号。随后：

```bash
python -B tools/runtime_core_cli.py --sandbox .local/m1-manual set-state --request .local/m1-manual/requests/enable.json
python -B tools/runtime_core_cli.py --sandbox .local/m1-manual create --request .local/m1-manual/requests/create.json
```

create payload 仅 `registration_id,input_ref,object_refs`；后两项完整复制本次 host-init 的真实返回对象，不凭猜测填摘要、范围或时间。读取 create 返回的 Case ID，替换下面 shell 变量的值：

```bash
python -B tools/runtime_core_cli.py --sandbox .local/m1-manual run-once --case-id "$CASE_ID"
python -B tools/runtime_core_cli.py --sandbox .local/m1-manual snapshot --case-id "$CASE_ID"
python -B tools/runtime_core_cli.py --sandbox .local/m1-manual events --case-id "$CASE_ID"
python -B tools/runtime_core_cli.py --sandbox .local/m1-manual host-inspect
python -B tools/runtime_core_cli.py --sandbox .local/m1-manual host-cleanup --manifest .local/m1-manual/manifest.json
```

每条命令立即运行、结束即退出，无常驻服务。成功状态应为 `QUEUED/r1 → RUNNING/r2 → SUCCEEDED/r3`；Case 事件严格为 `CASE_CREATED,NODE_READY,NODE_LEASED,NODE_STARTED,NODE_SUCCEEDED,CASE_SUCCEEDED`。登记的两条事件不算 Case 事件；全局 watermark 不等于 Case 事件数。

## 状态与失败边界

- REGISTERED 不是 ENABLED。STOP_NEW 只拒绝新单，不终止在途 Case；不可重新启用停新单记录。
- 当前原操作权限及读取权限先于历史重放。授权被撤后，已存在和未知请求键均拒绝，不透露原 Case。
- 相同作用域/操作/目标/键/语义摘要返回原结果；仅换 request_id 不执行 Provider。同键改内容报 IDEMPOTENCY_CONFLICT。
- 历史 create 即使 Case 现已成功，也仍返回原 QUEUED/r1；当前状态另查 snapshot。
- 执行前与首次提交均检查 owner/attempt/lease/30 秒期限、当前 P1/P2 权威及绑定；提交重新调用规则及输入输出校验。真实 monotonic 耗时与合成时钟双重门禁。
- claim、submit 各自独立原子提交，不把整条 run-once 称为单事务。领取后崩溃保持 RUNNING；到期查询显示 LEASE_LOST，不自动重领、续 lease、标 FAILED 或重新执行。
- 成功 submit 的合法历史重放不续 lease、不重新执行 Provider；终态换新键提交拒绝。
- 快照在 SQLite 同一只读事务读取 Case、节点、事件水位。事件最多 100 条完整窗口；超限或 cursor/filter/limit 明确拒绝，不截断。
- `.local` 下 `host` 保存受信合成控制、输出候选及原始提交意图，`requests` 是不可信请求，`runtime` 保存运行台账，`observations` 仅测试 PID/Provider 调用/屏障，不当作业务事件。公开 snapshot/inspect 不输出 lease 秘密。

| 退出码 | 含义 |
|---|---|
| 0 | 当前命令成功；登记/查询/重放成功不等于业务新完成 |
| 2 | 输入、权限、契约、幂等、版本、能力、状态或失租拒绝 |
| 3 | IN_PROGRESS、锁或暂时依赖不可用；不会自动后台重试 |
| 4 | 存储损坏/不兼容或意外内部错误；脱敏且保持拒绝 |
| 86 | 固定验收故障点 `os._exit(86)`；必须独立回读，不视为成功 |

## 固定测试宿主通道（不是业务 Agent 工具）

`host-control --scenario` 只接受内置枚举，没有任意函数、SQL、模块路径、auth_context 或通用恢复权限入口：

- 权限/权威：`revoke-operation,revoke-read,revoke-provider,revoke-grant,authority-gap,authority-stale,authority-rollback,fake-admission,unknown-provider,missing-implementation,mutate-definition`。
- 时钟/材料/规则：`advance-past-deadline,mutate-input,tamper-input,expire-input,output-mismatch,deny-rule,needs-input,rule-unavailable`。
- 准入反例：`publish-ai,publish-human,publish-multi-node,publish-wait,publish-readback,publish-action,publish-resources,publish-retry,publish-timeout,publish-wrong-role,publish-condition,publish-cycle,publish-version-conflict`。发布的是独立合成变体，结构合法性仍交原 validator。
- 事务故障：`fault-create-POINT`、`fault-submit-POINT`，POINT 为 `after_state,after_idempotency,after_events,before_commit,after_commit_before_response`；`disarm-fault` 只撤测试注入，不恢复权限/撤销状态。
- `release-query` 仅释放本机测试观察屏障，不改授权 revision，以便验证同一授权下的真实读写交错。

`host-test --case-id ACTUAL_ID --scenario NAME` 仅固定内部 Worker 反例：

- `claim-crash,prepare-crash,claim-replay,submit-replay,submit-new-key,execute-expired`。
- `submit-bad-owner,submit-bad-attempt,submit-bad-lease,submit-expired,submit-elapsed`。
- `submit-mutate-input,submit-tamper-input,submit-expire-input,submit-revoke-provider,submit-revoke-grant,submit-deny-rule,submit-needs-input,submit-rule-unavailable,submit-output-mismatch`。
- `submit-fault-POINT` 使用上述五个事务故障点。
- `snapshot-barrier` 在真实只读视图建立后等待另一前台命令提交；`event-overflow` **仅为自建 Case 注入 101 条明确标记的 SYNTHETIC_OVERFLOW_FIXTURE 测试污染事件**，用来证明超限拒绝。它不是合法运行事件生成器或生产写入口。

领取原请求、领取结果、输出引用和完整提交意图在宿主本地留痕；只有 runtime 中原子接受的结果才是完成证据。旧键重放通过测试通道显式验证，不等于提供了中断任务自动恢复。

## 全量验证

下列示例沙箱和报告路径必须尚不存在；已有一次证据时换新后缀，不覆盖旧报告：

```bash
python -B -m pytest tests/runtime_m1 -q -p no:cacheprovider --junitxml=.local/m1-l1.xml
python -B tools/verify_runtime_m1.py --sandbox .local/m1-acceptance-new --scenario all --report .local/m1-acceptance-new-report.json
python -B -m pytest spikes/002-authority-contract -q -p no:cacheprovider --junitxml=.local/m1-authority.xml
python -B -m pytest tests/test_collaboration_docs.py -q -p no:cacheprovider --junitxml=.local/m1-docs.xml
python -B tools/audit_tree.py
python -B tools/verify_workspace.py --assignment .local/assignment.json
```

验证器的九个实际场景：`normal,registration,trust,idempotency,atomicity,stale,restart,query,capabilities`，以及 `all`。验证器不 import service/store，以真实子进程与另一个新 Python 进程中的 SQLite URI 只读连接取证；期望事件、revision、输出摘要和行数来自手写验收要求，不调用核心计算预期。

L1 含字段、摘要固定预像向量、契约、幂等与负例；部分 pytest 也跑真实进程，但最终 L2 另以独立验收器报告为准。报告逐项记录 F01–F18、实际 PID/退出码、逻辑行、清理及失败，不把文档测试或旧 authority 成绩算成 M1 成功。

`audit_tree.py` 默认只扫跟踪文件，本卡新文件未 stage：最终交接另对 assignment 的全部新文件应用同源审计规则，检查绝对路径/凭据/空白及原文件摘要。不准通过 stage 扩大扫描范围。

## 清理与未验证项

只清理本轮 host-init manifest 所属目标；活动的自建进程、junction/symlink 或所有权不符即拒绝，不终止无关 PID。成功验收场景先记录最后状态和逻辑表，确认所有子进程退出，再清理并由新进程确认；失败场景默认保留精确沙箱及报告，修复后再按该 manifest 安全清理。保留的合成 RUNNING/LEASE_LOST 证据不冒称任务成功。

尚未实现/验证：M2 等待恢复、M3 路由汇合、M4 自动超时重试取消、M5 多 Worker/资源/分页、M6 外部副作用、真人 L3、生产 L4、跨机权威与安装分发。主控独立审阅与接收也是单独闸门；本卡不自行进入 M2，不提交、合并或推送。
