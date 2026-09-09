# 可复用、渐进生长的业务对象图：补充研究结论

## 核心判断

目标不是再选一个“大本体平台”，而是：**一个人、一座场站、一个设备只建立一次稳定身份；新业务增加关系、角色、切面和状态，不再造一套基础对象。**

车辆业务先引入 `Person / Vehicle / Station`；两票业务复用同一个 `Person / Station`，再增加自己的票据对象、角色与约束。这里的“两票具体类型、字段和状态”仍需按公司制度定义，不从工具样例照搬。

## 最相关的可借鉴点

| 来源 | 真正值得拿走的模式 | 不能误认为已解决的部分 |
|---|---|---|
| **FINOS Legend** | 业务模型与物理数据源分离，项目间复用模型依赖，模型代码化并纳入变更治理。可用于理解“公共核心模型＋业务扩展模块”。[1–2] | 不自动完成 EAM/EHR/钉钉同人、同站的身份对齐；已有 Obsidian 名称和双链也不会自动成为稳定对象标识。 |
| **Eclipse SAMM** | 一份可复用 Aspect Model 描述一个切面的结构、单位和约束；同类切面可用于不同孪生对象。**切面模型与当前运行值分离。**[3] | 不必把一个 Person 拆成多个身份；角色/切面应挂在共同身份上。SAMM 是可借鉴的表达与工具体系，不要求立刻采用全部运行栈。 |
| **AAS / BaSyx** | 在对象/子模型上暴露状态与操作，将具体操作委托给外部执行器，适合“孪生对象是入口，原业务系统仍执行”。[4] | 有操作入口不等于有审批、幂等或回读确认。所查 BaSyx 委托实现只支持 HTTP，且要求特定输入输出封装。[5] |
| **OpenSPG** | Schema、实体归一、构建和规则推理可组合成逐步完善的图。[6] | 不能替代公司自身的身份与模式治理；当前需求尚不足以证明必须引入该引擎。 |

## 落在车辆→两票复用上的最小规则

1. **身份稳定，来源可追溯。** 公司级对象 ID 不依赖姓名、手机号、显示名称或某业务表行号；维护“公司对象 ID ↔ 来源系统＋原始主键”。同名不自动合并，疑似重复进入确认流程。
2. **角色放在业务上下文，不变成新的人员类型。** 同一个 `Person` 在一张出车单里是驾驶人，在一张票据里可以是工作负责人；角色关联具体业务记录、场站或组织，并按需要带有效期。不要分别建立互不相认的“车辆人员”“两票人员”。
3. **核心小，扩展分模块。** 公共核心定义 Person/Station 等身份与基础关联；车辆模块拥有 Vehicle、出车记录及自身状态；两票模块拥有票据与票据角色。业务模块依赖核心，而核心不反向依赖每项业务。新增模块先查能否复用；只有语义确实不同才新建类型。
4. **孪生状态是带来源和时间的投影。** 车辆位置、车况、出车占用是不同切面，不能压成一个含糊的“状态”。保存源记录、观测/更新时间及必要历史；人员的“在岗”“持证有效”“有资格担任某票据角色”同样要区分，不相互替代。
5. **生长需要轻量变更门槛。** 给类型/属性/关系设负责人和版本；新增之前检查同义项，合并保留旧 ID 重定向或映射，破坏性变更有迁移规则。判断复用成功的验收点是：**第二个业务引用同一人、同一站，没有复制基础对象，同时保留各自角色和状态。**
6. **可迁移靠契约和导出，不靠承诺某数据库。** 至少能导出对象、关系、来源映射、模式版本与状态历史，并保留稳定 ID。Obsidian 可继续记录定义和证据；机器可读模式、实例图和状态投影需有明确边界，不要求它们初期就是多个独立服务。

以上为根据一手资料提出的设计建议，**不是已经实现或验证的平台能力**。本次未安装、未运行任何产品，未对公司数据做身份合并或系统写回。

## 许可证与权威来源

- **Legend：Apache-2.0。** [1] 官方总览：<https://legend.finos.org/docs/overview/legend-overview>；[2] 模型 Dependencies：<https://legend.finos.org/docs/overview/legend-features>；许可证/组件：<https://github.com/finos/legend>。
- **SAMM 仓库、ESMF SDK：MPL-2.0。** [3] 规范说明切面模型不包含实际运行数据：<https://eclipse-esmf.github.io/samm-specification/snapshot/index.html>；许可证：<https://github.com/eclipse-esmf/esmf-semantic-aspect-meta-model/blob/main/LICENSE.txt>、<https://github.com/eclipse-esmf/esmf-sdk>。snapshot 是演进文档，不作稳定版本承诺。
- **AAS API 规范：CC-BY-4.0；BaSyx Java V2 Server SDK：MIT。** [4] <https://wiki.basyx.org/en/latest/content/concepts/use_cases/aas_operations.html>；[5] <https://wiki.basyx.org/en/latest/content/user_documentation/basyx_components/v2/submodel_repository/features/operation-delegation.html>；许可证分别见 <https://github.com/admin-shell-io/aas-specs-api>、<https://raw.githubusercontent.com/eclipse-basyx/basyx-java-server-sdk/main/README.md>。
- **OpenSPG：Apache-2.0。** [6] 官方原始 README：<https://raw.githubusercontent.com/OpenSPG/openspg/master/README.md>。

核查边界：只读核查官方资料，没有产品实测。GitHub 匿名 API 限流后改读官方页面/原始 README；一次 SAMM 抽取返回错误站点正文，已弃用并直接读取原 URL 核实。仅创建/更新本报告，未安装软件或修改业务数据。
