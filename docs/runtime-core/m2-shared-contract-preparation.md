# M2共享契约落地准备

署名：Laiqh。仓库：`lqhoyh121-afk/xiehe-runtime-foundation-design`。任务：Issue #25。准备作者：`M2-SC-PREP-author-86c322f13e`。

**DRAFT / 准备回件，待主控1接收、原主控2独立消费复核。本件不是共享契约、M2运行代码、架构冻结、合并或版本发布的批准。**

一句话结论：先在原共享Schema/validator补齐机器表达，在原interfaces/design收口运行口径；核心和工作流只消费同一份固定版本。推荐保持`0.1-draft`的受控增量，但以精确摘要组合及显式M2 A/B支持共同准入，不能仅认版本字符串或profile标签。

## 1. 固定输入、基线与本轮权限

### 1.1 交接依据

- Issue正文连同主控1准备就绪评论（#25，`issuecomment-5629358303`）为范围依据；后者明确本轮独立绑定、唯一准备文档白名单及本会话单条认领例外，不把正文早期“仅发布”当现行领取状态。
- 本会话真实认领（#25，`issuecomment-5629438394`）由本机入口读取真实会话身份后生成，已独立GET精确回读；不是主控代领、账号assignee或自动Worker。精确评论URL保存在本机HANDOFF，内部会话定位不外发。
- 唯一产品产出为本文件。固定输入、授权、门禁脚本、共享Schema、运行代码、测试、CI、依赖和其他工作树均只读；本次不stage、commit、push、建PR、合并、发布或生产写入。一般远程写权限仍关闭，不发完成评论。
- 沿原Issue续办，不重开两份M2候选返修，不占用WF2 F01/E01工程师，不启动原主控2或替其签复核。任务状态唯一权威仍为GitHub Issue，本机回件只是证据与断点。

### 1.2 固定材料目录表

C、T是主控交接的本机固定输入，**未随代码发布到远程main**。下表逻辑相对路径只用于标识材料，不是可下载链接；私有接收报告仅列代号、标题和摘要。源定位及原始证据不进入本文。引用C/T节号只定位已接收内容，不复制第二份字段协议。

| 代号 | 固定材料 / 用途 | SHA-256 |
|---|---|---|
| C | `docs/runtime-core/m2-contract-candidate.md`；已接收A/B详细候选 | `c547804a3a921b79f60a866e55aacfdb9decca2e96a811881ab829db8affa7e7` |
| T | `docs/runtime-core/m2-implementation-ticket.md`；既有未来验收矩阵 | `5302ef1d1466f4197a43dc72e0c38a8e9591253cd17b34f30207f30e54b23317` |
| R1 | 主控1《RPT-01报告校正通过》接收记录 | `6485084457c3286477a5498d4b0a9032f651d6933ea34e6dc688d8c15d6ab100` |
| R2 | 主控1该次独立核验收据 | `fc1dc92743db40e5f0486833a2a50dbb91aa95c9b485472455e1d75b8b3f28d8` |
| R3 | 主控2《M2完整A/B候选工作流消费适配复核回件》RPT-01校正版 | `4a4300de0b0f9c4802c7fcab7d75be6f273465f5ea0e91daff312522830df412` |
| W1 | `docs/skill-toolchain/first-version-plan.md`；作者工具规划及I1–I8 | `72ba48cbddd180e41d314b7bc23845b63093d60f26c019eac68d54d4b26d2467` |
| W2 | `docs/skill-toolchain/g6-task-revision-candidate.md`；G6/G6-S1分层责任 | `86947a3852519ba3b9c989dc0aa6daa0008e6ef9f4453131b34c19b6dfce58fa` |
| A1 | 主控1《R2核心侧回件：首次领取前的恢复补齐建议》 | `bda9cf3ed3088609049a707c2e96071370592aad9075001f0ab7ec884c1d581a` |
| A2 | 主控2《R2首次领取前的A/B合同范围确认》 | `493560a1679b5d3aaae9e046a5b20b375551982252f7771f2f5ee3c2cef219fe` |

本会话逐份读完并重新计算9份摘要，与绑定一致；未追读相邻作者活动树。R1/R2/R3证明C/T的双主控文档复核已通过，不代表**本准备回件**也已复核，更不是M2运行结果。A1/A2及C/T内早期“待接收”文字保留为历史，不倒退后来接收，也不借后来接收解锁实施。

### 1.3 源码基线与依赖快照

- 本树精确base：`efa8ab6b74ba83a6969354a469731e9ccdee06fe`，对应已合并M1 PR #24的head。
- 本轮独立回读远程main：`300b0b95be95d884c2e1cd5775a85bebad3ba6ca`，是merge commit，不是本机base。两者Git tree均为`cc8e658eee0b233cf66f904b7cfbbaff243ef0b0`，本轮文件树相同；**commit身份不同，不自行换base**。
- 已读#25及关联#2/#4/#5/#6/#8/#12/#13的完整正文、全部评论和最近PR。本轮所读依赖仍OPEN；#2已有局部范围/入口确认，不能据此宣布G0/G3整体完成。
- Issue #8的WF2 F01/E01仍归原工程会话；PR #26初读为Draft，末次回读已非Draft、仍OPEN且未合并，head仍为`a77246450d6c10420998131aa6d1148a58a7eb55`。其正文尚写Draft，当前状态以API元数据为准；转为可审阅不覆盖旧独立FAIL。本卡仅读元数据/文件清单做冲突检查，不以该候选替换M1基线。
- G3 #5、装配准入 #6、P1/P2及正式来源保证继续保留。主控须在下阶段重新回读并确定精确整合base，不能从本快照推断未来仍无漂移。

