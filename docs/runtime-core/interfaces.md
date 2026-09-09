# 通用调度核心接口草案 v0.2

署名：Laiqh  
状态：DRAFT / 全部待实现，先对齐再深化。  
所属项目：底层架构设计。仅定义核心与外部模块之间的运行接缝，不是新本体规范、业务包格式、安装协议或已存在的HTTP/MCP接口。

修订依据：`../architecture-track/runtime-core-contract-review.md`。S1–S3、P3/P4已在本草案补充；P1/P2仍待架构侧提供权威定义。v0.2仅表示修订稿，不表示双方冻结或任何能力已实现。审阅回复见 `review-response.md`。

另已读取架构侧 `../architecture-track/business-flow-ports-and-data-contracts.md`。沿用其SourceAdapter → DataProvider → 节点快照及受控输出方向，仅补调用边界；数据引用的正式字段/Provider映射仍待P1冻结。

## 0. 阅读约定与公共上下文

这里的方法名称、字段和枚举是讨论用逻辑接口。Python/HTTP/MCP绑定、端口、认证方案未定，也未安装服务。字段如与整体架构已有名称冲突，映射到既有权威字段，不平行造协议。

- `business_ref`、`definition_ref`、`rule_ref`、`object_refs`、`evidence_refs`、`adapter_ref` 均引用整体架构已有或待定的权威格式。核心只核验可解析性、版本/摘要、权限及绑定，不另定义对象类型和规则语义。
- 每个写命令携带 `request_id`、`idempotency_key`；运行上下文含 `instance_id`、`case_id`、`node_run_id`、`trace_id`，适用时绑定 `attempt_id`、`lease_token`。`instance_id`是持久逻辑实例标识，重启不变；`worker_session_id`每次Worker进程会话重新生成，不作为业务幂等身份。迁移沿用的幂等命名空间与跨部署消费权由架构侧P2契约授权，复制数据库不获得接单权。
- `auth_context` 必须由可信接入层生成，不能接受模型自报身份或权限。其租户/项目/资源范围命名遵循整体权限契约。
- `expected_revision` 用于调用方发起的 Case 变更；Worker 提交以节点 attempt/lease 和绑定输入快照校验。独立节点并行完成不因其他节点合法完成而一律冲突；如果输入所依赖事实版本已变，重新校验或拒绝。
- 幂等键作用域为获准的持久命名空间、操作及业务对象；服务端将其绑定版本化规范化输入摘要。命名空间默认对应持久实例，不因Worker重启变化。迁移必须保留被批准的原命名空间，独立新部署不得私自继承消费权。规范化排除request_id及短期认证/续租载荷，保留业务参数、目标和版本。节点结果/对账提交等attempt级操作须绑定attempt身份；request_action的逻辑意图摘要不包含可变执行attempt，执行尝试另行绑定，避免重试变成新动作。具体字段表由整体协议冻结。
- 统一错误外形建议为 `code / safe_message / retry_class / correlation_id`，仅含脱敏上下文。`retry_class` 为 `never / after_backoff / after_input / after_reconciliation`。不可仅凭 HTTP 状态或异常文本自动重试外部写入。
- 常见错误：`UNAUTHORIZED`、`VERSION_CONFLICT`、`CONTRACT_INVALID`、`DEPENDENCY_UNAVAILABLE`、`LEASE_LOST`、`REVISION_CONFLICT`、`INPUT_STALE`。未实现的错误码不能被当作现成 SDK。

### 0.1 幂等重放顺序（S1）

