# WF1实现说明
署名：Laiqh。承接已接收WF0摘要5010ffd9fc7c08fa175211671e1b5cf5e61c912bd26c7e8a4a6aabe1fce8ce72。不是新增大任务或共享协议。

## 固定接缝与实现约束
- CLI入口tools/workflow_author.py：init/check；合成入口tools/workflow_author_synthetic.py：prepare/check。报告0.1.0，status退出码固定0/2/3/4/5/64/1，runtime_verified和production_authorized恒false。
- contracts模块集中作者键/默认草稿/profile/诊断；不复制共享Schema。authority_bridge从仓库固定路径用隔离模块名载入唯一validator；不接受用户模块路径，不占用全局validator模块名。
- safety模块产生只读有界快照（单文件2MB，总256文件/20MB）；拒绝链接/重解析/特殊文件/非法编码；清单只引用缓存快照，不重读绕预算。
- generator模块只往显式新建/空目录排他写；持有目标互斥，逐文件所有权记录。失败清理仅本次未变文件，冲突文件保留。kill残留须人工核验或换新目标，不擅自续跑。
- checker模块按安全→作者结构→共享外形/图→组件关联与profile→源码静态边界→权威元数据校验聚合。已知错误优先草稿，草稿优先来源未完成；所有必需项通过才能PASSED。不执行组件/测试/模型/规则。
- synthetic_host只在显式prepare构建WF0§5.1的逐条固定记录（8个非runtime记录及其runtime闭包、原始model长度边界和rule predicate）；check仅读取、严格校验、注入固定测试context。同一个check_package API消费Reader，普通CLI无透明fallback。材料与包必须分离。
- 检查器仍不import/collect/执行作者测试，但对每个已声明测试文件静态要求至少一个实质性的顶层`test_*`或`Test*`.`test_*`入口；helper、空/`pass`、无法识别的动态收集不能报绿，留给独立pytest/人工门禁。
- text报告与JSON使用同一diagnostics：逐项显示安全file/pointer/line/column、source_code（存在时）、message和remediation，不显示绝对路径、原输入、秘密或traceback。
- Skill和指南说明独立组件测试与静态通过分开；I3/I4/I6完整表示、Provider运行绑定、权限与核心运行仍未验证。

## 测试映射
B切片：init真实CLI及非覆盖/并发/失败清理。C切片：check_package全字段边界、敏感/执行/路径/资源预算。D切片：prepare与显式check、来源错误原码、真实CLI退出码/格式/不同cwd；真实repo Skill及生成说明链接。组件测试通过作者明确独立运行；黄金text规范化预期固定，不从检查器反推。自测最高L1/L2；另一作者L3留主控。

## 状态与恢复
CREATED仅生成草稿；DRAFT需要作者补全；REJECTED为确定不合格；INCOMPLETE为材料不可得；PASSED只表示声明的静态profile；CONFLICT不覆盖；USAGE_ERROR不回显参数；INTERNAL_ERROR不泄漏异常。check无持久业务状态。所有工具无网络/安装/生产副作用。实施/红绿记录留忽略目录；终版实跑见[验证摘要](wf1-verification.md)。