| 基线唯一文件 | 当前SHA-256（不是未来落地摘要） |
|---|---|
| `docs/architecture-track/contracts/authority-contract.schema.json` | `4599e93aa8b022fff3a480b566a0b056584863291af390594a8f6ce0570dbab9` |
| `spikes/002-authority-contract/validator.py` | `d67e3ac3c8f29c4f561978c5a86828514b3313d74bdd321a64c9c11747c1b2ab` |
| `docs/runtime-core/interfaces.md` | `aac6709183cf10392e289163e5d0f228e1c16a0515a056106931f7475e63c1ba` |
| `docs/runtime-core/design.md` | `2e79c68dc35e8bb85130990087f42c86bca45a2207d57b914a894466d4ef8360` |

## 2. 具名维护提案与交接顺序

下表是**供总负责人确认的具名建议**，不是这些会话已承诺、已认领或已有代码写权。实际工程会话、独立目录和时间占用须由主控再绑定；无法确认某承担者就阻断对应代码卡，不凭空造一个“共享维护者”。

| 责任 | 唯一候选承担者 | 产出 / 复核与限制 |
|---|---|---|
| 本卡准备作者 | `M2-SC-PREP-author-86c322f13e`，已真实认领 | 仅本文件及本机回件；交主控1，不自签接收 |
| SC01–SC03 Schema与语义validator作者 | 提议`M2-SC-PREP-author-86c322f13e`在未来新assignment中承担 | 同一作者维护原Schema/validator及本卡所提新增共享测试；主控1核运行语义、原主控2独立核工作流消费。此建议不延长当前任务授权 |
| SC04接口文档作者 | 提议主控1 | 只维护原interfaces/design的唯一运行口径；原主控2复核消费。未来运行工程作者另绑，不占用WF2原工程师 |
| SC02受信输入组装、SC03来源验证Adapter作者 | 提议主控2作为后续**本机合成Adapter**候选承担者 | 与共享字段作者分开；须明确实际工程会话后才能派工，来源核验由主控1另安排独立检查，不由Adapter作者自签。生产来源作者及真实保证机制**尚未提供，生产接入阻断** |
| SC05版本记录维护与操作 | 提议主控1唯一维护修订记录、汇总摘要并办理获准交接 | 作者给固定字节，主控2给独立消费意见，总负责人`lqhoyh121-afk`决定接收/冻结/合并/发布；Agent记录者不是批准者 |

建议顺序：主控1接收本准备回件 → 原主控2独立消费复核 → 总负责人决定维护人、版本策略及最小共享子集与G3/P1/P2关系 → 签发共享落地assignment → 共享形状/语义与原接口落地、精确摘要接收 → **另行**签发M2本机实施assignment → 真实运行验收 → 工作流后续集成。任何提交、合并、版本发布分别授权。

W1 §3–4及W2 §3/§5的分层仍保留：WF0/WF1可做已接受的离线作者子集，不等完整M2；未有机器表达的槽位只能是阻断草稿。WF2完整顺序/等待/恢复须真实核心和生成包接入，WF4动作/回读后置，不把本机合成M2当作者包已验收。

## 3. SC01–SC05唯一落点与消费矩阵

本文源码行号均绑定§1.3 base；共享类型用JSON Pointer精确定位。未来基线变化须重定位，不机械套旧行号。

### SC01｜等待声明

- **已有定义**：[authority-contract.schema.json](../architecture-track/contracts/authority-contract.schema.json)的`/$defs/WaitDefinitionRef`（107行）只限定kind=wait；`/$defs/Node/properties/wait_spec_ref`（317行附近）是可null引用。`/$defs/DefinitionRecord/properties/content`（505行起）只要求object，当前**不存在**`/$defs/WaitSpec`，引用槽不能充当材料等待合同。
- **唯一拟新增机器落点**：同一Schema的`/$defs/WaitSpec`；字段详细规则仅取C §3.1。内容校验和引用闭包仍由[validator.py](../../spikes/002-authority-contract/validator.py)承担，复用`shape`（111行）、`resolve`（159行）及`validate_projection`（229行）。“等待已消费/无attempt”属于运行条件，不塞进静态Schema冒充动态保证。
- **既有消费路径**：`Host.validate`（[synthetic_host.py](../../src/runtime_core/synthetic_host.py):214）→`check_consumption`（[authority_checks.py](../../spikes/002-authority-contract/authority_checks.py):163，174行调用`validate_projection`）→共享校验，然后`contract_adapter.capabilities`拒绝M1的wait。工作流声明者消费W1的I4/I5，不生成wait_id或自建等待循环；当前规划文件不是生成器实现证据。
- **未来运行消费**：C §4/§6/§8的上游submit建立下游WAITING、释放上游执行权；首次resume只消费一次；材料修订与消费次数分开。A与首次claim同提交，B仍在首次领取前且不重开CONSUMED。合法非null等待期限可被共享表达，但M2能力层必须拒绝；缺省不能默认为无期限。
- **维护/验收**：§2共享作者；原主控2复核I4。静态切片S-WAIT及未来T的L1-C02/S01/S03/S04、L1-A01/B01/B05、T01/T02/T09分别验形状、一次消费、A/B窗口，不混为本轮已运行。
- **越界停止**：未获shared白名单、要求新增定时器/重试、把旧不明wait直接当M2可执行内容、或需要改M1旧反例时停写。

