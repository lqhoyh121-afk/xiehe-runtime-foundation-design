# P1 槽位与完成条件候选矩阵

状态：**DRAFT**。署名：Laiqh。

本页说明 FIX-P1-SEMANTICS 对 R1/R2 的限定修复，不是共同冻结、生产授权或运行核心实现。实施依据为主控已确认的本地任务卡；可分发依据与源文件如下。

## 依据与唯一机器契约

- [P1/P2 验收清单](p1-p2-acceptance-checklist.md)：P1 精确引用、规则/验收 Provider 映射与可执行反例义务。
- [隔离设计](design.md)：不变量中的精确 kind/namespace/version/digest、发布投影绑定及依赖闭包；不会实际执行业务规则。
- [现有合成夹具](../../spikes/002-authority-contract/fixtures.py)：`publish`、`republish_projection` 及正常 `fixture`，运行投影发布为 runtime，输入/输出用 model，业务用 business，规则用 rule。
- [唯一共享 Schema](contracts/authority-contract.schema.json)：非 Provider 槽位 kind 与 completion 条件的唯一机器来源。
- [隔离 validator](../../spikes/002-authority-contract/validator.py)：公开 `validate_projection` 消费共享 Schema；保留可信记录、摘要/依赖闭包与已有 Provider 角色绑定检查，不另写一份槽位矩阵。

基线报告 R1 指 READBACK_VERIFIED 缺验收定义/回读 Provider 仍通过；R2 指 model 放进 rule_ref，真实记录与摘要均正确仍通过。原报告保留在主控指定的只读复核目录，不将本机路径或原日志放入本页。

## 非 Provider 槽位 → kind

| 位置 | 非空引用允许 kind | null / 缺字段 |
|---|---|---|
| Projection.business_ref | business | 均拒绝；沿用必填 |
| Projection.definition_ref | runtime | 均拒绝；沿用发布投影夹具 |
| Node.input_contract_ref | model | 均拒绝；沿用必填 |
| Node.output_contract_ref | model | 均拒绝；沿用必填 |
| Node.rule_ref | rule | 均拒绝；沿用必填 |
| Node.wait_spec_ref | wait | 保留 nullable，但字段仍必填 |
| Node.verification_spec_ref | verification | 仅非 READBACK_VERIFIED 保留 nullable；字段仍必填 |
| Projection.dependencies | 通用 DefinitionRef 枚举 | 保持现有数组约束，允许异构定义依赖，不收窄为单一 kind |

通用 DefinitionRef 当前枚举为 business/runtime/model/rule/wait/verification/provider。槽位错误种类必须拒绝，即使记录存在、摘要正确且依赖闭合。测试枚举取通用集合以覆盖所有反例；期望槽位映射独立来自本任务矩阵，不从实现推导期望值。

## completion → 必要配置

| completion | 本次约束 | 本次不推导的条件 |
|---|---|---|
| READBACK_VERIFIED | verification_spec_ref、readback_provider_ref 同时非 null；验收定义 kind=verification；回读 Provider 已绑定且 role=ReadbackProvider | 不强加 ActionAdapter、wait_spec 或执行类别 |
| OUTPUT_VALIDATED | 保持原必填/nullable 和 Provider 规则 | 不额外强制动作适配器或回读 |
| HUMAN_CONFIRMED | 保留现有格式与 Provider 规则 | 不强制 execution_kind=HUMAN、等待定义或 ActionAdapter；不把配置通过解释为真人批准 |

READBACK_VERIFIED 只缺验收定义、只缺回读 Provider、两者全缺均拒绝。Schema 用 completion 条件收窄两个字段的非空性，Provider 的 kind/绑定/role 仍交给原 validator，避免覆盖已有专用错误码。

## Provider 与错误出口

Provider 槽位的 kind=provider、role、NodeExecutor execution_kind 对应关系保持 [validate_provider_bindings](../../spikes/002-authority-contract/validator.py) 中原有校验，不复制角色映射。

