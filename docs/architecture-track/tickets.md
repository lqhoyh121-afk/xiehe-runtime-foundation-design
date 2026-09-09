# Tickets: P1/P2候选隔离验证

状态：DRAFT。用户已授权按P1/P2范围持续完成；卡粒度仅隔离执行安排，不代表批准生产设计。任务系统not configured；无Git提交。

## AC-1 P1：解析投影或明确拒绝
Blocked by：None。Required verification：L1。
What to build：单一Schema和公开validator，对精确引用/依赖闭包/节点图/Provider做完整本地检查。
Real entry：pytest公开Interface。
Business evidence：无生产；evidence/ac1-red与green日志/XML，固定合成黄金输入与变异反例。
Human steps：本地无；正式格式及Provider目录待双方冻结。
Recovery/idempotency：重复只读；不可核验拒绝。Cleanup：仅隔离临时文件。
- [ ] Schema字段、正常投影、版本/依赖/图/未知Provider反例通过。

## AC-2 P2：准入及实例消费权检查
Blocked by：AC-1。Required verification：L1。
What to build：独立宿主AuthorityReader接缝，对伪造准入、复制实例、撤销/过期/同步缺口失败关闭。
Real entry：pytest check_consumption。
Business evidence：无生产；evidence/ac2红绿及回归。
Human steps：真实权威/信任传输待定，不签发测试token。
Recovery/idempotency：每次重查当前授权，重复不扩权。Cleanup：无外部写。
- [ ] admission/version/providers/scope及current grant绑定完整，拒绝客户端自报批准。
- [ ] 撤销/有效期/水位/失联/伪造事件测试通过。

## AC-3 P2：迁移恢复核验和交付入口
Blocked by：AC-2。Required verification：L1、L2。
What to build：检查点、撤回旧权/停止旧执行器、目标能力、命名空间/代际；CLI无生产信任时拒绝。
Real entry：python -B cli.py --demo；真实子进程文件输入。
Business evidence：无生产；evidence/ac3红绿、最终pytest XML及CLI stdout。
Human steps：双方freeze待批准，人工体验未验证。
Recovery/idempotency：重复CLI不改输入；无认证Adapter失败关闭；迁移只检查不执行。
Cleanup：临时目录仅spike下，由测试清理，测试证据保留。
- [ ] 迁移正常/旧权未撤/旧执行器未停/过时检查点/缺能力/UNKNOWN反例通过。
- [ ] 最终全套、真实CLI、保护范围核查、双轴review、状态交接齐全。

## FREEZE（不执行）
Blocked by：AC-1/2/3及双方明确批准。Required verification：双方review和正式准入。
- [ ] 完成design.md F1–F8，固定共同接受版本摘要后才讨论核心实现。