### SC02｜输入映射与嵌套闭包

- **已有定义与缺口**：Schema `/$defs/Node`（274行）无`input_bindings`，也无`/$defs/InputBinding`。`validate_node_graph`（validator.py:173）只做图约束；`validate_projection`（241–251行）只收Node直接`*_ref`及已声明记录的dependencies，不能自动发现新数组内部引用。
- **唯一拟新增落点**：`/$defs/Node/properties/input_bindings`及`/$defs/InputBinding`，语义检查仍在原validator.py；必须覆盖数组内`source_contract_ref`和WaitSpec材料模型的完整已发布依赖链。不能只校引用kind、漏掉精确版本/摘要、scope或依赖声明。
- **兼容底线**：按C §3.2及T L1-C04，新增字段可选、可null，数组item引用InputBinding；Node原required集合不变。旧M1/M2根仅**缺省/null**明确沿原`input_ref`和完整根模型。不得把浅层Schema接受空数组外推为旧根消费许可。M2下游必须非null且恰有两个完整合法绑定，缺省/null/空数组/一项/三项都不准入。
- **语义与消费**：`source_kind`严格为`NODE_OUTPUT`或`WAIT_MATERIAL`。前者绑定唯一父输出及`PINNED_ACCEPTED_OUTPUT`历史政策；后者绑定同槽当前材料和`CURRENT`。slot唯一/排序、父关系、模型内容精确相等、整对象嵌套均取C §3.2，不增JSONPath、默认值或类型强转。`Providers.data/validate`（[synthetic_providers.py](../../src/runtime_core/synthetic_providers.py):52/61）目前只读单一current_input；它不是已经支持下游组装的函数。
- **分工**：共享作者定义形状/纯语义；§2独立Adapter候选负责获权读取与完整输入组装；核心只消费裁定并CAS落账。W1 I3/I6、W2 §5消费同一映射，不能在作者工具内部另造数据传递协议。
- **验收/停止**：S-MAP及T L1-C03/C04/A03/B02。映射必须经真实共享入口和核心现有导入路径验证；根缺真实输入不能变WAITING。闭包、模型或Adapter保证不足就阻断，不能“先装进去再补”。

### SC03｜材料事件、替换意图与可信来源

- **已有定义**：`/$defs/EvidenceRef`（Schema:139）仍且只含`evidence_id,digest,scope,observed_at,valid_until,source_ref,retention_policy_ref`七字段，禁止加Case/模型/材料版本等私有键。当前没有`MaterialEvent`、`ResumePayload`、`MaterialReplacementIntent`或`ReplaceMaterialPayload`。
- **唯一拟新增机器落点**：上述四个`/$defs/`定义全部放原authority-contract.schema.json。普通事件/载荷取C §3.3/§5.2；B独立意图/载荷取C §5.4。只做引用，不在核心另存材料Schema。
- **易错字段核对**：B payload外层是`expected_revision`和`replacement_intent`；稳定身份为`replacement_intent.intent_id`。材料预期/新版本及`expected_input_snapshot_id`、`expected_input_version`在意图内。`source_intent_id`是接纳后来源链字段，不是请求身份；不存在`expected_input_snapshot_ref`比较字段。主体是`initiator`，`material_replace`是权限，不是主体。按R3的RPT-01校正口径，不再误转述。

| 层次 | 唯一责任 / 验证边界 | 验收失败条件 |
|---|---|---|
| Schema形状 | 共享作者；`shape`复用唯一`$defs`，严格类型/额外键/Id/引用/整数与时间基础规则 | 非法event_type是SCHEMA_INVALID，不是“结构合法但能力不支持”；bool/float不能冒充材料整数版本 |
| 静态目标/引用关系 | 原validator内共享纯语义，核心提供明确目标快照后使用，不在Schema查库 | 错模型/父依赖/冻结引用必须拒绝，不用字符串相似关联 |
| 动态目标/消费与CAS | 未来Service/Store，原Case→NodeRun→wait→Binding→首次消费链及版本检查 | 普通resume只接纳版本1；新事件不能再推进CONSUMED，B不修改原接收记录；已有attempt关闭A/B |
| 来源真实性与真正新材料 | §2来源Adapter候选；独立重读受信不可变事件/意图全字段、真实内容、来源版本及摘要 | 请求自报有效、复制旧材料改时间或摘要不作新来源；服务不可用不能当自然到期 |
| 当前授权与提交覆盖期 | 可信宿主/来源权威提供；核心提交前重验，来源Adapter提供可独立核对的版本/授权保证 | 本机锁不证明远端未变；来源保证不可用则DEPENDENCY_UNAVAILABLE等原码阻断，不替生产Adapter背书 |

