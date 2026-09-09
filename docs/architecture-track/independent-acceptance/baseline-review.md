# 既有输入及权威契约基线独立复核

署名：Laiqh
执行角色：主控分配的辅助审阅会话A。关联 [Issue #19](https://github.com/lqhoyh121-afk/xiehe-runtime-foundation-design/issues/19)，输入任务 [#3](https://github.com/lqhoyh121-afk/xiehe-runtime-foundation-design/issues/3)，父任务 [#4](https://github.com/lqhoyh121-afk/xiehe-runtime-foundation-design/issues/4)。

## 一句话结论

**原有测试可独立复现，但测试绿灯不等于契约完整：发现三类错误接受问题及两项结构化错误出口缺口。保留既有成果，补修复卡；不建议据此通过正式准入、权威迁移或架构冻结。** 本报告可作为主控验收材料，不是合并、发布或生产批准。

## 基线、范围与证据等级

- 被审基线：`01ad6b5de76dcb51ccf156ff3da0e3ad0b4420cb`；任务分支：`task/19-baseline-review`。开工时 HEAD 等于基线，工作区无改动；`git diff BASE...HEAD` 为空是既有基线复核的预期，不是无内容可审。
- 已读取 AGENTS、PROJECT_CONTROL、协作开工/保护规则、assignment、本地断点、Issue #19及评论、#3/#4及最近PR #18。工作区工具返回 `verified=true`、`changed=[]`、退出码0；认领评论已独立回读。真实目录及原始输出只保存在本机，不进入本报告。
- 范围：两个spike的规范、源码与正式测试；P1/P2验收清单；共享Schema；runtime-core接口及对齐/回应文档。AC-3验收依据为 `docs/architecture-track/SPEC.md:15-16,27-39`、`design.md:19` 及 `spikes/002-authority-contract/test_migration.py`，不虚构另一个AC-3清单文件。
- 证据等级：L1合成契约测试；补充真实文件、SQLite及子进程CLI的局部L2证据。**L2不代表已经执行实例迁移**。L3人工体验、L4真实系统、生产签发/消费/停旧启新均未验证。
- 不修改源码、Schema、正式测试、CI、总控或其他会话文件。探针、虚拟环境、XML和原日志均留在本worktree的忽略目录。Git交付只有本报告。
- 内部使用两个只读分析上下文分别检查Spec轴与Standards轴，无第二个报告写入者。Spec轴指出R1/R2；Standards轴指出亚微秒截断及R4/R5；本会话补充非法时区反例并亲自完成所有文件/CLI复现，不仅采信子上下文总结。合并为5项问题（R3包含两个时间反例）；独立意见不是平台账号批准。

## 独立实跑结果

工作区根目录分别运行，未把两个含同名模块的spike合并收集。XML总数经程序读取，非照抄历史43/150。

| 验证 | 实跑命令/入口 | 结果 | 证明范围 |
|---|---|---|---|
| 开工工作区 | `python tools/verify_workspace.py --assignment .local/assignment.json` | 退出0，verified=true | 目录、分支、基线和允许文件匹配 |
| 输入正式测试 | `python -B -m pytest -q -p no:cacheprovider --junitxml=.local/review-evidence/input.xml spikes/001-input-contract` | 43通过，失败/错误/跳过均0，退出0 | 本机pytest 9.1.1的L1基线 |
| 权威正式测试 | `python -B -m pytest -q -p no:cacheprovider --junitxml=.local/review-evidence/authority.xml spikes/002-authority-contract` | 150通过，失败/错误/跳过均0，退出0 | 同环境P1/P2/AC-3基线 |
| 锁定依赖输入复跑 | `.local/review-venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp=.local/review-evidence/pytest-input-temp --junitxml=.local/review-evidence/input-pinned.xml spikes/001-input-contract` | 43通过，失败/错误/跳过均0，退出0 | 隔离环境pytest 8.4.2，与requirements-dev一致 |
| 锁定依赖权威复跑 | `.local/review-venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp=.local/review-evidence/pytest-authority-temp --junitxml=.local/review-evidence/authority-pinned.xml spikes/002-authority-contract` | 150通过，失败/错误/跳过均0，退出0 | 相同解释器、重新安装开发依赖；非干净电脑 |
| 双来源CLI | `python -B spikes/001-input-contract/demo.py --output-dir .local/review-evidence/input-demo` | 退出0；内部Excel/SQLite CLI均退出0 | 事实/预期判定/模型相同，来源快照不同；业务处理器和源文件未改变，六项检查均true |
| 中文空格迁址 | `python -B spikes/001-input-contract/verify_relocation.py` | 退出0，六项检查均true | 迁移源码位置、同一已装解释器；不是跨机部署 |
| 迁移演示CLI | `python -B spikes/002-authority-contract/cli.py --demo` | 退出0；一个正常本地通过、五个预期拒绝 | 所有场景production_authorized=false、migration_executed=false |
| 无真实Adapter | `python -B spikes/002-authority-contract/cli.py` | 退出2，TRUSTED_ADAPTER_REQUIRED | 正式路径失败关闭，没有真实迁移 |
| 额外P1探针 | `.local/review-venv/Scripts/python.exe -B .local/review-evidence/probes.py` | 退出0，复现下述R1/R2；正常对照通过，节点环对照NODE_CYCLE | 退出0表示复现断言成立，不是两个错误输入正确 |
| 额外时间CLI探针 | `.local/review-venv/Scripts/python.exe -B .local/review-evidence/probe_time.py` | 退出0，复现下述R3 | 真SQLite→输入CLI→快照回读，不只调用私有辅助函数 |
| Standards补充CLI探针 | `.local/review-venv/Scripts/python.exe -B .local/review-evidence/standards_probes.py` | 探针退出0；亚微秒未来输入CLI退出0，布尔属性Schema/超长整数CLI均退出1且无JSON stdout | 复现R3补充、R4/R5；错误路径均未生成业务结果 |
| 协作入口回归 | `python -B -m pytest -q -p no:cacheprovider tests/test_collaboration_docs.py` | 8通过，退出0 | 不混入两个spike测试数量 |

解释器为Python 3.11.15。两套环境的openpyxl均为3.1.5、jsonschema均为4.26.0、referencing均为0.37.0。隔离环境按 `requirements-dev.txt` 安装，仅写忽略目录，未修改宿主依赖。原有两组测试在第二套环境重跑不算新增测试；额外探针也不计入43/150。历史红→绿日志不在清理后的跟踪树内，本次没有改实现，不能宣称重新验证了原作者的修复过程。

## 会出事的：正式采用前必须处理的语义缺口

严重性针对未来把候选用作准入门禁；**当前返回值始终只是本地DRAFT，不构成已发生生产越权**。以下探针都只修改合成测试副本。R1/R2重新发布合成投影是为了通过已有摘要绑定，测试下一层语义；并非攻击者能改真实权威发布库。

### R1｜P1：要求回读完成，却没有可调用的验收定义/回读Provider

- 位置：`spikes/002-authority-contract/validator.py:191-223`，尤其212-214；`docs/architecture-track/contracts/authority-contract.schema.json:303-321,367-395`。
- 实测：原fixture首节点仅将 `completion` 改成 `READBACK_VERIFIED`，保留 `verification_spec_ref=None`、`readback_provider_ref=None`；重新发布后返回 `VALIDATED_LOCAL_ONLY`。
- 原因：Provider检查遇到None直接跳过，Schema允许这两个字段为空，却没有按完成条件施加必填约束。现有 `test_p1_negative.py:152-186` 检查错角色/未绑定，不检查这种缺失组合。
- 影响：类似“写着必须复验，但验收人和验收标准都没填”，这样的运行投影仍被标记本地有效。后续核心可能无法完成节点；若上层错误降级完成条件，会破坏独立回读门禁。未实跑核心，不声称已经提前完成了业务。
- 依据：`docs/architecture-track/p1-p2-acceptance-checklist.md:11-14`，`docs/runtime-core/interfaces.md:151-170`。
- 建议：在投影语义层明确completion与验收引用/Provider的组合规则，按完成条件拦缺项，并加入公开接口反例。是否要求ActionAdapter、HUMAN等待引用及其精确组合由架构方定契约，不在修复中猜测。

### R2｜P1：引用能找到、摘要正确，但放错种类仍能通过

- 位置：`spikes/002-authority-contract/validator.py:156-163,226-250`；Schema `Node.rule_ref` 只指向通用DefinitionRef（`authority-contract.schema.json:287-288`）。
- 实测：首节点 `rule_ref` 替换为fixture现有 `model` 引用，依赖仍闭合；重新发布后返回 `VALIDATED_LOCAL_ONLY`。
- 原因：Provider槽位检查kind与role，非Provider引用槽位没有相应的语义类型约束。校验“这张证是真的”，没有校验“是不是这里需要的那种证”。
- 影响：规则模块可能收到模型定义，直到运行时才失败；不能把“精确引用校验已实现”扩大成“槽位语义均已核验”。现有 `test_p1_negative.py:20-62,164-186` 覆盖摘要、闭包和Provider种类，不覆盖model占rule槽位。
- 依据：`docs/architecture-track/SPEC.md:9-12`、验收清单 `p1-p2-acceptance-checklist.md:11-14`；核心规则职责见 `docs/runtime-core/interfaces.md:119-127`。
- 建议：由单一契约定义各槽位允许kind，至少rule_ref拒绝model；盘点business/definition/input/output/wait/verification等非Provider槽位，兼容映射须显式声明，不凭名称回退。

R1/R2最小复现：进入 `spikes/002-authority-contract`，下列只读检查代码的变更只作用于内存合成fixture，不改源码或正式文件。分别将 `case` 设为 `readback`、`rule-kind` 运行；实际两者都打印本地通过。

```python
from copy import deepcopy
from fixtures import fixture, republish_projection
from validator import validate_projection
f = fixture()
case = 'readback'  # 第二次运行改为 'rule-kind'
if case == 'readback':
    f.projection['nodes'][0]['completion'] = 'READBACK_VERIFIED'
else:
    f.projection['nodes'][0]['rule_ref'] = deepcopy(f.model)
republish_projection(f)
print(validate_projection(f.projection, f.authority, f.context))
# 实测：verdict=VALIDATED_LOCAL_ONLY, production_authorized=False
```

### R3｜输入契约：非法时区分钟被自动进位，真实CLI输出业务结果

- 位置：`spikes/001-input-contract/input_contract.py:48-60,210-216`；已有回归 `test_review_regressions.py:43-46` 拒绝紧凑格式和秒级偏移，但未覆盖偏移分钟超界。
- 实测原值：`2030-01-01T12:59:00+00:60`。分钟60不是有效RFC3339偏移；显式校验却接受并规范化成 `2030-01-01T11:59:00+00:00`。
- 实际CLI链路：复制本次demo自建SQLite到忽略目录，仅将 `observations.sampled` 改为上述非法字符串；沿用原model/objects/business/mapping，`--as-of 2030-01-01T12:00:00+00:00`，输出目录使用新目录。CLI退出0、`status=validated_local_demo`，独立读取生成快照确认了上述自动进位值。
- 辅助函数最小复现：在输入spike目录运行 `python -c "from input_contract import timestamp; print(timestamp('2030-01-01T12:59:00+00:60'))"`，应拒绝却打印有效UTC时间。完整CLI复现按上条修改自建SQLite后，使用README中要求的全部显式参数即可；不需要真实数据或凭据。
- 原因：正则只限制两位数字，`datetime.fromisoformat` 会规范化超界偏移分钟。可选jsonschema date-time检查器缺失时，显式代码没补齐这个边界；本次锁定依赖环境已实际复现，不推断所有安装环境都会放过。
- 依据：`spikes/001-input-contract/README.md:46,54-56` 声明显式时间校验不依赖可选包；不能把不合法源值先修成合法事实再计算时效。
- 建议：显式校验偏移小时/分钟范围（分钟00–59），保留合法时区转换；增加 `+00:60`、`+00:99` 等反例，分别测试辅助函数和无可选format checker环境下的真实CLI。拒绝时不得生成业务结果。
- 同一时间边界的补充实测：自建SQLite改为 `2030-01-01T12:00:00.0000001Z`，时钟仍为整12点；CLI退出0，快照变成 `2030-01-01T12:00:00+00:00`。`timestamp`允许任意小数精度，datetime截到微秒，导致正的未来尾数被丢失；违反 `SPEC.md:10` 的未来时间拒绝义务。影响量级很小，不夸大为大范围时效绕过，但须明确支持精度并拒绝超出精度或无损比较。修复卡同时补这一反例，不只增加偏移正则。

## 半成品：已有局部证明，但正式能力尚未实现

### R4｜输入CLI：合法布尔属性Schema触发裸异常

- 位置：`spikes/001-input-contract/input_contract.py:177-195,231-233`、`cli.py:43-48`；现有 `test_cli.py:46-54` 只覆盖顶层Schema形状错误。
- 最小复现：复制本次demo自建model，将 `record_schema.properties.reading` 改为JSON `true`，按既有规范化重算并更新business中的model摘要，其他夹具及CLI参数不变。JSON Schema允许布尔子Schema，前面的schema自检会通过；随后 `descriptor.get('type')` 对bool报错。
- 本会话真实CLI结果：退出1、stdout为空、stderr含AttributeError，未生成业务结果。没有越权放行，但上层得不到承诺的结构化拒绝码。
- 建议：明确固定观测模型支持的Schema子集；不支持布尔属性时提前返回MODEL_INVALID，或安全处理布尔descriptor。不能只在CLI吞掉所有异常。补真实CLI回归，保留输入契约SPEC:21-22的固定模型边界，不扩成任意模型实现。

### R5｜权威CLI：小文件内的超长整数绕过结构化错误出口

- 位置：`spikes/002-authority-contract/validator.py:80-96`、`cli.py:45-58`。`load_json`捕获JSONDecodeError，但未捕获Python整数转换触发的普通ValueError。
- 最小复现：在忽略目录创建内容为 `'{"generation":' + '1' * 4301 + '}'` 的JSON文件，然后运行 `python -B spikes/002-authority-contract/cli.py --demo --request <该自建文件>`。本机默认整数位数限制4300；文件远低于2,000,000字节上限，先在JSON解析阶段报错，尚未到Schema或canonicalization检查。
- 本会话真实CLI结果：退出1、stdout为空、stderr含ValueError；没有业务结果或授权。违反 `docs/architecture-track/design.md:7,10` 的固定安全码/结构化结果约定，不能称为成功失败关闭接口。
- 建议：在JSON解析边界把整数转换失败转成固定ContractError，保留现有重复键/非有限数字错误码；增加真实子进程用例。参照 `test_cli.py:48-62` 的坏载荷矩阵，不改解释器全局整数限制来掩盖问题。

| 审查项 | 代码/测试证据 | 当前状态与不能扩大的结论 |
|---|---|---|
| 输入切换与来源摘要 | `input_contract.py:77-110,119-145,157-159,229-240`；`test_contract.py:75`；`test_review_regressions.py:13-26,49-54` | **已验证（局部）**：Excel=file_bytes，SQLite=selected_rows，语义摘要与来源摘要分开；不是全数据库完整性、线上一致读或任意模型支持 |
| 输入对象/时间/不可覆写 | `input_contract.py:165-240`；`snapshot_store.py:10-44`；`test_boundaries.py:24-137` | **已验证（局部）**：身份/类型/过期与快照完整性、重复写检查；时间仍有R3。摘要及本地类型不是认证，可信配置限制见README:48 |
| 定义引用与依赖闭包 | `validator.py:156-163,226-248`；`test_p1_negative.py:20-115` | **已验证（局部）**：声明依赖逐一resolve并纳入传递依赖；缺依赖/错摘要/跨范围拒绝。不执行依赖内容语义；槽位类型仍有R2 |
| 节点图 | `validator.py:170-188`；`test_p1_negative.py:118-149` | **已验证（局部）**：重复id、缺父节点、环和终止叶节点集合；额外环对照也拒绝。未运行调度器/双Worker，不把元数据依赖闭包等同调度执行证明 |
| Provider绑定 | `validator.py:191-223`；`test_p1_negative.py:65-69,152-186` | **半成品**：已检查发布描述符、角色、执行类别及精确依赖绑定；缺失的完成条件组合见R1；没有装载或核验真实Provider代码 |
| 签发权威/准入 | `authority_checks.py:41-77`；`test_p2.py:31-53,108-148`；`validator.py:29-47` | **本地核验已验证，正式签发未实现**：宿主注入policy及Reader；请求不能自带approved/trust。没有真实认证传输、issuer服务或密码学验签；类型检查不是安全隔离 |
| 撤销、过期、同步缺口 | `validator.py:142-153`；`authority_checks.py:121-159`；`test_p2.py:151-258` | **本地判据已验证**：有效期、生效时间、水位、范围、代际、完整性和重复调用重验；真实同步/水位持久化/乱序恢复/撤销与放行竞争未实现 |
| 消费权及复制边界 | `authority_checks.py:80-111,163-179`；`test_p2.py:56-105` | **本地绑定已验证**：实例/部署/命名空间/消费范围/代际/当前Grant；没有消费操作、跨机唯一权威或原子切换。worker_session及稳定动作幂等字段表仍属草案（核心interfaces:16-31） |
| 迁移、检查点、停止证明 | `migration_checks.py:79-163`；`test_migration.py:9-88` | **半成品/只读候选**：目标AC-2权利、源Grant撤销及有效事件、代际提高、检查点/停止/能力绑定；不执行迁移，不证明旧进程真的停止或fence有效 |
| UNKNOWN | `migration_checks.py:98-99,146-149`；`test_migration.py:18-48`；核心 `interfaces.md:164-190` | **局部已验证，核心草案**：control/stop的UNKNOWN拒绝；没有真实ActionIntent未知写结果的持久化/对账/隔离实现，不能用两个枚举反例代替UNKNOWN恢复验收 |
| AC-3 CLI | `cli.py:14-60`；`test_cli.py:17-71` | **已验证（本地入口）**：6个演示场景、文件重复/输入不变、无Adapter拒绝。迁移批准引用虽然在共享AuthorityRef枚举出现，不等于存在批准签发和迁移工具 |

AC-3特别边界：`migration_checks.py:3-7,63-76,154-155` 明说checkpoint/stop的issuer相等只做绑定，不校验正式控制记录签发权限；证据仅检查引用的范围/时间，未取回内容验证digest。`_CallReads`（38-55）只在本次调用内缓存同一引用，防止第二次读到另一份未验证视图，**不是跨记录原子快照，也不是跨机事务或防止检查后变化的fence**。这些是正式化前置缺口，不冒充隐藏的生产攻击路径。

## 不影响使用：文档与维护性判断

- 清理后的跟踪树不含原evidence目录；输入README:11、52和架构旧对齐文件仍保留当时环境、证据路径及阶段措辞。总控/Issue已明确迁库后只接续候选；这些历史表述不能当作当前完成状态。本次重新跑测试可替代本地基线证明，不能补出丢失的历史红绿日志。
- `docs/architecture-track/SPEC.md:39` 的“任务系统未配置/Git不存在”是旧阶段文字；当前以AGENTS/PROJECT_CONTROL与GitHub Issue为准。建议单独文档卡修订历史标记，不在本卡越界修改。
- Standards判断：本次未提出仅凭个人风格的阻断项。测试夹具与验证器独立构造摘要是有意降低同源正确答案风险（`fixtures.py:1-5,19-25`），不应因“看起来重复”就要求合并。源码气味不替代业务不变量与实跑反例。

## 后续修复卡建议与验收阻断

| 建议卡 | 建议范围 | 最小验收 |
|---|---|---|
| FIX-P1-SEMANTICS（对应R1/R2） | authority Schema/validator及正式P1反例，另行派工 | 明确槽位kind和completion组合；R1/R2先红后绿；保留正常/图/Provider/闭包测试，两个spike分目录回归 |
| FIX-INPUT-TIME（对应R3） | 输入timestamp及CLI回归，另行派工 | 非法偏移不自动进位；无可选format checker时也拒绝；失败无结果输出，合法时区与过期边界仍正确 |
| FIX-ERROR-BOUNDARY（对应R4/R5） | 输入Schema子集和权威JSON解析边界，另行派工 | 布尔属性、超长整数产生结构化安全错误；不吐裸traceback、不生成业务结果、不放宽准入 |
| AUTHORITY-FORMALIZATION | 承接#4，由主控拆卡 | 明确issuer/认证/受信Reader、权威控制记录签发范围、撤销同步与持久水位、消费唯一权威；给获准真实验证方案 |
| MIGRATION-ACCEPTANCE | 承接后续迁移阶段，非本卡启动实现 | 一致检查点、数据和去重证据内容/保留、源端停止或fence真证明、目标探测、批准/切换原子边界；L2离线CLI不得充当真迁移完成 |
| CONTRACT-ALIGNMENT/DOC | 对应核心§6及历史说明 | 按精确版本/摘要记录逐项接受或调整；明确幂等字段表、UNKNOWN/错误出口、Provider契约；旧说明标历史，不维护第二份任务进度 |

**阻断分层**：R1/R2/R3阻断把当前候选当作完整正式准入基线；生产权威、迁移和共同冻结还受设计F1–F8缺口约束（`docs/architecture-track/design.md:24-32`）。这些不阻断完成Issue #19的只读复核报告，也不自动批准父任务完成。修复范围须主控新派，不由本会话自行修复。

## 交付与未验证项

- 报告之外无跟踪文件变更；提交前已再次跑workspace校验，verified=true、退出0，changed仅本报告。逐文件stage后扫描69个跟踪文件，findings=[]、退出0；`git diff --cached --check` 通过。原始证据不上传GitHub，仅提交本页脱敏摘要与可复现方法。
- 未验证：生产身份/签发/撤销同步、跨机唯一消费、真实停止/fencing、迁移/恢复/去重台账、Provider执行、运行核心、真实外部读写、人工操作体验、干净机器安装及跨语言规范化。
- 独立Agent意见属于不同执行上下文复核，不是GitHub独立账号approval。Issue/PR只提供审阅结论；唯一批准人仍为总负责人。
- 本次不合并、不发布、不关闭#3/#4父阶段，也不宣布架构冻结。