1. 先验证当前调用身份、对目标对象和原操作的权限，以及结果读取范围；无权限时不泄露原请求是否存在。
2. 同键同摘要已有已提交记录：返回该操作当时的已记录结果，标记 `replayed=true`、原提交revision；不得重新调用Provider、写外部系统或再次推进状态。即使原租约已过期，也不把合法重放误作首次提交。当前状态另查快照，不改写历史返回值。
3. 同键不同摘要：返回 `IDEMPOTENCY_CONFLICT`。尚在处理中：返回 `IN_PROGRESS`与获准操作查询引用，不重复发起外部动作。
4. 尚无已接受记录：才按首次请求检查租约/attempt、版本、输入快照、生命周期及撤销门禁。未提交过的过期attempt仍拒绝；不能拿重放豁免首次提交。
5. 幂等记录与本地结果、状态变化同事务持久化。保留期限须覆盖在途任务、动作对账和授权迁移；归档结果后仍保留足够的去重墓碑或可核查索引，禁止删到无法识别旧动作。已过结果保留期限应显式返回 `IDEMPOTENCY_EXPIRED`或转核查，不能视作新请求；具体保留策略等待整体契约。

已提交历史返回值中的短期许可不因重放续期，后续动作仍重新验证当前授权/租约。合法重放可以来自经授权的恢复主体，但其代表原操作的权限必须由接入层验证，不能仅靠持有幂等键。

## 1. 业务注册

### 核心提供：`register_business(registration, auth_context)`

输入（由整体发布/安装模块在完成自身准入后提供）：

| 字段 | 含义 |
|---|---|
| business_ref | 精确业务标识与版本；不是触发词 |
| definition_ref | 已发布运行定义的引用及内容摘要，由约定 Resolver 解析 |
| contract_version | 运行接口版本，不是另创业务包版本规范 |
| provider_bindings | 获准的执行、规则、契约校验、回读 Provider 引用 |
| admission_ref | 安装/发布侧的准入证明引用；必须经可信通道核验，不能只是 `approved=true` |
| request_id / idempotency_key | 注册幂等与追踪 |

返回：`registration_id / business_ref / resolved_digest / state / readiness / blockers[]`。

- `state` 初始为 REGISTERED；注册不自动接单。`readiness` 描述依赖与能力是否满足，不代替启用授权。
- `set_business_state(registration_id, expected_revision, target_state, auth_context)` 提供启用/停新单的逻辑操作。启用先确认依赖可用和授权；停新单不删除在途任务依赖。撤销危险能力按整体紧急停用规则暂停受影响节点。
- 核心仅接受已经由约定 Resolver 解析和校验的运行投影：流程引用、依赖、执行者类别、输入输出契约引用、资源及超时/重试上限、等待和验收引用。投影字段最终与整体运行定义一一映射，不是第二份业务包清单。
- 同业务版本不同内容摘要拒绝。每个 Case 锁定注册/定义/Provider版本快照；新版本不修改旧 Case。停用与退役不是删除。
- 不从注册请求加载任意模块路径、脚本或 shell 命令。不读ZIP、不装依赖、不解释本体、不维护发布市场。

现状：旧 `ApplicationRegistry.match()`、`skill_versions()` 存在，但固定路由不是以上接口。**新接口未实现。**

## 2. 节点执行

### 核心提供的逻辑入口

| 操作 | 关键输入 | 返回 |
|---|---|---|
| `create_case` | registration_id、input_ref、object_refs、idempotency_key、auth_context | case_id、revision、绑定版本、status |
| `claim_node` | 受信 Worker 身份/能力、instance_id | Lease 或空；含 node_run_id、attempt_id、lease_token、deadline、input_snapshot_ref、executor_ref、资源集合 |
| `heartbeat` | node_run_id、attempt_id、lease_token、Worker身份 | 新租期或 LEASE_LOST |
| `submit_node_result` | node_run_id、attempt_id、lease_token、input_snapshot_ref、outcome、output_ref、evidence_refs、idempotency_key | 已接受状态、Case revision、事件引用或结构化拒绝 |
| `resume_case` | case_id、wait_id、event_id、expected_revision、材料/确认引用、auth_context | 当前Case状态与事件引用 |

`outcome` 提案：`SUCCEEDED / WAITING / RETRYABLE_ERROR / TERMINAL_ERROR / RECONCILE_REQUIRED`，由核心验证后接受。返回“成功”不等于 Worker 有权使 Case 成功。

### 核心调用的执行接缝：`NodeExecutor.execute(lease_context)`