- 现有`Host.authorize`（synthetic_host.py:201）只有原操作/读取/角色约束；`Providers.evidence/data`（43/52行）只有当前合成M1证据路径，均不是M2材料真实性与新权限已实现。C §7的`source_check`归SC04内部审计，不另造一种AuthorityRef或自签授权凭证。
- **验收/停止**：S-MATERIAL及T L1-C05/C06/I01–I04、L1-B02–B05/T03/T05/T08。形状测试成功不能标来源验证通过；生产来源作者/保证机制缺失保持明确阻断。本卡不生成合成材料事件来冒充已落实机器契约。

### SC04｜运行接口、原子接纳及查询审计

原[interfaces.md](interfaces.md)是唯一逻辑接缝文档，原[design.md](design.md)维护职责/状态说明；两者开头“全部待实现”是历史宽口径，不能据此否认已合并M1。未来只在其原章节加入分层支持说明，不重写整份设计、不改本轮固定C/T。

| 原维护位置 | 未来最小增量 / 真实消费点 |
|---|---|
| interfaces §0/§0.1（11–31行） | 明确M1请求摘要不变、当前授权先历史、A无独立刷新槽、B独立意图历史；对应Service.identity/replay（service.py:117/124） |
| interfaces §1（33–56行） | 共享版本与精确摘要组合、受信能力准入、register与enable分开；对应Host.resolve_binding/validate、contract_adapter.capabilities |
| interfaces §2（58–84行） | 将材料resume与HUMAN确认分层；按C维护resume/B及claim的绑定/返回/拒绝和权限。真实链是CLI.main的run-once（runtime_core_cli.py:69–71）→Worker.run:51→prepare:35→claim:18→Service.execute:26→node_command:208→commit:136→Store.write:58 |
| interfaces §3（111–127行） | 仅声明缺项的后继就绪检查允许NEEDS_INPUT；根/完整输入/规则拒绝/不可用不一律WAITING。现有Service.rule:194仍只接受ALLOW |
| interfaces §5（194行起） | 原resume收据与当前输入/材料版本链分开；NODE_LEASED审计A、MATERIAL_REPLACED审计B；query同一视图核权限/水位且不触发恢复。现有Service.event/query在131/299行 |
| design §4–5（60–126行） | BLOCKED/领取前WAITING、单次消费、不可变多版本与唯一当前指针、A同claim事务/B独立事务、既有attempt后拒绝；不把M3–M6全部原语拉进M2 |

**A不能挪到Worker.prepare领取之后。** C §4.4规定事务外准备、与首次claim共同提交证据/来源链/当前输入/attempt/租约/原claim幂等/领取事件/READY移除；失败全旧，无独立刷新阶段或命令。B按C §5.4/§5.5独立换料，不变为普通resume别名；新材料仍有效而证明再过期回到claim内A，不要求重复交资料。已有attempt即使租约过期也不得重领或换料。

运行状态、RuntimeEvent、规则决策与`source_check`目前无共享`$defs`；本次建议仍由SC04原接口唯一维护，不新增runtime-event.schema.json。接口引用共享字段，design引用接口，不同时维护两份字段表。未来若确需机器化运行事件，先单独确认一个唯一文件/作者及旧定义退役，不能由本卡暗增。

静态文档落地须逐条映射C §4.4/§5.4/§5.5/§7–9及T的A/B/X组；真实事务、Provider调用、竞争、读水位只在后续M2 L1/L2证明。本卡及下一张共享静态切片不能冒称运行链已验收。维护者按§2；触及共享类型新建第二协议、WF2在途文件或运行实现即停止本卡写入。

### SC05｜版本与兼容

**唯一推荐：受控DRAFT增量，不升级共享根`contract_version=0.1-draft`或Schema `$id`，不发新运行版本；用精确文件摘要组合区分修订，未来M2必须显式满足A/B能力与来源保证后才启用。** interfaces的v0.2是逻辑文档版本，不充当共享Schema版本或软件版本。所有建议待负责人批准。

选择依据：新增字段保持可选/null、EvidenceRef及Node原required不变；旧引用、P1/P2、迁移和既有M1摘要路径可保持。直接把共享根改成另一常量会影响ProviderDescriptor、Projection、ConsumptionRequest和多类权威记录，以及[migration-contract.schema.json](../architecture-track/contracts/migration-contract.schema.json)的跨Schema URN和[migration_checks.py](../../spikes/002-authority-contract/migration_checks.py):21–35的Registry，不适合夹在本次最小共享落地里。

#### 静态增量如何不误伤旧消费者

