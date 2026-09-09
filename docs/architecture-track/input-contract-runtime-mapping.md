# 输入定义→调度核心：可执行候选映射

署名：Laiqh

状态：候选接口，尚未双方冻结；本轮只实现`spikes/001-input-contract`中的隔离观测契约，未实现通用业务包SDK或生产Provider。不是完整本体格式的新权威。

## 1. 单一权威与所有权

正式模型定义由整体模型模块发布，SourceAdapter只持有字段映射。DataProvider消费模型与对象目录/事实源，生成节点输入快照；核心只接收已验证引用，不知道Excel列号或SQL表结构。新业务处理代码引用模型/规则，不在Skill正文重复定义字段和推进状态。

本轮实际演示的一份model.json同时约束Excel和SQLite；objects.json是实例清单，不是第二份类型定义；business.json绑定模型摘要及合成规则。该读数示例不代表出车、隐患或两票规则。

## 2. 已实现接缝与待接线字段

| 核心接口概念 | 本轮可执行候选 | 正式化时还需补充 |
|---|---|---|
| definition_ref中的输入契约引用 | 模型id/version/sha256，expected_model_ref与内容核对 | 已发布定义Resolver、撤销与批准身份，不接受调用者自行批准 |
| input_snapshot_ref | Snapshot.snapshot_id及内容寻址快照 | 受权限保护的Evidence/Fact引用解析；不把本机绝对路径作为远程协议 |
| facts/对象引用 | 观测记录object_ref与对象目录digest | 正式稳定身份、权限、关系、权威来源解析 |
| 输入契约校验Provider | load_snapshot：结构→身份→时效→整批接受或拒绝 | 通用模型扩展、来源授权、刷新/回源策略、撤销门禁 |
| CODE执行Provider | business.evaluate，完全无Excel/SQLite读取分支 | 注册受信handler、节点权限、生产规则依赖、结果契约 |
| 节点证据 | 模型、目录、来源摘要、validated_at、标准记录、结果 | 原始行定位/原件保管策略、脱敏、保留期限及访问控制 |
| ACTION/ReadbackProvider | 未实现；本地结果文件不能替代 | 沿用调度核心动作意图与独立回读，不能直接标外部完成 |

## 3. 规范化输入的责任

来源字段映射属于接头；类型/单位/必填属于模型；身份匹配属于对象解析；新鲜度要求属于获准输入/规则契约；时效计算与拒绝由Provider执行。读取时生成独立快照，写入前仍要按规则重验，不能因快照存在永久有效。

关键标识原文保留，不去空格、不猜同名。合成样例使用同一对象ID，因此本轮只证明目录存在性，不声称跨系统身份归一已完成。

## 4. 单笔输入结果的候选语义

- VALIDATED：全批输入满足绑定模型及本次时钟策略，返回不可变快照引用。
- REJECTED：结构/单位/身份等不合格，无节点执行结果。
- REFRESH_REQUIRED/WAITING：正式版针对实时事实；本轮用STALE_FACT显式拒绝，没有实现回源。
- PROVIDER_UNAVAILABLE：正式版故障协议；本轮文件不可读返回SOURCE_READ_FAILED。

错误码不能自动映射为业务FAILED；交给批准流程的异常路由决定等待、补充或技术失败。拒绝也不能因Agent提出改模型就自动重试通过。

## 5. 技术证据与限制

真实运行入口：`python -B demo.py --output-dir 一个不存在的目录`，在spike目录启动。它真实创建合成xlsx/SQLite，再分别启动同一cli.py，独立读回result与snapshot，检查语义等价、固定预期、来源区分、同一模型和处理器未变、输入文件未改。

证据：`../../spikes/001-input-contract/evidence/最终候选 run-2/summary.json`与`tests-final-run.json`。时钟2030年只是标明的测试夹具，不是当前时间或现场数据。

正式化前仍需完成共同契约冻结、正式SPEC/准入、通用节点/模型Schema、包准入绑定、权限边界与调度接线。本文件不批准调度分支进入实现，也不升级总体项目验收。