- 新增槽位与完成条件的 Schema 拒绝沿用 `ContractError('SCHEMA_INVALID')`。
- `PROVIDER_KIND_MISMATCH`、`PROVIDER_NOT_BOUND`、`PROVIDER_ROLE_MISMATCH`、`PROVIDER_EXECUTION_KIND_MISMATCH` 继续原路径；依赖/摘要错误出口不改。
- `ProviderDescriptor.ref` 的直接 shape 当前仍为通用 DefinitionRef。此处未加独立 provider-kind 限制；真实投影路径仍有原 Provider kind 检查。直接描述符约束属于记录项，不扩大本次修复。

## 验证接缝与范围

[新增测试](../../spikes/002-authority-contract/test_p1_semantics.py) 使用既有合成发布方法，不修改共享 fixture 或原有测试：

- L1：直接调用公开 `validate_projection`，覆盖 R1 缺失组合、完整回读、错 role/未绑定、全部非 Provider 槽位的错误 kind、null/缺字段、合法 wait/verification、异构依赖和原正常完成条件。
- 错 kind 的合成引用必须可解析、摘要正确、依赖闭合，并重新发布投影；definition_ref 则发布一条错误 kind 的真实投影记录，不靠 lookup 缺失制造假反例。
- L2：新解释器进程调用同一公开接口；合成探针 stdout 仅输出本地结果或固定码的 REJECTED JSON，拒绝退出2，不输出投影载荷、无裸异常。重复调用前后核对投影和 authority 记录不变。
- 现有 [cli.py](../../spikes/002-authority-contract/cli.py) **仅支持迁移请求**；`python -B spikes/002-authority-contract/cli.py --demo` 仅作兼容回归。没有新增或宣称存在 `--projection`，探针也不是生产 CLI 功能。
- 两个 spike 分目录全量回归，另跑协作文档测试。本页本地链接单独检查，不用已有入口测试冒充覆盖本页。

## 本次合成验证结果

以下是本地候选验证，不是生产验收。新增测试共 160 项：L1 公开接口 80 项，L2 新进程 80 项。

| 阶段 | 实际结果 |
|---|---|
| 原始基线 | 权威 180、输入 43、协作 8 通过 |
| R1 红测 | 6 失败、26 通过；三种 null 缺失组合分别在 L1/L2 错误返回本地通过 |
| R1 修复后 | 32 通过 |
| R2 红测 | 84 失败、44 通过；七个槽位各六种错误 kind，在 L1/L2 均错误返回本地通过 |
| R2 修复后 | 128 通过 |
| 全量回归 | 权威 340、输入 43、协作 8 通过 |
| 真实迁移 CLI 兼容 | `--demo` 六场景输出符合预期，未执行迁移、无生产授权 |

可在本任务根目录分别运行：

```bash
python -B -m pytest spikes/002-authority-contract/test_p1_semantics.py -q -p no:cacheprovider -k 'readback or existing_completion'
python -B -m pytest spikes/002-authority-contract/test_p1_semantics.py -q -p no:cacheprovider -k 'slot or heterogeneous'
python -B -m pytest spikes/002-authority-contract -q -p no:cacheprovider
python -B -m pytest spikes/001-input-contract -q -p no:cacheprovider
python -B -m pytest tests/test_collaboration_docs.py -q -p no:cacheprovider
python -B spikes/002-authority-contract/cli.py --demo
```

当前修复版上述测试应全绿；红测来自修复前实跑，不是要求在最终版再次失败。原日志、JUnit、子进程 stdout/stderr/退出码和首次本地测试运行器临时目录设置失败记录仅保留忽略目录，不进入 Git。

## 尚未决策／未验证

READBACK_VERIFIED 是否一定有动作适配器、HUMAN 是否必须等待、人工身份认证/授权、完成事件、输出与规则语义执行、真实 Provider 行为均未在本补丁决定或验证。

配置通过只说明 `VALIDATED_LOCAL_ONLY`，`production_authorized=false`。不证明实际回读、真人批准、真实迁移、分布式权威或完整底座；共同冻结和生产授权仍由负责人另行批准。R3/R4 不在本分支，已继承的 R5 不重复修复。