- 原`shape`和`validate_projection`保留既有调用签名及旧P1检查义务。新增可选映射出现时补嵌套引用闭包；无M2声明的旧图仍按既有共享子集检查，不能把所有历史DefinitionRecord.content强制改成M2材料形状。
- 建议在**同一validator.py内**新增一个明确的材料语义消费入口（拟定名`validate_material_projection(projection, authority, context)`，当前不存在、须下阶段卡固定）。它先调用原`validate_projection`，再调用同一Schema的WaitSpec/InputBinding形状和已接收材料语义；必须完整核等待内容、映射、闭包与模型，不能“识别不了就回旧检查”。这是单一共享validator中的增量入口，不是第二个Schema或核心私有校验器。
- 调用旧通用入口得到VALIDATED_LOCAL_ONLY，只能说明旧检查义务通过，**不算M2材料语义验收**。未来M2能力路径必须显式调用新增材料入口并核精确已接收修订；旧消费者只支持M1则保持拒绝M2，不以optional字段可解析就放行运行。
- 特别防止旧消费路径漏拦：当前M1 capabilities不检查input_bindings，单独加Schema字段可能让旧核心忽略新映射。建议共享层拒绝本材料子集根节点的非null映射（包括空数组），下游非null映射则严格核源节点/等待/模型；缺省/null继续原路。正式S-COMPAT必须从真实M1入口核拒绝，不能仅测试新增材料入口。如果必须改contract_adapter.py才能满足拒绝要求，应停在D02，重新取得范围批准，不能扩大§5白名单或先发有漏拦的增量。
- 这样保留`test_p1_semantics.py:31–34/234–248`中真实旧类型测试及opaque wait记录；`tests/runtime_m1/test_contract_gate.py:38–55`原multi-node/wait仍应CAPABILITY_UNSUPPORTED。不能改这些旧测试期待来迎合“所有wait立即严格化”。以上是实施准备建议，**不是已接收C/T的改写或声明现有函数已支持它**。

#### 兼容 / 拒绝矩阵

| 消费者与输入 | 共享检查 / M2追加检查 | 运行结论与回归义务 |
|---|---|---|
| 旧M1包，无新增字段，使用旧消费者 | 原七字段、原Node required、原完整根输入与P1/P2不变 | 原M1行为保留；本轮只读源码定位，不借历史PR数量当新测试 |
| 增量共享validator + 旧M1；根缺省/null映射 | 可选/null仅增量表达，根仍完整模型校验；原映射缺省语义不变 | 不默认授M2能力；坏根仍拒绝 |
| 空数组或任意新映射交旧根消费者 | 浅层形状即使通过也不证明其消费语义 | 没有明确支持就拒绝/保持未支持，不能归入缺省/null兼容正例 |
| 旧共享validator读含input_bindings的新投影 | 旧Node additionalProperties=false，拒绝未知键 | 不删除映射“降级生成”来躲拒绝 |
| M2下游映射缺省/null/空/一项/三项或闭包非法 | 新材料语义入口必须拒绝，不依赖原Schema有无minItems | 不注册、不启用、不创建M2 Case；下游完整性不可降级 |
| 共享增量静态通过，但仍用当前M1核心 | 只通过共享检查，不表示core具备两节点/等待/A/B | 原capabilities仍拒绝；下一张共享卡不改运行限制 |
| 未来M2消费者、同名profile但未接收精确摘要/只支持旧无A/B版本 | `m2-linear-material-v1`标签不是足够依据；全部所需共享/接口/实现/来源能力须共同匹配 | 缺支持拒绝，不回退resume、不接受仅A省略B |
| 未来M2正确字节/能力、仍缺来源真实性或提交期授权保证 | 静态通过不授信；材料入口与提交重验不成立 | 按C原错误优先级拒绝，不用本地hash自签生产来源 |
| 未来M2原证明过期但材料有效 / 材料自然失效 | 前者同claim A；后者A拒绝并要求显式受权B | 始终首次claim前、旧消费不变；查询/历史重放不续许可 |
| 未来M2已有attempt或定义/目标变化 | A/B窗口关闭；新定义另走版本与准入 | 不删attempt、不改旧Case绑定、不自动选最新版 |
| 未来M2二进制遇M1 version1旧库 | 存储版本与共享根版本分开；按C §7拒绝 | 不迁移、不重建。旧M1继续用旧库；M2旧行为回归用新version2隔离库 |

#### 版本记录与回退

建议未来新增**一个**文档记录`docs/runtime-core/shared-contract-revisions.md`（拟新增、当前不存在），由主控1维护；不新增可运行Schema/锁文件来成为第二权威。记录必须区分：

1. 原/新共享Schema及validator精确文件摘要、Schema `$id`/contract_version、接口/design版本及摘要、基线commit与测试输入摘要；新摘要只在真实产物产生后计算，**当前尚未取得**。
2. C/T已接收摘要、双方消费意见的精确报告摘要、主控接收记录及负责人决定；“源文档通过”与“共享实现通过”各自记录，正文不嵌自身hash制造循环。
3. WaitSpec的`material-wait-v1`、M2合成profile的`m2-linear-material-v1`、显式A/B支持的已验实现/Provider组合；实际能力检查绑定既有ProviderDescriptor.capabilities及受信宿主安装/版本证据，不让请求自报能力清单或摘要充当许可。新增能力字符串/宿主绑定载体若必需，由正式M2卡在已确认口径内精确锁定，当前不创造第二份包ABI。
4. M1请求摘要`rc0-m1-request-v1`保持；未来resume的`rc0-m2-resume-v1`与B的`rc0-m2-replace-v1`取C §5.4/§8.2；A不增摘要版本或幂等槽。存储候选version2、包/组件/Adapter/模型/规则版本各列，不能混用。
5. 旧→新影响清单、兼容/拒绝结果、具体批准范围及精确head。头或候选字节变化后旧批准不能自动沿用，主控只复核受影响项，不篡改旧收据。