- 可执行节点的input_ref/input_snapshot_ref只引用经获准DataProvider校验的快照；核心通过受信Provider核验来源、契约版本、权限和时效绑定，不接受任意文件路径、SQL或模型自报“数据已正确”。未验证材料由接入/数据侧隔离或待补充，不能作为已知事实放行节点。输入缺口由批准流程的等待/拒绝出口处理。
- 数据读取策略由批准节点/规则声明，DataProvider执行快照/时效缓存/强制回源；回源失败不能静默使用旧缓存。新观测可产生新快照，不覆盖旧Case绑定。核心不实现Excel解析、事实库或SourceAdapter，外部材料事件必须经授权入口关联Case，不允许接头直接改Case。
- 执行节点的分工从批准运行定义读取。CODE 使用获准处理器；AI只获得必要输入和局部工具；HUMAN登记持久等待并立即释放Worker。
- 输入按指定契约校验；执行器返回结构化候选结果，核心校验输出、证据和当前租约。AI不能注册 Provider、更改规则、获得任意终端或直接写业务系统。
- 外部动作通过下节定义的受控动作路径，执行器的 `SUCCEEDED` 不能代替独立回读。
- 接纳结果、变更 NodeRun/Case、记录事件、登记后继任务是一次事务。重试创建新 attempt，但同一逻辑外部动作沿用 action_id 和稳定幂等键。
- WAITING 必须返回获准 `wait_spec_ref`、缺失输入引用、超时策略；wait_id 由核心生成并记录。恢复事件须核对身份、目标、类型、输入契约与幂等，不能接受任意字符串“完成”。
- 资源声明由已批准运行定义和适配器强制约束共同计算；共享会话锁覆盖全部干扰区间。不能按步骤名称猜资源。
- 失租 Worker 不能首次提交节点推进；已接受请求的授权重放按0.1处理。可信迟到动作回执仅能走4.1的证据接纳路径；对于未知外部副作用，确认旧执行器停止或隔离冲突资源前不能放出新的冲突动作。

现状：旧 `WorkScheduler.enqueue/claim_next/heartbeat/complete` 与 `DispatchWorker` 可参考，仍含旧业务执行假设。**以上通用接口及全部保证未实现。**

### 2.1 实例生命周期接缝（P3，未实现）

由部署控制方调用，核心不提供安装、压缩、复制数据库或跨机选主实现。

| 操作 | 必需输入 | 返回与效应 |
|---|---|---|
| `control_instance` | instance_id、expected_control_revision、command、授权原因/证明引用、deadline、幂等键、auth_context | operation_id、控制revision、当前模式、blockers；仅承认控制请求落账，不同步等待所有任务结束 |
| `get_control_operation` | operation_id、auth_context | `ACCEPTED / RUNNING / COMPLETED / BLOCKED / FAILED`、目标/当前模式、阻断和观测时间 |
| `prepare_export` | 已停止调度的instance_id、expected_control_revision、迁移意图引用、auth_context及幂等键 | checkpoint_ref、数据/事件水位、依赖版本引用、就绪状态、blockers；不生成安装包，不含凭据 |
| `authorize_resume` | instance_id、checkpoint_ref、目标部署绑定、ownership_grant_ref、expected_control_revision、auth_context及幂等键 | 控制操作引用及批准状态；核验当前消费权和检查点后才可能恢复 |

`command`最小集合：`STOP_ACCEPTING / DRAIN / CHECKPOINT / PAUSE`。恢复只走 `authorize_resume`，不接受普通节点的resume_case代替部署授权。

