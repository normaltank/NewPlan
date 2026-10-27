# Mission B 文档与档案索引

从 [Mission B 入口](../README.md) 选择使用或维护路径。本索引区分当前说明、版本附带说明与历史证据；旧报告中的版本、测试数和远端状态只描述当时运行。

## 当前说明的负责文件

| 内容 | 负责文件 | 更新时机 |
| --- | --- | --- |
| 当前产品入口 | [Mission B README](../README.md) | 使用入口或目录职责改变 |
| Agent 的阅读路径与工作流来源 | [AGENTS.md](../AGENTS.md) | 工作方式或导航改变 |
| 维护任务分流、实施派工与业务验收证据 | [维护执行约定](maintenance-workflow.md) | 维护的分流或验收方式改变；公共规则仍由根目录工作流维护 |
| 完整版启动、输入、URL 核验和四列汇总规则 | [api_workbench/README.md](../SmallMission/api_workbench/README.md) | 当前实现或核验契约改变 |
| 精简版操作、展示边界、日志、邮件与构建 | [README_lite.md](../SmallMission/api_workbench/README_lite.md) | 精简版行为或分发维护改变 |
| 任务、规格、验收状态 | [根目录任务管理](../../docs/agents/issue-tracker.md) | 在对应 GitHub Issue 更新，不再维护第二份待办表 |
| 术语、长期设计决定 | [根目录领域文档约定](../../docs/agents/domain.md) | 出现需要明确的术语或决定时按需记录 |

根目录文档整理若影响 Mission B，先核对实际差异和上述职责。主工作台的人员资格、身份去重和字段交付规则不应通过文档整理带入 URL 核验。当前代码、版本常量和打包清单是实现依据；维护记录说明它们在何种材料上得到验证。

## 历史资料与发行说明

| 资料 | 适用范围 |
| --- | --- |
| [SmallMission README](../SmallMission/README.md) | 2.x 无 API 版与 2026-10-15 首批核验；保留原入口和历史结果链接 |
| [SmallMission 发行说明](../SmallMission/README_distribution.md) | 旧规则版发行包；其旧汇总格式和“无需 API”描述不适用于当前 API 版 |
| [DeepSeek 试验说明](../SmallMission/experimental_deepseek/README.md)、[报告](../SmallMission/experimental_deepseek/REPORT.md) | 3.0 形成前的结构识别对照；运行命令可能联网并产生费用 |
| [3.0 实现与验收报告](../SmallMission/api_workbench/IMPLEMENTATION_REPORT.md) | 2026-10-15 的版本、样本与计数，不作为后续版本的验收 |
| [完整版发行说明](../SmallMission/api_workbench/README_distribution.md) | 随完整版 3.0.1 打包的用户说明；保留与旧包一致，当前源码说明在本索引上方 |

这些文件原地保留，避免破坏保存页、回放和构建脚本的相对路径。旧发布包内的 README、原始输入和历史输出不改写。`README_distribution.md` 与 `README_lite.md` 会被相应构建脚本复制进包，修改维护说明前须核对其读者；已发布包不会随源码文档自动更新。

## 本地维护证据

以下路径均相对于 `SmallMission/api_workbench/`，属于维护机本地档案，未上传公开仓库。源码检出中缺少这些目录不代表测试失败；没有取得原件时不能复述为已复验。通过目录内 README 查具体运行、摘要和复现方法。

| 本地路径 | 证据范围 |
| --- | --- |
| `maintenance/20261022-college-list/README.md` | 20 学院基线、独立抽查、静态零链接修复与局部复测；仍有 5 个“错误”未做同等深度复核 |
| `validation/lite-20261022/README.md` | 精简版首次分发、日志还原和界面验证 |
| `maintenance/20261023-lite-progress/README.md` | 进度条、刷新与便携包验收；旧 MyPlan 分支的 CI 未启动记录 |
| `maintenance/20261023-log-mail/README.md` | 自动邮件回传、实际 EXE 发信、用户收件确认及 NewPlan 分支 CI 结果；关联 [Issue #2](https://github.com/normaltank/NewPlan/issues/2) |
| `maintenance/20261023-documentation/README.md` | 本轮文档整理、另一对话核查范围、链接检查与保留校验 |
| `maintenance/20261023-lite-results/README.md` | 精简版页面结果、仅错误学院下载和 20 文件上限；关联 [Issue #5](https://github.com/normaltank/NewPlan/issues/5) |
| `maintenance/20261026-compact-input/README.md` | 单学院的师资入口表与姓名／个人URL表兼容、原件解析与 1.0.6 分发验证；关联 [Issue #8](https://github.com/normaltank/NewPlan/issues/8) |
| `maintenance/20261026-batch-stall/README.md` | 19 份原件批量停滞复现、康复学院无效分页修复与 1.0.7 验证；关联 [Issue #11](https://github.com/normaltank/NewPlan/issues/11) |
| `maintenance/20261026-mail-triage/README.md` | 回传日志去重、21 个特殊情况的原因分流；关联 [Issue #13](https://github.com/normaltank/NewPlan/issues/13) |
| `maintenance/20261026-log-maintenance/README.md` | 名单范围冲突与分页维护、原网页实跑、反例及 1.0.8 分发验证；关联 [Issue #14](https://github.com/normaltank/NewPlan/issues/14) |
| `maintenance/20261026-workflow-contract/README.md` | Mission B 维护分流、实施派工与验收记录的流程修正；关联 [Issue #17](https://github.com/normaltank/NewPlan/issues/17) |

历史运行的 `.planning/` 文件记录当时执行过程，供复盘查阅；任务当前状态到 GitHub Issue 核对，不从旧计划自动恢复工作。新增记录写清问题、来源、根因、修改、实际验证和剩余限制；完成后从本索引或负责文档提供一个入口。

## 存放与保留

- 当前源码和维护说明入库；输入表、运行日志、模型原文、网页证据、带配置的分发包及构建目录按现有忽略规则留本地。
- 历史包也可能是构建依赖：精简版的 [build_lite.py](../SmallMission/api_workbench/build_lite.py) 仍从完整版 3.0.1 包校验并复用浏览器，不能因版本旧而删除该包。
- 下载结果保存在新输出目录；`data/`、`lite-data/`、`validation/`、`maintenance/` 与旧 `outputs/` 各自保留来源关系，移动时先核查相对路径和回放依赖。
- 文档整理结束时检查当前入口的相对链接、历史正文保留情况及变更清单。涉及行为变更时，另按对应任务执行隔离验证；链接检查不能证明核验准确率。
