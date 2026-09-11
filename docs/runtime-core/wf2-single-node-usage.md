# WF2 单节点真实包接入先导

署名：Laiqh。DRAFT / TEST ONLY / production_authorized=false。

这是一个已审固定包的本机接入先导，不是完整 WF2、M2、生产安装器或任意 Python 插件平台。合并、远程同步、发布和生产权限均不由安装/测试结果授予。

## 支持范围

固定安装计划 `normalize-l3-v1` 绑定：

- 一个 CODE / OUTPUT_VALIDATED 节点，同步 `normalize(value)`，`helpers=[]`。
- 精确 ProviderRef、完整包/材料/工具文件摘要、入口和 ABI `sync-json-v1`。
- 安装记录版本 `wf2-install-v1`、Adapter 版本 `python-component-v1` 及其固定源码摘要。
- 本机解释器及允许的模型校验依赖身份；安装后运行环境身份变化也会拒绝。
- 原 Service 的注册、显式启用、创建、领取、接纳、幂等、事件和 SQLite 事务。原 M1 CLI/Host 默认行为保留；失败时没有跨宿主回退。

作者只接收已验证输入 JSON 的深拷贝，不得到 EvidenceRef、Host、Store、P2 或 lease。输入不得修改，返回必须属于 canonical JSON 子集并通过精确输出模型。Executor 编译并调用安装副本中同一份已核验字节，不按路径 import、不使用字节码缓存或缓存 callable。Validator 使用独立边界扫描校验结果，不调用作者函数充当 oracle。

规则要求 text 至少包含一个非 U+0020 字符；纯空格在领取/执行之前返回 RULE_DENIED。只去除首尾 U+0020，不删除内部双空格、tab、换行或 NBSP。

## 前提与路径

由本机任务绑定提供以下变量，全部使用 forward-slash 绝对路径，不把实际路径写入仓库或远程系统：

- `WF2_TOOL_ROOT`：已锁定的只读 WF1 工具根，含所需原版共享契约依赖；不是作者 request 字段。
- `WF2_REFERENCE_ROOT`：验收使用的只读快照根，包含 `l3/package`、`l3/materials`。仅测试/验收器使用。
- `PACKAGE_COPY`、`MATERIALS_COPY`：自己新生成的副本，不能指向已验成品进行覆盖。
- `SANDBOX`：当前获准工程树 `.local` 下尚不存在的新子目录；其父目录须由本轮拥有。
- `INSTALL_RESPONSE`、`REGISTER_RESPONSE`、`CREATE_RESPONSE`、各 request 文件和报告：本轮 `.local` 中的自有文件。

不要安装新依赖或升级冻结工具来绕过不匹配。依赖或源版本漂移须回到范围/批准流程。安装器没有接收任意 Python 路径、approved=true 或计划 JSON 的接口。

## 从真实生成物到成品

在固定工具根运行：

```bash
python -B tools/workflow_author.py init --template single-code-output-v1 --output "$PACKAGE_COPY" --format json
python -B tools/workflow_author_synthetic.py prepare --output "$MATERIALS_COPY" --format json
```

工具要求目标父目录已存在、目标本身不存在。生成后只补入已审作者内容：

- `package-manifest.json`
- `definitions/workflow-projection.json`
- `components/normalize-submission/declaration.json`
- `components/normalize-submission/implementation.py`
- `components/normalize-submission/test_normalize.py`
- `acceptance.md`

不替换生成的 Skill 资产，不改原工具/包/材料。逐文件核对成品与冻结版本一致后执行：

```bash
python -B tools/workflow_author.py check --package "$PACKAGE_COPY" --format json
python -B tools/workflow_author_synthetic.py check --package "$PACKAGE_COPY" --materials "$MATERIALS_COPY" --format json
```

第一条独立 checker 没有 TrustedContext，保留其 `INCOMPLETE` / 退出码 4 / `TRUST_CONTEXT_REQUIRED`；这是静态层语义，不是核心数据库损坏。第二条固定合成材料检查须为 PASSED，但仍不是运行消费授权。安装时另核受信固定计划与运行 P2。

## 安装和核心操作

回到获准工程根，显式设置上述环境变量。安装返回的 `result` 包含 installation_id、record_digest、输入 EvidenceRef/object_refs、register_request 和 manifest 路径。

```bash
python -B tools/runtime_package_cli.py --sandbox "$SANDBOX" install --package "$PACKAGE_COPY" --materials "$MATERIALS_COPY" --fixture normalize-l3-v1 > "$INSTALL_RESPONSE"
python -B tools/runtime_package_cli.py --sandbox "$SANDBOX" install-inspect
python -B tools/runtime_package_cli.py --sandbox "$SANDBOX" register --request "$REGISTER_REQUEST" > "$REGISTER_RESPONSE"
python -B tools/runtime_package_cli.py --sandbox "$SANDBOX" set-state --request "$ENABLE_REQUEST"
python -B tools/runtime_package_cli.py --sandbox "$SANDBOX" create --request "$CREATE_REQUEST" > "$CREATE_RESPONSE"
python -B tools/runtime_package_cli.py --sandbox "$SANDBOX" run-once --case-id "$CASE_ID"
python -B tools/runtime_package_cli.py --sandbox "$SANDBOX" snapshot --case-id "$CASE_ID"
python -B tools/runtime_package_cli.py --sandbox "$SANDBOX" events --case-id "$CASE_ID"
```

变量必须从真实 JSON 回执读取，不用示例 ID 代替：

