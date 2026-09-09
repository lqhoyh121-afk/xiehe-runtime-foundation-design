# 公司级本体建模与治理：开源候选调研

**核查日期：2026-09-09。** 仅查官方文档、GitHub 仓库、许可证和发布记录；没有安装、访问企业系统、读取凭据或进行集成测试。下述“适合本公司”“建议”是架构判断，不是厂商已交付的能力。

## 结论

**低成本首选：LinkML 管统一对象/字段契约，Git 管变更审批与版本，现有 Obsidian 管制度依据和解释。** 真需要复杂分类、公理推理时再用 Protégé；多人共同编审 OWL 时再评估 WebProtégé；确有“结构化事实的关联查询、历史版本与分支合并”需求时才引入 TerminusDB。它们不是四选一的同类数据库，更不是买一个就能自动运行 EAM/GPS/钉钉业务。

## 四个候选

> Protégé Desktop 与 WebProtégé 属于同一家族，但专业桌面建模和多人在线治理的使用方式、部署负担不同，因此分列。

| 候选 / 角色 | 对新能源运维公司的适用点（建议） | 官方支持的建模与治理能力 | 许可证、发布/维护信号 | 关键边界与选型判断 |
|---|---|---|---|---|
| **LinkML**：模型语言与工具链，不是知识图谱服务器。[1] | 先统一“场站、设备、人员角色、车辆、缺陷、证书”等对象及字段，让 EAM、GPS、钉钉接头有共同的数据契约。 | YAML 编写 schema、数据校验；生成 JSON Schema、Python/Pydantic、SQL、OWL、文档等；官方明确推荐 Git 版本管理、变更治理和发布流程。[10][13][14] | **Apache-2.0**。[21] GitHub Latest 为 **v1.11.1，2026-05-20**；发布说明披露 v1.11.0 打包错误并从 PyPI 撤回，不能忽略版本说明。[6] | **优先选。** 治理靠团队评审流程配合，不是自带公司审批门户；生成模型不等于生成 EAM 连接器。OWL 转换存在开放世界/封闭世界语义差异，不能承诺无损互转。[19] |
| **Protégé Desktop**：专业 OWL 本体编辑器。[2] | 给少数领域专家梳理设备分类、概念关系和逻辑约束；适合需要解释“为什么归入这类设备/事件”的模型。 | 支持 OWL 2、本体开发、推理/查询和插件扩展；是本地建模工具。[2][16] | **BSD-2-Clause**，仓库明确声明。[2] 官方分发仓库 Latest 为 **5.6.9，2026-03-07**，有 Java 兼容与缺陷修复记录。[7] | **按需使用。** 不宜要求全公司员工直接编辑 OWL；文件协作、模型发布审批需要另外安排。逻辑一致性检查不能替代“证书齐不齐、工单是否真保存”的业务核验。 |
| **WebProtégé**：多人在线 OWL 编审环境。[3] | 安全、生产、设备、信息化共同讨论术语、分类与关系时，比让所有人改 YAML 更合适；业务人员参与模型治理，不等于操作业务单据。 | OWL 2 编辑、完整变更历史、共享权限、讨论、关注与通知；旧版发布说明有多语言标签及主/次显示语言能力，但不据此承诺完整中文界面。[3][15] | 旧主仓库许可证为 **BSD 两条款**。[12] 旧仓库 Latest **4.0.2，2020-07-31**；README 明确开发已迁往微服务仓库，后端可见 **2026-07-27** 的功能提交及 5.0.17 版本更新，不能只看旧仓库就判定停更。[3][15][17] | **有专人治理时再选。** 下一代文档列出多个服务及 MongoDB、Pulsar、MinIO、Keycloak 等依赖，维护负担高于桌面/文件方案；需逐项核查实际组件版本与许可证，不把旧 WAR、云端服务和新架构视作同一发行物。[9] |
| **TerminusDB**：有 schema 的版本化文档/图数据库。[4] | 将“某设备归哪座场站、某时点谁任负责人、记录如何变化”做成可查询的结构化事实层；不是只写术语表时就必须引入。 | JSON/JSON-LD 文档关联、schema 约束；commit、diff、历史查询、push/pull/clone；提供 REST、GraphQL、WOQL。[4][20] | **Apache-2.0 核心**。[22] GitHub Latest 为 **v12.0.7，2026-08-10**；官方说明已由新维护者接手，需重新审视维护与支持边界。[4][8] | **第二阶段候选。** 使用专有 schema/WOQL 与封闭世界 RDF 语义，不是任意 OWL 本体的通用推理器。[5][20] 官方另推 DFRNT Studio/托管体验；不能把网页展示的全部可视化能力都算进开源核心或默认免费自托管范围。[5] |

**维护信号的口径：** 发布日期取 GitHub 页面中的时间字段，日期按 UTC；“Latest”是本次查询时的标签。新提交、发布或测试记录只能证明活动信号，不能证明满足公司级安全、可用性、性能或兼容要求。WebProtégé 的新后端版本号也不代表整套系统有同版本的一键发行包。

## 必须拆开的五层

以下为建议的责任边界，避免把知识图谱当成状态机：

