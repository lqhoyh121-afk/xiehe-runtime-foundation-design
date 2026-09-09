# 项目任务总控
署名：Laiqh

## 总目标
建立独立于Agent、可安装可迁移的企业业务底座。知识有依据，本体共享身份和语义，业务包复用能力，输入输出可换接头，运行状态可恢复可审计。新增第二/第三业务不重造调度器、不重复建立人员场站；生产写回须独立回读。

## 架构
知识依据（现有Obsidian知识库）→受控模型候选/评审/发布→唯一模型和规则；来源Adapter→标准事实；业务包＋部署绑定→装配准入→调度运行→受控动作/独立回读→只读控制台。

整体候选：docs/architecture-track/assembly-architecture.md；调度候选：docs/runtime-core/interfaces.md（v0.2）；不另造第二份机器契约。

## 阶段依赖（不是执行状态表）
- G0 总目标/整体装配讨论；先经总负责人确认。
- G1 输入替换验证：继承spikes/001-input-contract。
- G2 P1/P2＋迁移候选：继承spikes/002-authority-contract；独立审阅与权威签发边界未完成。
- G3 共同冻结：依赖G0/G2及调度双方对齐，不因测试通过自动冻结。
- GA 装配准入；GA-V 两业务最小装配：依赖G3及隔离实施批准。
- G4 运行核心、G5 模型/身份/事实/规则、G6 业务包SDK及薄Skill：按G3接缝分工，先最小装配后完善。
- G5-K1 Obsidian知识关联/稳定ID/来源；G5-K2 知识→模型候选→评审→发布/影响分析，普通笔记不是已发布规则。不新建重复知识库，不自动改实际Vault。
- G6-S1 Skill规范/模板、代码/AI/人工分工、端口与验收检查器。
- G7 跨业务真实接头：依赖G4/G5/G6/GA；需授权沙箱。
- G8 安装诊断/备份迁移；G9 真实运行控制台；G10 最终干净环境及业务验收。

## 权威状态与闸门
执行状态只认[GitHub Issues](https://github.com/lqhoyh121-afk/xiehe-runtime-foundation-design/issues)，改动审阅只认PR。旧tickets/SPEC是基线参考，不再更新执行勾选；每项任务需Issue记录负责人、边界、依赖与验收。此文件只维护目标、架构、依赖、闸门和导航。

历史验收基线：输入43项、权威/迁移150项是本地合成测试，不是生产或完整独立审阅。架构仍DRAFT；缺P1/P2完整权威及双方冻结时禁止核心实现。签发者策略、分布式权威切换、远程停止真实性和生产Adapter均未验证。

总负责人lqhoyh121-afk批准合并/发布。首个协作试点仅文档链接检查，不改业务或规则；试点PR检查和审阅后等待负责人批准，再扩大并行。

## 执行入口（只做导航，不复制状态）
- [协作试点 #1](https://github.com/lqhoyh121-afk/xiehe-runtime-foundation-design/issues/1)
- G0/G1/G2/G3：Issues #2/#3/#4/#5；GA/GA-V/G4/G5：#6/#7/#8/#9。
- G5-K1/G5-K2/G6/G6-S1：#10/#11/#12/#13；G7/G8/G9/G10：#14/#15/#16/#17。
- [实际保护规则与局限](docs/collaboration/GOVERNANCE.md)。Issue记录细化/认领/验收，PR记录测试和审阅；历史tickets不再勾选。