- 持久模式提案：`RUNNING → STOP_ACCEPTING → DRAINING → QUIESCED`；紧急PAUSE可从非静止态进入 `PAUSED`，但未知动作和活动进程仍另外记账。`authorize_resume`经全部闸门可从QUIESCED/PAUSED返回RUNNING；命令重复和revision冲突遵循0.1。
- STOP_ACCEPTING提交后，入口不再承认新业务事件/创建新Case；已提交入口请求的合法重放只返回原结果。在途节点可以按既有授权推进。消费源游标只确认已持久接纳的事件；核心不以拒绝接单代替上游消费交接协议。
- DRAIN在短事务中关闭新的普通节点/动作领取，允许已领取工作在有界时间内完成及安全对账；禁止重试或后继节点绕过关闭状态。CHECKPOINT用同一排空机制将等待任务持久化并暂停，长期WAITING不占Worker，也不要求人为完成业务才能静止。
- 排空超时返回BLOCKED并保留停接单/停领取状态，不自动回到RUNNING。暂停不能假装已杀死外部进程；活动副作用仍按隔离与UNKNOWN协议处理。
- QUIESCED必须证明无有效的活动执行权、无仍可写入的旧执行器且无未解决外部动作；普通可迁移导出准备在存在UNKNOWN、对账中、失控执行器或证据不足时返回BLOCKED。核心不提供强制忽略阻断的导出许可。
- prepare_export在一致视图下绑定控制revision、Case/动作/幂等台账及事件水位、来源游标引用；待复制期间保持静止。任何使检查点失效的受理证据、撤销事件或状态变化均使旧checkpoint_ref失效，消费方须再次检查；实际备份一致性由部署/存储工具实现。
- 迁入初始PAUSED，不自动消费。部署控制方必须提供绑定源/目标部署、持久实例/幂等命名空间、消费范围、授权代际和有效期的可验证授权引用，以及旧消费权已撤回/旧写执行器已停止或被有效fence的证明。字段正式格式归P2，核心不自行签发授权。
- 核心启动、领取和动作放行都核验当前部署消费/执行权；跨机唯一性依赖共同权威控制，而非各机文件锁。无法确认有效权时失败关闭。单靠租期或授权代际不能阻止不支持fencing的外部系统旧写入；证明不足时保持PAUSED并隔离，不声明安全迁移。
- 撤销闸门、Provider健康、模型/规则依赖仍须在恢复时重验，不能靠已批准迁移绕过；无目标接头能力则返回具体blockers。

生命周期控制状态、操作结果和事件原子落账。网络探测和等待在事务外完成，结束时按控制revision再次核对，不能用过时观测完成排空。

## 3. 规则校验

### 外部规则模块提供、核心调用：`RuleProvider.evaluate(rule_request, trusted_context)`

| 输入 | 输出 |
|---|---|
| case/node/action上下文；action_id（有动作时）；action_name；业务/规则版本引用；object_refs；input_snapshot_ref；事实来源引用与时间；权威身份范围 | decision_id、`ALLOW / DENY / NEEDS_INPUT / UNAVAILABLE`、rule_ref与版本、input_digest、constraints_ref、reason_codes[]、required_evidence_refs[]、有效期/重验条件 |

职责：规则模块解析语义、获取/核实权威事实并独立计算；核心负责绑定、调用、校验返回者身份、保存决策引用，并在执行动作前强制检查。

- 不接收 Agent 传入的 `passed=true` 作为规则结果。核心不能在规则服务不可用时改用搜索或模型判断放行。
- ALLOW 必须绑定具体动作、参数摘要、对象/事实快照、规则版本和授权上下文，不是通用通行证。
- 规则要求的事实陈旧、身份/权限变化、关键输入变化或决策失效时重新评估；输入竞争性变化需要动作接头原子条件写入或等效保护，不能仅靠短TTL保证。
- DENY 拒绝动作；NEEDS_INPUT进入正式等待；UNAVAILABLE按依赖故障策略等待/有限重试，不得视为业务不合格或允许。
- 规则调用原则上只读外部事实；其业务状态写入不在本接口内。核心只持久决策引用与审计记录。

现状：旧代码有局部状态/版本门禁，但没有这套跨业务 RuleProvider。**接口未实现；规则库与规则实现不属于本分支。**

### 3.1 规则/Provider撤销事件入口（P3，未实现）

`apply_dependency_event(event, trusted_context)`：输入权威issuer、event_id、被撤销的精确定义/规则/Provider引用与版本或摘要、issuer_revision、生效时间、reason_ref；返回接纳序号、当前撤销水位、影响查询引用和处理状态。事件格式、签发者及撤销/恢复授权仍归架构侧P1/P2。