回退建议：发布前失败保留候选/失败证据，不接收新组合；发布后须另获授权停新准入并回到上一**已接收的整套摘要组合**，不能只换Schema漏掉validator或接口。在途Case保持原绑定、材料/输入历史与幂等，能力或来源不可用时阻断，不能降级运行或复活wait。M2 version2库不能交旧M1二进制“回滚运行”；原库及sidecar保留，离线迁移另卡。Git回退也须按PR流程，不改公共历史。

## 4. 文件冲突与阻断清单

- 本卡唯一新文档与PR #26的完整文件清单无交集；本树原90份跟踪文件、9份固定输入及控制锁均受门禁保护。本卡不借相同HEAD判断其他树干净，也不清理其他树。
- 下一阶段共享最小白名单见§5，和本轮观测PR #26无交集。未来M2运行变化则与PR #26明确交叉：`src/runtime_core/service.py`、`src/runtime_core/synthetic_host.py`、`src/runtime_core/worker.py`。其他新增包宿主/Provider也是以后整合必须重查的消费点；**这里不读取未绑定运行候选、不给它签兼容结论**。
- C/T及W1/W2是只读固定材料，不因本文建议维护者或版本而改原字节；作者工具/已验包的源码与入口未随本卡交接，真实工作流生成/检查路径当前只能列为后续绑定缺口，不能猜一个命令称为“实际存在”。

| 阻断ID | 缺少的真实决定或保证 | 阻断哪层 / 交谁处理 |
|---|---|---|
| D01 | §2具名作者提案尚未成为实际工程会话绑定；Adapter生产作者未提供 | 阻断对应共享/Adapter代码assignment；主控1协调，总负责人确认 |
| D02 | 推荐DRAFT增量、共享新语义入口、唯一版本记录及旧消费者策略尚未接收 | 阻断共享正式落地卡；双主控复核后总负责人决定，不自行升级根常量 |
| D03 | 最小共享子集与完整G3/P1/P2权威闭包的边界尚待明确 | 阻断代码准入，不宣布#4/#5/#6整体完成；总负责人决定，现有P1/P2不削弱 |
| D04 | 真正来源新版本、当前权限及提交覆盖期的生产保证机制不可用 | 阻断生产来源接入；合成可做本机协议测试，不能替代生产保证 |
| D05 | 未来M2与WF2整合base、共享实现/接口/来源版本精确摘要尚未产生 | 阻断M2运行实现/生成包集成；主控1锁基线并复核交叉文件 |
| D06 | 本准备文档尚待主控1接收与原主控2独立复核 | 阻断本卡最终验收，不由准备作者自签或另建审查会话代替 |

这些是可明确决策的后续闸门，不是重开已通过的AB-R01/R1–R3/RPT-01，也不撤回已接收A/B边界。

## 5. 下一阶段共享落地卡草案（未发布、不是开工令）

### 5.1 草案范围与精确建议白名单

建议下一张卡只落共享静态形状/语义、原接口文档及修订记录，不做等待运行、来源Adapter、CLI或数据库。正式Issue编号、base、工程目录、维护会话及批准尚未取得，不能虚构。§2提案及D01–D03必须先解决。

| 路径 | 当前状态 / 未来允许增量 | 唯一维护候选 |
|---|---|---|
| `docs/architecture-track/contracts/authority-contract.schema.json` | 已有；仅SC01–SC03新增`$defs`及Node可选映射；原七字段/required及根常量不变 | §2共享作者 |
| `spikes/002-authority-contract/validator.py` | 已有；新增形状引用、嵌套依赖闭包与材料语义入口，保留原公共函数行为与P1检查 | 同一共享作者 |
| `spikes/002-authority-contract/test_m2_shared_shapes.py` | **拟新增，当前不存在**；独立形状/可选null/基础类型与旧字段保护反例 | 同一共享作者 |
| `spikes/002-authority-contract/test_m2_shared_semantics.py` | **拟新增，当前不存在**；真实公共入口的材料语义/闭包/消费导入路径及拒绝反例，测试夹具在本文件内 | 同一共享作者 |
| `docs/runtime-core/interfaces.md` | 已有；只维护SC04所列原章节和已接收范围，不新增平行运行协议 | 主控1候选 |
| `docs/runtime-core/design.md` | 已有；只补SC04职责/状态分层说明并引用接口，不复制字段表 | 主控1候选 |
| `docs/runtime-core/shared-contract-revisions.md` | **拟新增，当前不存在**；单一版本/摘要/接收/回退记录，不是新机器契约 | 主控1候选 |

一任务一写入者：正式卡如由同一工程作者物理落全部文件，主控1仍是接口口径维护/接收方；如分作者，则主控分成不重叠assignment并串行交接，不能在同一worktree并发写。这里建议文件范围不直接授予任何会话写权。

