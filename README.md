# OpenSource · 高校师资采集与复核工作台

输入大学、学院名、学院链接及可选的师资列表链接，采集教师名单、职称、本人邮箱、完整简介与主页，保存原件并把需要人工判断的异常集中到工作台。可信记录自动交付，按大学分别生成教师 Excel。

**自 2026-10-21 起，本目录是当前项目。** 旧 MyPlan 的代码、数据与归档已按所有者要求清除；OpenSource 自己的运行数据、复核决定、密钥和依赖独立保存。采用本项目不等于全院完整性已普遍验证，也不等于已部署公网服务。

## 开始使用

已配置的本机环境，双击 [start-workbench.bat](start-workbench.bat)，打开 [本机工作台](http://127.0.0.1:8765/)。首次安装、密钥配置、只看复核与夜间运行见 [运维手册](docs/operations.md)。

在网页粘贴“大学、学院名、学院链接、可选师资列表链接”，预览后提交；采集结束后处理异常并按大学下载。每份教师 Excel 固定为“有邮箱教师、无邮箱教师、主页失效教师”三个 Sheet。采集人统一为“自动采集”。详细使用见 [使用与复核](docs/review-and-delivery.md)，字段和完整性要求见 [交付契约](CONTEXT.md)。

## 文档入口

| 需要了解 | 文档 |
| --- | --- |
| 项目做什么，哪些信息可以交付 | [CONTEXT.md](CONTEXT.md) |
| 安装、运行、备份、部署边界与排障 | [运维手册](docs/operations.md) |
| 输入、批量复核、排序、下载 | [使用与复核](docs/review-and-delivery.md) |
| 代码职责、实际调用链、当前工具 | [架构与模块](docs/architecture.md) |
| 文档维护与历史资料 | [文档导航](docs/README.md) |
| 开发 agent 如何开始工作 | [AGENTS.md](AGENTS.md) |

## 工程与试验

根目录 Python 模块和 `workbench-static/` 是当前工作台；`runs/` 保存当前原件、结果与复核数据库。依赖通过 [requirements.lock](requirements.lock) 锁定，离线验证命令见运维手册。

[experiments/](experiments/README.md) 保留独立工具对照。Jina 暂不接入正式流程，Docling 本地试验环境与模型保留。`Mission B/` 是另一个名单链接核验工具，其 [使用与交付说明](<Mission B/SmallMission/api_workbench/README_distribution.md>) 与本工作台分开维护。

学院输入表集中保存在 `inputs/colleges/`，可继续复制到网页输入框使用。当前 Git 根目录为 OpenSource，对应公开仓库 [normaltank/NewPlan](https://github.com/normaltank/NewPlan)。仓库保存源码、测试和文档；运行数据、输入表、凭据与安装环境留在本机，不能用代码仓库代替数据备份。

OpenSource 路径保持不变。父级 MyPlan 保留旧 Git 元数据以支持其他关联工作树，以及通用开发技能和简短入口；本项目提交从 OpenSource 目录操作。旧项目删除范围与验证结果见 [清除记录](docs/maintenance/2026-10-21-retire-legacy/README.md)。