- 在同一短事务先记录撤销事实/闸门和事件，之后才允许分批构建受影响列表。每次领取、规则决策使用、动作放行及结果推进均检查该闸门，不能等影响扫描完成才拦截。
- 使用注册、Case、节点实际绑定及已用决策/输入溯源引用定位影响；包括依赖被撤销结果的未完成后继节点，不用字符串相似或业务名猜。若溯源缺失，保守暂停无法排除影响的范围并报告缺口，不谎称“精确扫描完成”。
- 未启动节点进入持久执行暂停闸门并等待重验；在途节点登记取消/隔离要求；已写入或UNKNOWN动作继续记录事实并走获准只读对账，不因为撤销而抹去意图、证据或自动重发。
- 暂停是独立的执行许可状态，不能覆盖RECONCILING等事实状态。已完成Case不倒写历史完成事实，追加影响标记并按授权建立复核，不追溯伪造未发生过的结果。
- 撤销与动作放行在核心按事务顺序裁定；已放行的网络请求无法保证撤回，标记在途风险并隔离核查。受影响的正常结果不得直接解锁后继，须通过现行授权重验。
- 先核验签发者及其可控制范围；身份不可信的事件拒收，不能借伪造撤销暂停任意业务。同事件幂等；更低issuer_revision不能恢复权限。可信通道内乱序、缺版本或同步缺口只在获准范围内保守阻断并请求权威同步。恢复必须是授权的新版本事件及重验，普通resume_case不能撤销此闸门。
- Provider本身撤销时不得为了对账继续调用被撤销代码；等待权威侧指定获准替代读取Provider或人工核查。核心不自行选择业务规则或接头。

## 4. 外部回读（含必要的动作关联）

### 核心动作闸门：`request_action(action_request, trusted_context)`

输入：case_id、node_run_id、有效领取身份、adapter_ref、action_name、参数/目标引用及摘要、规则要求、verification_spec_ref、稳定幂等键。

核心先核对租约、资源、权限和所需权威决策，持久化 ActionIntent 后，才交给获准 `ActionAdapter.execute(action_context)`。参数是否完整、资源是否独占及具体写入方式由批准接头承担，不绑定业务字段。

写入候选结果：`ACKNOWLEDGED / REJECTED / UNKNOWN`，附 `action_id / attempt_id / external_ref? / safe_receipt_ref`。ACKNOWLEDGED 只是接头收到响应，不表示验收通过。

### 外部验收模块提供、核心调用：`ReadbackProvider.verify(verification_request, trusted_context)`

输入：action_id、adapter_ref、精确 external_ref（已知时）、持久化的对账定位键、verification_spec_ref与版本、预期参数摘要/证据引用、deadline。

返回：`verification_id / verdict / external_ref? / observed_at / source_ref / evidence_refs / mismatches[] / retry_after?`。

`verdict` 提案：

- `VERIFIED`：精确目标和规定字段/状态/附件满足验收。
- `MISMATCH`：已找到目标，但不符合约定。
- `NOT_FOUND`：本次没查到，不能自动推导“从未写入”。
- `INCONCLUSIVE`：查询异常、歧义、最终一致性窗口等导致无法确认。

### 未知结果的编排规则

- ActionIntent状态提案：`PREPARED → EXECUTING → ACKNOWLEDGED / REJECTED / UNKNOWN → VERIFIED / MISMATCH / RECONCILING`。VERIFY失败不能改成写入失败并盲目重发。
- 已知外部单号先回读精确目标；未知单号只能按已存的动作定位键与批准查询范围对账。多个匹配结果必须阻断，不选最近一条。
- NOT_FOUND/INCONCLUSIVE不能直接重新创建。只有接头的幂等保证或权威证据明确允许时才可能重试，且沿用稳定动作身份；否则人工核查。
- 回读由独立读取路径完成，不能把写入响应换个包装当证据。同一接头包可实现读写，但读回路径必须实际访问目标，身份与权限按整体安全契约隔离。
- 核心验证返回 Provider 身份、动作绑定及证据要求，不允许业务执行Agent直接提交一个伪造 `VERIFIED`。
- 不通过回滚本地代码声称撤销外部操作；补偿动作如业务需要，必须另行授权并按完整链路执行。

