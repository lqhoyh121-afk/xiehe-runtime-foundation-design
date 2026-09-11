# WF1验证摘要

署名：Laiqh。状态：**实现方自测完成，候选待主控独立验收；不是主控已接受，也不是WF2开工。**

## 验证对象与边界

承接WF0已接收作者合同（SHA256 `5010ffd9fc7c08fa175211671e1b5cf5e61c912bd26c7e8a4a6aabe1fce8ce72`），只验证`single-code-output-v1`。未改共享Schema、核心、B线RC0、WF0或已安装Skill。所有命令使用任务指定同一Python 3.11.15解释器、Windows本机、独立测试目录；未安装依赖、访问业务系统或发起生产写入。

## 实际结果

| 独立进程/套件 | 实际结果 | 不夸大的结论 |
|---|---:|---|
| `python -B -m pytest tests/workflow_author -q -p no:cacheprovider` | 209通过、0失败、0错误、0跳过 | 作者工具L1/L2离线检查及CLI/组件分项自测通过；含R1/R2/R3返修回归 |
| `python -B -m pytest spikes/001-input-contract -q -p no:cacheprovider` | 101通过 | 输入合同旧回归保持 |
| `python -B -m pytest spikes/002-authority-contract -q -p no:cacheprovider` | 340通过 | authority合同旧回归保持，单独进程避免同名validator串台 |
| `python -B -m pytest tests/test_collaboration_docs.py -q -p no:cacheprovider` | 8通过 | 协作约束回归保持 |
| 真实CLI链单独生成的组件测试（不由check调用） | 4通过 | 独立固定黄金输出、模型边界与规则预期分开验证；不计入上述201 |
| 真实CLI链 | 12步全部符合预期 | 不同cwd/中文空格路径，生成→草稿→显式补全→普通入口未完成→合成入口通过→已知错误拒绝→恢复通过 |

正式测试命令额外使用本机忽略目录中的`--basetemp`和`--junitxml`，逐条完整argv、cwd、stdout、stderr、退出码及原始JUnit只留本地handoff指向的证据目录。计数由JUnit逐testcase核对声明数，不按终端滚屏估算。

真实CLI链的作者补全为**独立显式写入**，不是check自动修包：拷贝合成投影、更新candidate/implemented声明、写纯转换实现/测试和验收记录。普通CLI在该包上返回`INCOMPLETE/4`；显式宿主返回`PASSED/0`且`synthetic_only=true`。所有报告`runtime_verified=false`、`production_authorized=false`。JSON/text状态一致。重复init和prepare均为`CONFLICT/5`且不覆盖。

## 需求与证据映射

| 要求 | 覆盖位置及实跑内容 |
|---|---|
| 作者外壳/组件填写合同 | `test_contracts.py`逐必需字段缺失/错误类型、嵌套空值/额外字段、版本、重复声明、引用与kind、组件关联、占位/仅换implemented标签 |
| 目录/profile | `test_checks.py`清单/孤立声明/空源码/空测试/空验收、单CODE节点/单OUTPUT完成，无等待/控制动作偷偷报绿 |
| 权威来源而非包自证 | `test_synthetic_host.py`普通与显式入口分离；真实共享shape/digest/reader/context校验；缺来源/缺依赖/过期/撤销/来源不可得/摘要损坏/Provider角色及执行种类错误保留原码；伪造ctx/嵌套包材料不接受 |
| 不执行不写包 | 有副作用标记源码不被import/exec；check前后包、材料字节摘要一致；独立组件只由显式pytest进程运行 |
| 诊断与CLI合同 | `test_cli.py`字段/状态/退出码/两种格式，未知profile、无效参数及缩写拒绝；异常正文/秘密不回显 |
| 敏感内容 | 明显凭据/token/本机业务路径/包自称授权被拒绝，报告不复制原内容或异常；源码静态预筛不宣称全面秘密扫描或安全沙箱 |
| 文件系统/预算 | `test_paths.py`绝对/越界/反斜杠/ADS/保留设备名/坏编码/二进制/单文件2MB/累计20MB/256文件/深JSON；**真实Windows文件/目录/根路径symlink和junction均实跑，未跳过**；相同basename不同目录完整保留 |
| 并发与失败 | `test_generation.py`两独立进程竞争仅一方CREATED、另一方CONFLICT；重复生成不覆盖；故障注入的半截写入清理只删自有且未被改动文件，旁观者文件保留 |
| 宿主中立Skill | `test_skill_assets.py`检查真实源码/生成产物，生成说明链接不悬空；未安装或触发Skill，不伪造核心调度 |

## 红绿与自审

- 缺失工具入口的第一条CLI测试先红，生成实现后绿；缺失checker/合成入口也分别先红后绿。
- 对抗测试曾发现缺绑定被延后成INCOMPLETE、未声明导入漏检、空验收/空测试通过、半截写入残留，均修根因后重跑。Windows `DirEntry.stat().st_nlink`为0的差异改用真实`lstat`确认，不放松硬链接拦截。
- 最终规格对齐：异常退出码按任务卡固定为1；合成JSON/text显式标记synthetic_only；纯转换组件不求值非空规则，规则预期由独立测试明确分开。
- 主控首次审查返修R1/R2/R3：先运行新增定点红测试，得到4失败/3通过；随后恢复WF0§5.1固定8条非runtime发布记录及runtime闭包、模型0/1/80/81边界和规则空格预期；测试文件静态就绪门要求可识别的实质pytest入口，且保持不import/collect/执行；text诊断逐项保留JSON已有的安全位置、底层码、原因和修正提示。定点绿测7通过，终版209通过。
- 实现方做过需求与代码边界两轮自审；**不是独立审查结论**。没有用跳过/xfail制造通过；首轮测试临时父目录缺失、清理程序遇到pytest自建current符号链接等环境/取证失败，也原样保留失败记录与重跑结果。

## 副作用、清理与未验证项

真实CLI链前后包、材料及仓库逻辑文件SHA256一致；链路样例清理后独立确认不存在。R1/R2/R3返修链亦从新目录走完12步并清理；6个本轮pytest basetemp目录已读回不存在。测试临时目录按本次命令清单清理，保留清理前文件摘要、原始报告、JUnit和备份；不扫描或删除其他项目/历史/缓存。全部逻辑新增文件限定assignment允许范围，具体清单、摘要及范围检查结果见本机handoff。

尚未验证/未批准：
- 独立新作者只依Skill/指南完成L3盲跑，及主控独立验收。
- Linux/macOS实机兼容；未把Windows实跑泛化为全平台通过。
- I3等待/挂起/恢复、I4异步身份/回调、I6受控动作/幂等/读回的完整表示及运行语义。
- 真实Provider、发布Authority、Core/执行器/调度、激活/权限/业务闭环和生产批准。合成Reader/context只作固定测试夹具，不是生产可信来源。
- 静态AST筛查不能证明任意Python安全/纯函数/正确性；恶意宿主OS并发攻击不是安全沙箱承诺。必要人工审查与真实运行测试不能被静态PASSED替代。

**停止点：交主控独立验收。未暂存、提交、推送或改远程状态；不得由本候选自动进入WF2。**
