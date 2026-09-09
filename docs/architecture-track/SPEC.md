# P1/P2 可执行契约候选规格

状态：DRAFT；署名：Laiqh。限架构侧隔离交付，非共同批准。

## 问题与解决方案
调度v0.2仍不能按机器格式核查引用、投影、Provider及准入/消费权。交付一个共享Schema文档、只读本地validator和反例，供后续核心复用判据。不引入第二套本体、调度器或权限服务器。

## 用户故事 / 范围
1. 架构方能用单一引用定义锁定kind/namespace/id/version/content digest，不把摘要当批准。
2. 核心方能拒绝重复节点、缺依赖、环、未列入依赖闭包的契约及未知Provider。
3. 节点投影包含执行类别、输入输出、规则/等待/验收引用、Provider、资源、超时重试和结束条件。
4. 注册方必须经独立受信Resolver获取发布投影和Provider记录；请求中的approved或文件存在不授信。
5. 实例方持久instance_id与deployment_id、worker_session_id分离；复制请求默认没有消费权。
6. 每次消费检查准入、部署范围、授权代际、有效期、撤销水位和完整性，依赖不可核验失败关闭。
7. 迁移恢复检查当前检查点、原消费权撤回、旧执行器停止/有效fence、目标能力及命名空间；不实际迁移。
8. 接手方可真实启动离线CLI及测试，结果明确标示SYNTHETIC/DRAFT，不被当作生产通行证。

## 已确认边界与拷问记录
本轮用户已明确继续至真实测试和交接，六个验收问题已有答案：终点=候选文件和本地拒绝证据；入口=隔离CLI/pytest；人必须批准=正式身份、可信通道与双方冻结；外部成功证据=本轮不适用；重跑=只读且不发权、不消费、不改Case；拒绝=引用/图/信任/时效/撤销/迁移证据不足。只在该隔离范围执行，不把用户继续授权记成双方设计批准。真实权威归属未决冻结，见design.md。

## 实现决定
单个JSON Schema 2020-12文件是共享字段唯一候选。Python接缝只提供检查结果和错误码，不提供签发、签名、安装、动态代码加载或网络。仅内置测试Adapter由宿主构造；CLI不接受trust文件、issuer、公钥或自报权限参数。测试时钟2030明确为夹具。正式受信通道必须替换该Adapter。

## 测试决定
期望取自runtime-core/interfaces.md §1/2.1/3.1及v02-alignment §2/3的拒绝义务，不调用validator生成测试正确答案。正常投影+变异版本、图、未知Provider、伪造准入、复制实例、过期、撤销、迁移停止证明构成独立反例。每个垂直卡先红后绿；不用001已通过43测试冒充本轮测试。

## 验证契约
- required levels：L1契约/反例；L2真实子进程/文件CLI。没有生产业务闭环，不要求L4。
- real entry：spike目录 `python -B cli.py --demo`；`python -B -m pytest -p no:cacheprovider -q`。
- real fixture：明确SYNTHETIC的固定测试发布记录和实例；不读取账号/凭据。
- assertions：正常候选通过本地判据；列明错误的反例拒绝；CLI结果含DRAFT和synthetic_only、不返回生产授权。
- external readback：N/A，无业务写入；证据读取文件与子进程输出。
- human steps：共同冻结/真实权威决策未执行；不代批。
- recovery/idempotency：相同输入重复执行输出相同，输入文件不修改；authority不可用、同步缺口失败关闭。不存在事务、队列、幂等台账或网络超时恢复实现。
- cleanup：临时文件仅在隔离spike测试目录；保留红绿日志；不改根状态和001证据。
- evidence：spike/evidence测试日志/XML/CLI结果；架构侧.dev-flow保存基线、状态、review。

## 非目标与验收标准
不实现运行核心、认证服务、跨机选主、生产fencing、签发/自签自验、模型/事实通用校验或外部写回。所有命名/规范化格式是DRAFT候选。验收需Schema自检、P1/P2反例、本地真实入口、完整测试输出、保护范围哈希比对与交接齐全。任务系统：not configured；Git不存在，不初始化、不提交。
