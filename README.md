# 协合底层架构设计
署名：Laiqh

公开协作仓库：lqhoyh121-afk/xiehe-runtime-foundation-design。公开范围已由总负责人确认；不包含凭据、真实业务数据或本机配置。

先读[项目总控](PROJECT_CONTROL.md)、[协作规则](AGENTS.md)、[开工说明](docs/collaboration/START.md)和[保护规则](docs/collaboration/GOVERNANCE.md)。GitHub Issues负责执行状态，PR记录改动和审阅；总负责人批准最终合并/发布。

现阶段：架构候选＋两个合成验证片段。不是已部署底座，不包含生产账号/数据。整体连接见docs/architecture-track/assembly-architecture.md。

## 本地测试
Python 3.11；安装requirements-dev.txt后分别运行：

- 根目录跑`python -B -m pytest tests/test_collaboration_docs.py -q -p no:cacheprovider`；两个spike有同名模块，须分目录单独跑。
- 推荐进入spikes/001-input-contract，再跑`python -B -m pytest -q -p no:cacheprovider`。
- 进入spikes/002-authority-contract，再跑同一命令。
- 在第二目录跑`python -B cli.py --demo`；仅合成协议核验，不执行迁移。

证据和本机状态不随仓库发布；历史文档中的本地证据链接仅是溯源指示，不表示随库可下载。协作基线来源见docs/collaboration/MIGRATION.md。