现状：旧 `DwsReceiptTransport.deliver/reconcile` 和 `OutboxStore.reconcile_unknown` 可作机制参考，本轮未实测外部交付。**通用动作/回读接口未实现；具体业务接头和验收判据由整体架构侧提供。**

### 4.1 回执、回读提交与迟到结果（S2，未实现）

网络写入、网络回读均在数据库事务外进行。核心持久化动作意图/执行attempt后再调用接头；外部动作与本地数据库不假装是一个分布式原子事务。

| 阶段 / 内部受信接缝 | 提交内容与竞争约束 |
|---|---|
| `record_action_receipt` | 以receipt_id、action_id、执行attempt、目标/参数摘要、来源及证据引用接纳ACK/UNKNOWN等事实；先验来源身份，再幂等追加。无关联动作或摘要不符拒绝。返回evidence_ref与接纳状态，不赋予节点推进或解锁资源权限 |
| `claim_reconciliation` | 核心为持久action_id领取独立reconciliation_attempt与租约，绑定expected_action_revision、验收/依赖版本和观测要求。一个有效领取者可裁定，其他合法回读只能作为候选证据 |
| `commit_reconciliation` | 当前获准回读者提交verification_id、reconciliation_attempt/lease、expected_action_revision、验收绑定、verdict及证据。事务内重验身份、租约、控制/撤销闸门、动作版本、证据新鲜度及因果关系 |

- record_action_receipt允许可信旧Worker提交迟到事实，即使它已失去执行租约；它仍须具备当前有效的“提交动作证据”权限。该权限不授予执行权或节点推进权，已撤销身份不能借此读旧结果。必要时由获准接头回读替代。
- 对账结论持久化、Action状态裁定、允许的NodeRun/Case推进、事件和后继任务在同一短事务中提交；提交失败全部不生效。若生命周期/撤销闸门不允许推进，保留权威观测并转待重验，不能放行后继。
- 同一action_id的裁定通过action_revision和有效对账租约竞争；败方结论只能标为过时观测，不覆盖新结论。不能只按observed_at墙钟时间决定新旧；Provider应提供可用的目标版本/一致性证据，不可比较时转INCONCLUSIVE或重新读。
- 迟到ACK不得把VERIFIED退回ACKNOWLEDGED；迟到矛盾事实追加审计并触发新的获准复核/风险标记，不篡改既有结论。新的复核是新reconciliation_attempt，不重用旧结论覆盖。
- 写入成功后进程退出：恢复时保持UNKNOWN/RECONCILING，仅回查目标，不重新创建。回读成功但本地事务提交失败：允许仍有权的同一回读提交幂等重放；失租或输入过期则重新领取并复核，不重复业务写入。
- 状态裁定成功不自动证明旧执行器已停止；资源解除隔离还须有停止/有效fencing证明及无冲突动作，否则保留隔离并限制后继资源使用。

上述回执/对账入口仅对获准接头和核心调度开放，不是给业务Agent任意标记VERIFIED的公共工具。

## 5. 事件查询

### 核心提供：`query_events(query, auth_context)`

输入：`case_id? / business_ref? / node_run_id? / resource_ref? / event_types? / states? / time_range? / cursor? / limit`。

返回：`items[] / next_cursor / has_more / watermark / observed_at`。

每条事件建议包含：event_id、sequence、case_id、case_revision、node_run_id、attempt_id、type、recorded_at、occurred_at（若可得）、actor_ref、trace_id、causation_id、版本绑定引用、脱敏详情/证据引用。