该草案**不允许修改**：authority_checks.py及migration_checks.py、迁移Schema、旧spike fixtures/测试、M1运行/CLI/测试、任何WF2文件、C/T、作者工具/已验包、依赖/CI/协作规则。需要其中任一文件，先报告影响/取得新白名单，不临时扩项。来源Adapter及M2运行后续落点沿C §4/§7、T §2原候选文件表，本卡不另发布那张代码卡。

### 5.2 最小RED→GREEN切片及实际消费验证

以下S编号只是本草案的验证切片，不是新Issue或本轮测试通过数。全部新测试**拟新增、尚未运行**；RED必须来自届时真实入口，不用本文文字检查冒充。

| 切片 | RED与负例义务 | GREEN / 可证明边界 |
|---|---|---|
| S-WAIT | 基线无WaitSpec；新测试调用共享shape及拟新增材料语义入口，缺键/额外键/错类型/错event_type/null/非法期限和合法非null期限分别覆盖 | 唯一Schema可表达C §3.1，语义检查冻结引用与闭包；合法期限只是共享可表示，M2仍未实现/不支持，不在此测试中建wait或声称单次消费已证 |
| S-MAP | 基线未知input_bindings应拒绝；缺省/null兼容、原required逐项删、M2下游0/1/3项、错父/重复slot/错freshness/嵌套缺依赖/模型不等分别为独立负例 | 旧P1原测试不改；新材料入口必须真调用原validate_projection和同一`$defs`，并核完整映射/模型；从原`contract_adapter.validator`导入路径调用同一入口作消费者烟测，不复制Schema |
| S-MATERIAL | 新shape入口覆盖普通MaterialEvent/ResumePayload与独立B意图；额外EvidenceRef键、错误Id/事件类型/布尔版本、意图字段层级错误逐项拒绝 | 证明四种机器表达及纯静态关系；带结构合法的错目标/错来源/版本样例留给后续C/T动态验收，不能把形状拒绝当来源真实性通过 |
| S-COMPAT | 原M1无标记图、opaque wait、多节点负例，P1/P2撤权/缺依赖及迁移引用不能被新语义重分类；新组合缺一摘要/能力不准宣称M2支持 | 原spike/M1入口回归和导入路径烟测通过才接受共享候选；当前M1核心仍拒绝M2。未来M2再验显式能力准入、当前权限和真实CLI，不把新共享入口等于core已调用 |
| S-INTERFACE | 对C/T逐项检查A共同提交、B独立权限/意图、历史/current分离、已有attempt排除；缺一条就文档拒收 | 原interfaces/design与唯一修订记录相符，主控1/主控2独立确认；A/B事务、竞争/清理结果只由后续M2 L1/L2实证 |

合成测试发布记录和TrustedContext必须由显式测试夹具准备，不由失败的validator自动造可信上下文。输入、authority记录和内容摘要要真实对应；做语义负例时重新构造合法外层发布关系，避免只触发外层摘要错误。预期码/摘要从C/T及独立规范预像取得，不调用被测实现反推答案。

### 5.3 实际存在的回归入口与未来入口分开

下列文件/符号在固定base已定位，**本轮不运行这些共享/运行回归**，只作为下阶段授权卡的验收要求。每个运行根和原输出由届时assignment明确绑定；两个spike分开跑，避免其同名模块混在一次pytest收集中。

| 既有命令 / 符号 | 作用与来源 |
|---|---|
| `python -B -m pytest spikes/002-authority-contract -q -p no:cacheprovider` | P1/P2/迁移及规范化回归。`test_p1_negative.py:45/127/170`、`test_p1_semantics.py:234/241/247`、`test_p2.py:154/245`反例保护真实公共入口 |
| `python -B -m pytest spikes/001-input-contract -q -p no:cacheprovider` | 既有输入合同回归；不能把材料新语义放入另一套输入协议绕过共享定义 |
| `python -B -m pytest tests/runtime_m1 -q -p no:cacheprovider` | 原M1真实CLI、旧请求摘要、权限/重放/存储/时效；`test_contract_gate.py:46/58`、`test_idempotency.py:11/35/53`、`test_transactions.py:89`及`test_cli_process.py:58/154` |
| `python -B tools/verify_runtime_m1.py --sandbox "$M1_RUN_ROOT" --scenario all --report "$M1_REPORT"` | 已有有界L2入口，参数在该文件main:388；需要全新本树隔离根及树外报告，不用本文假路径或已验根运行 |
| `python -B -m pytest tests/test_collaboration_docs.py -q -p no:cacheprovider` | 协作入口回归，仅检查该测试列明的文档，不覆盖本准备全文 |
| `python -B tools/audit_tree.py`与`git diff --check` | 仓库卫生/空白；审计只读跟踪文件，新增未跟踪文件须单独补扫 |

未来拟新增入口：`python -B -m pytest spikes/002-authority-contract/test_m2_shared_shapes.py spikes/002-authority-contract/test_m2_shared_semantics.py -q -p no:cacheprovider`。只有§5.1正式授权并实现后才能实跑；现在不存在，不宣称已通过。共享消费烟测不启动Executor/Store；它只能证明实际导入同一机器定义。

后续M2完整运行验收沿T §3.3/§4/§5：`tests/runtime_m2`及`tools/verify_runtime_m2.py`均是拟新增，当前不存在；原L1与A/B组、T01–T10不得省略。当前固定base也没有`tests/runtime_package`和`tools/verify_runtime_package.py`，这些是PR #26候选路径，只能由其原任务在受控材料下验收，本卡不搬来运行。

