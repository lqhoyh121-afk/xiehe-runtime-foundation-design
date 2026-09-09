# 协作规则
署名：Laiqh

先读PROJECT_CONTROL.md，再读GitHub Issue、其依赖及最近PR。Issue是执行状态唯一权威；本地状态文件只是缓存/断点，不自行维护第二份完成率。

总负责人：lqhoyh121-afk。Agent负责协调和具体操作，不得自行批准合并、发布、架构冻结或生产写入。首次清理基线提交/推送获本次授权；此后所有修改通过PR，禁止直接推main、强推、rebase/amend改写公共历史。

一任务一Issue、一任务分支、一独立worktree。启动前由总控提供精确工作目录、issue URL、分支、base commit、允许文件和验收；本机绝对路径只放忽略的.local/assignment.json，不放GitHub。进入指定根目录跑`python tools/verify_workspace.py --assignment .local/assignment.json`，回传真实输出。不能把聊天分支当文件隔离。

修改前读源码和任务、备份到忽略目录；先测试再修复；只逐文件stage并跑tools/audit_tree.py。凭据、真实业务数据、本机配置、数据库、原日志、缓存和备份不进入Git/Issue/PR。合成测试摘要可进PR，原输出保持本地；不上传账号密码或token。

任务认领要在Issue记录实际会话/Agent角色（不要上传内部session路径）。总控统一调度，边界冲突先停写，不覆盖。提交PR注明关联Issue、范围、实跑命令、结果和未验证项；独立审阅由不同执行上下文完成，不把同一GitHub账号的Agent评论当作平台独立账号批准。

合并与发布必须得到总负责人针对具体PR/head的批准；不启用auto-merge。权限允许时要求PR、CI及独立review；保护不可用时必须说明，规则文件不是强制保护。开发/测试不默认取得生产权限。

旧本地仓库及历史只读保留，本协作库基于清理的成果建立新根提交；不得从旧仓库merge/push历史。现有spike继承，不因迁库重做。所有源码仍为局部候选，冻结和生产闸门不变。