- 存储提交时分配 sequence，并与状态原子落账；不依赖设备时钟排序，时间必须附时区。
- cursor绑定筛选范围、授权范围/版本、最后扫描序号及固定高水位，且需防篡改。分页只读取 `(last_sequence, upper_watermark]`，按sequence排序；新增事件待本窗口完成后在下一窗口读取。重试同页可重复返回，消费方按event_id去重，不承诺网络交付恰好一次，也不得把被过滤事件数称作本页数量。
- 无完整总数就不返回 total；has_more根据真实剩余记录计算。游标超出保留期报 CURSOR_EXPIRED，不能悄悄当成空列表。
- `get_case_snapshot(case_id, auth_context)` 返回当前Case、节点摘要、阻断原因、资源/回读摘要、版本、revision及事件水位，供时间线和断线重建。快照与水位来自同一已提交一致视图，禁止先取状态再单独读取更晚MAX(sequence)。提交序号必须对应可见提交顺序，禁止事务预分配序号后乱序提交造成低序号晚出现。
- 只读，不接受通过查询接口推进状态。原始附件、凭据及未经脱敏的错误不进入列表。
- 首期传输可轮询，是否SSE/WebSocket由整体接入层另定。现在没有可访问URL。

现状：旧 `CaseCoordinator.snapshot/get_case/get_case_evidence`、Outbox查询为局部能力。**统一事件查询、稳定游标和实时接口未实现。**

### 5.1 快照、水位与恢复（S3，未实现）

- 核心在同一一致读视图取得授权状态和水位W，消费方以W之后的事件续读；若是异步投影，只能返回该投影实际完整应用的水位，不得配上权威库的更晚水位。
- 快照创建过程不跨请求持有长数据库事务。分页快照须使用存储版本视图或有期限的物化结果，并返回snapshot_ref及有效期；不支持固定视图时明确报能力不可用，不能退化为边翻页边变化的状态。
- 当前窗口末页即使没有可见事件，也返回可续读的进度游标；推进到实际扫描的高水位，避免无匹配事件时永远重复扫描。has_more只表示本固定窗口内符合权限/筛选的剩余记录，非未来事件。
- 过期游标、权限范围/版本或筛选变化返回 `CURSOR_EXPIRED / CURSOR_SCOPE_CHANGED`，重新取授权快照，不能只继续过滤旧游标。每次请求仍重验当前授权，不能靠旧snapshot_ref保留已撤回访问。
- 事件中的states筛选以记录时的运行状态为准，不动态连接当前Case状态。不使用“只订阅RUNNING事件”来维护当前RUNNING列表：应订阅有权范围内所有相关状态变化，再应用显示过滤；离开范围时发送获准删除/失效信号或要求重建，避免旧条目永久留在看板。

### 5.2 业务/Case发现与运行健康（P4，未实现）

| 只读操作 | 输入 | 返回 |
|---|---|---|
| `list_businesses` | 授权范围、启用/就绪状态筛选、snapshot_ref/cursor、limit | 可见注册业务版本、启用状态、就绪/阻断摘要与snapshot_ref、水位、分页信息 |
| `list_cases` | 授权范围、business_ref、当前状态、时间/资源筛选、snapshot_ref/cursor、limit | 当前Case摘要、节点/阻断摘要、revision与一致视图分页；不要求预知case_id |
| `get_instance_status` | instance_id、auth_context | 接单/领取状态、生命周期模式、控制revision、控制操作、迁移阻断、观测时间 |
| `get_runtime_health` | instance_id、授权资源/Worker范围、cursor/limit | Worker会话、最后心跳、资源占用/隔离、队列观测，以及观测分页/时间；不主动探测外部系统 |

- list_cases/list_businesses分页与5.1共用一致视图规则。当前列表不从有限历史事件猜测；事件保留期以前创建的未完Case也必须可发现。
- Worker观测包含worker_session_id、last_seen_at、heartbeat_interval/失联阈值；状态至少区分已观测在线、超过阈值未见、从未观测/未知。失联只描述观察，不证明进程已停止。
- 资源观测包含owner/attempt、lease_expires_at、隔离标记、相关动作/Case引用。租期已过而隔离未解除不能显示“空闲”。
- 每项观测返回 `observed_at / as_of / freshness / reason`；freshness至少为 `FRESH / STALE / UNKNOWN`。健康列表受授权和分页限制，不以隐藏项为零；缺观测用null/UNKNOWN，不填零故障或全绿。empty只有在成功、完整且范围明确的查询中表示无记录。
- 心跳/健康是带时间的只读观测，可独立轮询，不冒充由Case事件完整重放得到的健康状态。若返回聚合数，标明授权范围、覆盖度和同一观测视图；无法完整计算不返回伪精确total。
- 接头可达性、外部登录/权限、模型可用性由外部健康模块提供带时间的只读观测，控制台聚合；核心只暴露其已获观测引用及调用失败事实，不硬塞EAM/钉钉等探测实现，也不把调用未报错当作外部健康。
- 发现与健康查询沿用权限过滤，不授予暂停、迁移或恢复权限；界面通过其他受控命令操作，不能借GET改变状态。