| 层 | 应保存/负责什么 | 不应混入什么 |
|---|---|---|
| **模型定义** | 类、字段、关系、枚举、中文解释、稳定标识、规则依据、模型版本；可用 LinkML 或 OWL。 | 不保存“某笔工单执行到第几步”的唯一状态。 |
| **来源事实** | EAM 单号/设备编码、GPS 设备号与观测时间、钉钉稳定用户标识；保留来源、采集时间、原始证据和映射版本。 | 不因两条记录同名就自动认定同一人/设备；不把过时 GPS 数据当实时事实。 |
| **Case 状态** | 每笔业务的当前节点、等待资料、审批结果、重试与失败原因，进入事务化运行台账。 | 不由聊天上下文、图上连线或通知是否送达决定业务完成。 |
| **动作门禁** | 身份与授权、材料齐备、前置状态、幂等键、资源互斥、执行接头。 | 模型中的 `Action` 类型或“允许整改”关系不自动获得 EAM 写权限。 |
| **独立核验** | 按确切外部单号回读字段、附件和状态，核对证据后再推进终态。 | schema 校验通过、API 返回成功、Agent 自述成功都不能单独替代业务核验。 |

Protégé 的推理与 LinkML 的数据校验也不是同一回事：LinkML 官方特别说明 OWL 使用开放世界语义，OWL 表达可能不足以完成数据校验。[19] **即使模型完全一致，也无法凭空证明现场整改已经发生。**

## 最小成本推进路径（建议，不是实施计划）

1. **保留现状，不重建巨型图。** `[LOCAL_WIKI]` 的 raw/wiki/output 三层继续保存原材料、编译后的知识和阅读产物。仅在需要机器契约时增加一份受版本控制的模型源；Wiki 展示或链接它，避免两份定义分别修改。
2. **先做共同词典和标识映射。** 选择一条已有业务，例如证书到期或车辆离线提醒；只定义它实际涉及的对象。每个术语明确中文名、含义/反例、业务负责人、字段单位、来源系统和映射规则。稳定机器标识与中文显示名称分离；人员姓名不能代替身份键。GPS 坐标系、时间戳和新鲜度规则也要明确。
3. **用轻量治理代替“上治理平台”。** 业务负责人审语义，技术负责人审字段与兼容性；通过变更请求、版本标签、废弃期和正反例数据管理演进。LinkML 官方已有协作治理与语义化发布指导，可借鉴机制，不必照搬公开开源社区的数据公开政策。[11][13]
4. **复用现有接头，但逐个重验。** 根据已提供的背景，EAM 仍走授权浏览器、钉钉仍走现有 CLI，GPS 沿合法现有通道；外面加模型映射和输出校验，而非先替换整个工具栈。本轮官方资料**未核得适配该公司私有 EAM/GPS/钉钉环境的开箱即用连接器**；不能承诺“100% 复用”。SSO 会话、租户/场站权限、同人映射、分页与失败回读仍要另行验证。
5. **需求出现再升级。** 真需要多人 OWL 共编才评估 WebProtégé；跨业务历史关联确实困难才考虑 TerminusDB。LinkML 确有 TerminusDB JSON-LD schema 生成器，文档声明面向 v10+ 文档接口；可减少重复定义，但 v12、具体模型特性及迁移仍需验证，不能将“存在生成器”写成“已集成成功”。[18]

**成本判断：** 以上开源核心许可证不是商业支持、云服务或运维成本的报价；本报告不提供未经核实的价格。“低成本”指优先复用文件、Git、Wiki 与现有接头，少引入常驻服务，并明确谁负责维护。公司模型、生产数据和人员/GPS 信息不因使用开源软件而应公开；外部托管服务需另审访问控制、数据出境与保留策略。

**关于“开源 Palantir”：** 本轮不将任何候选称为完整替代。TerminusDB 最接近可组合的版本化语义事实底座，但其数据库能力和另行提供的 Studio 体验不能证明已经具备公司所需的业务动作、审批、私有连接器和独立验收。[4][5] 当前更合理的是“明确模型 + 保留来源 + 独立运行台账与受控动作”，而不是以一个大平台统包这些责任。

## 核查限制

GitHub 匿名 API 返回 403 rate limit exceeded，已改查官方网页及原始 HTML 时间字段；没有使用凭据绕过。个别旧页面失效，已改用当前官网或仓库文档。本文完成的是来源与边界核查，**不是安装验证、端到端测试、安全认证或采购尽调**。

## Sources

[1] https://github.com/linkml/linkml
[2] https://github.com/protegeproject/protege
[3] https://github.com/protegeproject/webprotege
[4] https://github.com/terminusdb/terminusdb
[5] https://terminusdb.org
[6] https://github.com/linkml/linkml/releases/tag/v1.11.1
[7] https://github.com/protegeproject/protege-distribution/releases/tag/protege-5.6.9
[8] https://github.com/terminusdb/terminusdb/releases/tag/v12.0.7
[9] https://github.com/protegeproject/webprotege-next-gen/wiki/WebProt%C3%A9g%C3%A9-Next-Generation-Overview
[10] https://linkml.io/linkml
[11] https://linkml.io/linkml/developers/manage-releases.html
[12] https://raw.githubusercontent.com/protegeproject/webprotege/master/license.txt
[13] https://linkml.io/linkml/howtos/collaborative-development.html
[14] https://linkml.io/linkml/generators/index.html
[15] https://github.com/protegeproject/webprotege/releases
[16] https://protege.stanford.edu
[17] https://github.com/protegeproject/webprotege-backend-service/commits/main
[18] https://linkml.io/linkml/generators/terminusdb.html
[19] https://linkml.io/linkml/generators/owl.html
[20] https://terminusdb.org/docs/schema-reference-guide
[21] https://raw.githubusercontent.com/linkml/linkml/main/LICENSE
[22] https://raw.githubusercontent.com/terminusdb/terminusdb/main/LICENSE
