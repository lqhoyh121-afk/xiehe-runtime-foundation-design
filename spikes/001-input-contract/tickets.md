# 输入契约验证任务
本地SPIKE，不代替总体任务卡或调度分支状态。

## IC-1 表格和SQLite使用同一模型及处理器
Blocked by: None。验证L1/L2。入口：pytest与demo.py。证据：测试报告、两个来源的标准快照、固定预期判定。无人工步骤/外部写入。合成数据可重复生成到新目录；源文件只读。
- [x] 两接头实读；同一处理器产生等价结果，来源可追溯。证据：evidence/最终候选 run-2/summary.json。

## IC-2 异常拒绝与版本/快照约束
Blocked by: IC-1。验证L1/L2。入口：pytest、cli.py。缺失、未知/重复对象、时间、类型、单位、模型变更和快照损坏必须可观察拒绝。无生产操作。
- [x] 对抗用例及重放通过；未合格数据无结果输出。证据：evidence/tests-final.xml、tests-final-run.json；仅本地L1/L2。

## IC-3 独立验证与契约交接
Blocked by: IC-2。验证L2。入口：新目录中的demo.py/CLI；不冒充干净机器发行。审阅源码与行为；记录限制及调度映射，无Git提交。
- [x] 最终CLI真跑、依赖版本和证据记录、可交接结论。证据：evidence/demo-final-review-run.json、REVIEW.md；43项测试见evidence/tests-final-review.xml。只完成本片段，不批准正式核心实现。