## 6. 双方需要对齐的最小清单

| 待确认项 | 本分支提案 | 整体架构侧需提供/确认 |
|---|---|---|
| 业务运行定义 | 核心只注册批准后的定义引用与不可变摘要 | 现有权威字段、定义解析入口、版本与撤销规则 |
| 执行节点 | 统一领取/租约/输出/等待，节点分工由运行定义声明 | 节点描述格式、输入输出校验器、执行Provider接口 |
| 对象与规则 | 对象引用透传，调用权威 RuleProvider | 对象/事实引用格式，规则求值及可信决策绑定方式 |
| 外部动作与验收 | 核心存意图、隔离UNKNOWN、独立回读后推进 | ActionAdapter/ReadbackProvider、资源强制约束、稳定查询键、验收规范 |
| 事件消费 | 核心提供只读快照、事件序号和游标 | 既有状态/事件命名、权限范围、看板所需筛选及保留期 |
| 生命周期与撤销 | 核心提供停接单、排空/检查点、导出准备、批准恢复及撤销闸门 | P2消费权权威、迁移身份/授权代际、撤销事件签发与恢复规则 |
| 发现与健康 | 核心提供当前业务/Case列表、Worker与资源观测 | 控制台筛选/时效门槛；外部健康Provider的观测契约 |

确认方式：整体架构方在以上接口逐项标记“接受 / 映射到已有定义 / 需调整”，给出权威文件路径和字段映射即可。不要求另起一套设计，不在本轮选装新框架。

## 7. 后续契约验收要求（未运行）

- 同版本不同内容拒绝；缺依赖不能启用；注册不能加载任意代码。
- 两个独立Case可并行；同资源冲突排队；已提交同键同内容且仍有权的重放返回原记录，不重复推进；不同摘要、未提交过的过期attempt、已无权限重放分别拒绝。
- WAITING不占Worker；错误身份/Case/输入不能恢复；重放事件不重复推进。
- 伪造规则通过、决策过期、输入变更、Provider不可用均不能写入。
- 写入后进程崩溃、响应丢失、旧Worker仍活动时不重复产生外部副作用；不确定时明确转核查。
- 写响应不当回读；精确目标不一致不完成；本地回滚不冒充外部撤销。
- 状态/事件/后继任务事务中断后不出现半提交；分页、断线续读、权限过滤和水位一致。
- S2：写成功后进程退出、回读成功后本地提交失败、两个对账者竞争、旧Worker迟到回执、矛盾迟到证据，不造成重写、陈旧覆盖或提前解锁。
- S3：快照获取中并发提交、低序号晚提交防护、跨页新增、空筛选页、游标过期/授权变化、任务离开显示筛选范围，重建结果与授权权威状态一致。
- P3：停接单响应丢失重放、排空超时、WAITING检查点、UNKNOWN阻断导出、过时检查点、复制库无消费权、旧执行器无法fence、迁入未经批准均不偷跑。撤销与领取/放行竞争、影响扫描未完、乱序撤销及已完成Case复核均验证。
- P4：无需case_id可发现当前任务；新Worker无心跳、失联但进程存活、过期锁仍隔离、分页/权限不完整、外部健康无观测，不能展示虚假正常或越权结果。

测试接缝分别放在公开逻辑接口、隔离存储/双Worker、受信假接头对抗测试，以及获准的真实外部回读。模拟接头仅证明本地协议，不证明任何真实系统接通。
