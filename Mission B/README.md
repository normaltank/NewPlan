# Mission B：师资名单链接核验

Mission B 核对输入表中的 URL 与指定师资名单页面的实际链接，生成核验结果和修正表。它与 OpenSource 的教师信息采集工作台共用仓库，独立运行和保存数据；链接核验通过不代表全院教师信息已采齐。

| 你要做什么 | 从这里开始 |
| --- | --- |
| 使用、维护本地完整版，了解输入与判定规则 | [完整版说明](SmallMission/api_workbench/README.md) |
| 分发只需输入和下载的精简版，维护进度、日志和邮件回传 | [精简版维护说明](SmallMission/api_workbench/README_lite.md) |
| 查找版本记录、验证证据或旧版资料 | [文档与档案索引](docs/README.md) |
| 让 agent 修改 Mission B | [维护入口](AGENTS.md) |

当前实现位于 `SmallMission/api_workbench/`；`SmallMission` 顶层的无 API 版和 `experimental_deepseek` 是保留的旧实现、试验及证据。原始名单位于本地 `学院列表/`，生成结果不会覆盖原件。正式分发请使用干净发行包。