共享阶段回归会创建合成测试根，正式卡须先审读`tests/runtime_m1/fixtures.py:15–20/66–75`及M1验收器的根/报告/清理出口，真实记录本轮根和清理前证据；输出归档在删除树外。必要的外层留证检查器只放未来assignment批准的忽略目录，不能修改旧测试或补造已经清掉的历史。若所需证据无法在原出口取得，先解决留证边界，不冒称完整零残留。

## 6. 本准备回件验收映射与待决事项

### 6.1 对Issue验收逐项交证

| Issue验收义务 | 本件依据 / 已做与未做 |
|---|---|
| 固定输入、精确base、本机绑定、实际认领一致；缺来源显式列明 | §1；真实认领及9份固定输入复核、本机工作区门禁有原输出；未持有的工作流实现及生产来源在§4明列 |
| SC01–SC05唯一落点、具名作者提案、真实消费方、验证与停止条件 | §2–3、§5逐项提供；维护提案尚未变成代码派工，实际承担者接收是D01 |
| 机器定义/来源验证不混淆、SC04无第二协议、SC05区分版本/摘要 | SC03分层、SC04原章节、SC05记录与兼容矩阵；未来摘要尚未产生，未填写假值 |
| A/B、SC02兼容、EvidenceRef七字段、旧M1及P1/P2边界无降级 | SC01–SC05及§5切片；保留RPT-01校正字段、旧opaque wait类型回归和根缺省/null，不重新审已接收候选 |
| 后续草案有精确文件、RED→GREEN和真实消费要求；拟新增入口明确 | §5；只供后续授权，不另发代码Issue、不改共享/运行文件 |
| 文档引用/范围/脱敏、diff、audit取得真实结果 | 规定命令见§6.2；本文件最终字节、实跑结果和新文档补扫绑定在本机HANDOFF与独立收据，不用空tracked diff证明新文档没问题 |
| 主控1接收、原主控2独立复核、总负责人待决项清楚 | **尚未完成**。本节仅交回；不能由准备作者勾Issue完成，不能关闭#5/#8或宣称共享/M2实现 |

### 6.2 本轮验证口径

本卡为L1文档、范围及引用一致性检查；L2运行链、L3真人体验、L4生产验证不适用，也未通过。本会话只读源码/AST/JSON和固定材料，不运行M1/M2/WF2、Provider、核心CLI或SQLite业务实验。

入口规定的最终实跑命令为：

```sh
python -B .local/verify_readiness.py --mode document
python -B tools/verify_workspace.py --assignment .local/assignment.json
python -B tools/audit_tree.py
python -B -m pytest -q -p no:cacheprovider tests/test_collaboration_docs.py
git diff --check
```

开工已实测：prepare门禁通过；认领成功；document模式在缺文件时返回`PREPARATION_DOCUMENT_MISSING`，为预期结构红灯。默认Python缺pytest的失败原输出保留，改用本树忽略目录内独立Python 3.12.12 / pytest 8.4.2后协作基线8项通过；子进程固定同一解释器，不修改项目requirements或全局环境。最终检查在成稿后重跑，真实argv/退出码、未跟踪文档补扫、反例、固定输入与控制锁复验及文档最终SHA仅存本机回件；本段不预填尚未运行的“全部通过”。

本文件无旧版本可备份，首次成稿前确认不存在；后续修订先在本树忽略证据目录备份。只保留本卡自有材料，不清理WF2现场、其他树、历史失败或认领锁。只有单条认领评论是本轮获准远程写例外；完成后只交本机HANDOFF，不再发评论或改变Issue元数据。

### 6.3 复核记录与负责人待决项

| 对象 | 已有依据 / 当前结论 | 下一责任方 |
|---|---|---|
| C/T原A/B候选 | R1/R2/R3固定接收，双主控文档复核通过；不重开旧返修 | 保持原字节，不把接收扩大为实施 |
| 本准备回件 | 本会话成稿和L1自检交回；**主控1尚未接收** | 主控1按最终SHA核全文、边界、具名提案、版本及冲突 |
| 本回件工作流消费适配 | **原主控2尚未独立复核本回件**；旧R3不能挪作此次结论 | 主控1另行协调原主控2，准备作者不自动启动 |
| 共享最小子集/G3/P1/P2 | 整体冻结及子集代码边界未批准 | 总负责人明确是否接受§2/SC05/§5，并限定局部代码范围 |
| 来源Adapter与生产保证 | 本机候选承担者仅提议；生产作者/保证机制未提供 | 主控安排真实来源职责；无法提供则生产阻断 |
| 共享实现、M2实现、合并、版本发布 | 均未由本卡授权；未来精确摘要未取得 | 分别取真实交付与对应负责人批准，不自动连跳 |

交主控1的决定题：是否接受本准备范围；是否确认§2维护分工及实际工程会话；是否采用受控DRAFT增量和独立M2材料语义入口；如何限定其与G3/P1/P2关系；是否在后续授权卡接收§5文件/验证范围。没有真实批准，不建新树、不发布代码卡、不开始M2。
