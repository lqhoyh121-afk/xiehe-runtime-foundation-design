# 协作者开工
署名：Laiqh

1. 克隆公开仓库；写入需各自正规GitHub授权，不得共享账号令牌。
2. 读[协作规则](../../AGENTS.md)、[项目总控](../../PROJECT_CONTROL.md)和[保护规则](GOVERNANCE.md)；从总控已分配的Issue接任务，不自行抢占。
3. 总控用`git worktree add -b task/issue-N <本机独立目录> main`建立工作区，提供Issue、精确目录、base SHA、文件边界、验收；在.local/assignment.json保存本机绑定。
4. 在该worktree根跑`python tools/verify_workspace.py --assignment .local/assignment.json`，回传实际路径与分支；失败停写。
5. 接续既有代码，备份/测试/定向修改；提交前扫描，逐文件stage；只能推任务分支，不直接推main。
6. 创建PR，关联Issue并写测试结果、影响范围、未验证项。独立审阅后由总负责人明确批准merge/publish，Agent不得自批。

任务状态只更新Issue；本地断点可保存但不冒充第二任务系统。凭据/真数据/配置/原日志不放Issue/PR。保护受套餐制约时，必须人工遵守并明确缺乏平台强制，不能以CI绿色推断有合并批准。

## 开工命令

```sh
git clone https://github.com/lqhoyh121-afk/xiehe-runtime-foundation-design.git
cd xiehe-runtime-foundation-design
git fetch origin
```

随后使用总控下发的真实目录和任务分支创建worktree，不能直接在克隆根目录开发。进入worktree后先核实assignment，再安装`python -m pip install -r requirements-dev.txt`。首次试点为Issue #1；总负责人批准合并前不扩大并行。
