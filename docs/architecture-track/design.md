# P1/P2 隔离设计

状态：DRAFT；署名：Laiqh。本设计仅作候选测试假设，生产选择仍待共同冻结。

## Module / Interface / Seam
- Schema Module：一个 `$defs` 文档，共享DefinitionRef/ObjectRef/EvidenceRef/AuthorityRef/Node/Projection/ProviderDescriptor/Admission/Grant/RevocationView/Checkpoint/MigrationRequest等格式。未知字段/版本拒绝，不复制到spike。
- ContractValidator Module：Interface为 `validate_projection(projection, authority, context)`、`check_consumption(request, authority, context)`、`check_migration(request, authority, context)`。返回仅本地验证结果，失败抛固定安全码。
- AuthorityReader Interface：`lookup(kind, ref, context)` 与 `current(kind, key, context)`；宿主在可信接入层认证后注入。两个Adapter：显式合成测试目录、不可用故障Adapter。请求永远不能选择或修改信任根。没有签发方法。
- 可信context提供当前范围与部署、时钟，必须独立于请求；synthetic context不能序列化成生产身份。validator不能防御已控制宿主进程的攻击者。
- CLI Module：只读请求文件、stdout结构化结果；默认缺生产AuthorityReader失败关闭，`--demo`才用内置合成夹具，无网络、无trust路径参数。

## 不变量
定义摘要算法sha256；候选规范化 `json-sort-utf8-int-v1`：UTF-8无BOM、对象键排序、无多余空白、不转义Unicode、数组保序，仅整数/字符串/bool/null/集合容器，整数限制IEEE安全整数。拒绝浮点、重复JSON键、NaN、无效Unicode；不做身份trim/Unicode规范化。此格式不是RFC8785，只用于当前候选受限元数据。所有引用绑定精确kind/namespace/id/version/digest，生命周期来自受信记录而非引用。

Projection由发布DefinitionResolver提供独立受信artifact，客户端投影必须全量相等且内容摘要/源定义绑定；不由核心手写生成流程。节点依赖图必须无环、无孤点孤终点问题；所有终止叶节点显式列入terminal_nodes；依赖引用闭包由受信发布记录解析，不执行规则语义。CODE/AI/HUMAN是执行类别，ACTION声明是受控动作要求，不把ACTION当可任意调用终端的executor。

准入精确绑定business/definition/projection/providers/范围。Grant精确绑定instance/deployment/namespace/消费scope/generation/admission，current ownership验证当前代际。每次check重新读受信view，不缓存许可；effective_at <= now < expires_at。撤销view必须完整、新鲜、无revision回退；trusted event先验issuer及scope，按精确引用和revision验证；本轮不实现流同步/影响扫描/恢复写入。恢复只能用新受信view，不能由请求传入restore=true。

迁移源Grant必须已撤回、目标当前Grant正确且代际提高；检查点绑定instance/source deployment/namespace/control revision/数据与去重台账证据；当前检查点引用不符、UNKNOWN/活动执行器/缺停止或fence证据均阻断。停止证明由受信控制Reader给出，本地只核对字段，不证明远程旧进程已停。

## 状态、副作用、恢复、观测
validator无持久状态变化；返回 VALIDATED_LOCAL_ONLY 或拒绝码，核心如何PAUSED/WAITING/技术故障属于后续映射。authority失联=after_backoff，补资料=after_input，结构/授权不符=never；不自动重试外部动作。唯一文件写为人工触发测试证据和工具产物，不存在业务写。重复纯函数无副作用。L1挂公开Interface，L2挂CLI子进程；L3人工、L4真实系统均未验证。

## 冻结缺口（不猜）
F1：生产身份/issuer目录/认证通道/授权范围管理者。
F2：兼容版本、候选规范化是否采用、跨语言测试向量、公开标识命名。
F3：投影编译器/依赖包正式发布、Provider代码验证及接口演化。
F4：撤销同步一致性/水位持久化/乱序恢复和撤销与动作放行事务竞争。
F5：消费权唯一权威、原子切换、旧执行器fence的真实证明与目标能力探测。
F6：幂等输入字段表、去重墓碑/保留期限、Checkpoint存储一致性与凭据重绑定。
F7：对象/事实/证据权限、留存和生产Provider实现，Rule/Action/Readback不在本地执行。
F8：双方逐项接受和被接受版本摘要、正式GO/SPEC/核心实现测试；当前均未完成。