- `REGISTER_REQUEST` = 安装回执 `result.register_request`，保持其既有五键 payload。
- 每个新请求外层只含 `request_id`、`idempotency_key`、`payload`。
- enable payload 只含 `registration_id`、`expected_revision`、`target_state`。前两者取 register 的真实结果，`target_state` 是字符串 `ENABLED`，不是 `state`。
- create payload 只含 register 的 `registration_id` 和安装回执的 `input_ref`、`object_refs`。
- `CASE_ID` = create 回执 `result.case_id`。
- 同意图重放保留原 idempotency_key/payload，只更换 request_id；不要把 package_id 当业务去重键。

没有显式 ENABLED 不能创建。安装激活和核心 register 是分开的动作/回执，不是一笔跨层事务。安装重放返回原安装身份，不自动注册或创建 Case。

## 身份、错误与期限

宿主 `host/installation.json` 是私有安装记录，不是新增共享 Schema。注册 binding 和 Case binding 固化安装记录摘要；包/声明/实现/文件集合、Adapter、解释器或依赖身份不符时拒绝 VERSION_CONFLICT。自报新 hash 不重新授信，旧 Case 不跟随新默认绑定。

实际调用证明关联 Case、NodeRun、attempt、ProviderRef、安装/源码/输入/输出摘要及真实 Python PID。证明用于审计，不是状态机；Case、evidence 和 events 的真相仍在原 SQLite 台账。Windows Python launcher PID 可能不同于回执中的 Python PID，须分别记录，不能假设两者相等。

| 层/失败 | 行为 |
|---|---|
| 独立 WF1 checker 缺可信上下文 | INCOMPLETE/4，保留来源状态 |
| 核心缺 P2/Reader 不可得 | 保留 DEPENDENCY_UNAVAILABLE/AUTHORITY_UNAVAILABLE 等原码 |
| 不支持多节点、等待、AI/HUMAN、读回/动作、资源、重试等 | 原门禁拒绝，不裁剪投影、不另建执行器 |
| 作者 KeyError/TypeError、非法返回、输入修改 | 局部 CONTRACT_INVALID；不暴露异常正文 |
| 作者内部异常 | INTERNAL_ERROR；不冒充数据库损坏 |
| 真正 SQLite 损坏/缺失 | STORAGE_INVALID/4；不自动建库或修复 |
| 临时依赖/占用 | CLI 退出码 3；不表示自动重试已实现 |
| 同键异意图 | IDEMPOTENCY_CONFLICT，无新台账或调用 |
| 已撤权的已知/未知键 | 都拒绝，不先泄露幂等历史 |

本先导只针对已审纯代码，不是恶意 Python 沙箱。受控同步执行继承 M1 接纳期限，不提供强制抢占。一个宿主会话只支持一个活动 attempt；不扩展多 Worker ABI。

领取后进程崩溃：状态可查询，但新进程不能接管或自动重跑；期限后 LEASE_LOST，不自动 FAILED/等待/恢复。终态重复 run-once 被拒绝；create 幂等重放仍返回历史 QUEUED，snapshot 才显示当前 SUCCEEDED。

## 验收与证据

在各自独立进程运行，保留原始 stdout/stderr、退出码和 JUnit；报告放在待清理沙箱之外：

```bash
python -B -m pytest tests/runtime_package -q -p no:cacheprovider
python -B -m pytest tests/runtime_m1 -q -p no:cacheprovider
python -B tools/verify_runtime_package.py --sandbox "$ACCEPTANCE_SANDBOX" --report "$ACCEPTANCE_REPORT"
python -B tools/verify_runtime_m1.py --sandbox "$M1_SANDBOX" --scenario all --report "$M1_REPORT"
python -B -m pytest spikes/001-input-contract -q -p no:cacheprovider
python -B -m pytest spikes/002-authority-contract -q -p no:cacheprovider
python -B -m pytest tests/test_collaboration_docs.py -q -p no:cacheprovider
python -B tools/audit_tree.py
```

新验收器默认执行 S01–S10，支持 `--scenario S01` 至 `S10` 作专项复验；只运行部分场景的报告不能称完整通过。S10 真实运行 M1 单测、两套契约和协作文档回归，因此全量是有限长测试，应使用具备退出通知的后台**测试进程**，不要启动长期 Worker 或后台 Agent。

`cli_count` 统计包/WF1 CLI 及安装内 checker；`observer_count` 是独立只读观察；`probe_count` 是明确标注层次的 ABI/模型探针。原始 `commands` 和 `embedded_checker_commands` 可重新计数。探针替代源码仅验证局部 ABI，绝不声称它们通过固定计划安装或作为真实 Case 执行。pytest 数量和这些进程数分列；M1 独立 CLI 报告另列，不混合计数。

单节点正常 Case 事件为：CASE_CREATED/NODE_READY 的 revision=1，NODE_LEASED/NODE_STARTED 的 revision=2，NODE_SUCCEEDED/CASE_SUCCEEDED 的 revision=3。注册/启用事件不混入这六条 Case 事件。

## 清理、失败保留与回滚

```bash
python -B tools/runtime_package_cli.py --sandbox "$SANDBOX" host-cleanup --manifest "$MANIFEST"
```

先保存审计，确认本轮子进程退出，再使用安装回执中的精确 manifest。返回清理文件摘要，另起进程验证目标缺失。链接、hardlink、活动进程、错误 manifest 或不认识的文件会阻止清理。不得直接删库掩盖失败，不跟随链接删除邻居目录。

安装使用固定 `.pending` 同级目录后原子改名；快照或激活前中断没有可用正式安装，重试遇到 pending 保持 IN_PROGRESS。激活后丢失响应可验证并重放原安装回执。失败 pending 只能在核对本轮所有权、进程退出、逐文件清单并留证后清理；不得将其改名当作安装成功。

回滚仅停止使用并清理自己这一安装，不改共享 Schema/DDL、原包、M2 材料、Git 历史或其他工作树。实现交付不等于审阅通过；交付后等待独立审查与另行批准。
