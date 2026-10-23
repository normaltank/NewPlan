> 后续状态更新：所有者随后明确授权删除旧 MyPlan。本文所说的旧代码、旧文档和 `legacy-server-outputs.zip` 等旧归档已经删除，下面的旧证据恢复操作不再适用。当前状态见 [最终清除记录](../2026-10-21-retire-legacy/README.md)；正文保留本轮结束时的事实。

# 2026-10-21：OpenSource 采用与存储整理

用户确认以 OpenSource 作为当前项目，并要求释放旧 MyPlan 占用及统一文档。本次处理项目入口、存储和文档；保留既有采集行为与人工决定，不进行真实院校采集、付费调用、推送或服务器部署。

## 当前与历史的边界

当前入口为 [项目 README](../../../README.md)、[业务契约](../../../CONTEXT.md)、[文档导航](../../README.md)。安装与运行由 OpenSource 的 `.venv`、`.secrets`、`workbench.py` 和 `runs/workbench/workbench.db` 支撑。旧 MyPlan 的 `server/`、类型库、计划和启动脚本保留追溯用途，文档入口已标明历史范围。

实际 Git 根目录仍是 `D:\Agent Workspace\Intern\MyPlan`；本次没有移动 OpenSource、创建新仓库、提交或推送。开始时 OpenSource 整个目录尚未被父仓库跟踪，因此本次先保存本机源码备份。父级已有的 AGENTS.md、docs/README.md 修改和其他未提交工作保留，改动前内容与补丁一并备份。

## 清理范围与保留内容

可重建目录的精确清单见 [cleanup-manifest.json](cleanup-manifest.json)，实际删除日志见 [cleanup-results.jsonl](cleanup-results.jsonl)。清理前核对绝对路径、工作区边界、目录中的重解析点、文件数与字节数；删除使用 PowerShell 原生文件操作。

| 内容 | 处理 |
| --- | --- |
| 旧 MyPlan `.runtime/dev-venv`、`worker-venv` | 删除可重新安装的环境；旧源码、锁文件、加密凭据和历史备份保留 |
| Mission B 构建缓存、暂存目录与验证包内的依赖／浏览器副本 | 删除可重建副本；13 个正式 ZIP 经完整性验证后原样保留，源码、输入、验证结果与用户输出保留 |
| 本地工具试验 `.uv-cache` | 删除依赖下载缓存；试验虚拟环境、浏览器、源码、报告与原件保留 |
| 旧 `server/outputs` | 先压缩归档，逐文件验证 SHA-256，核对来源未变化后删除展开副本；详见下方恢复说明 |
| 当前 OpenSource `.venv`、`.secrets`、`runs` | 保留；当前复核数据库和原始材料未作为缓存清理 |
| Docling、Jina 与其他工具试验 | 环境／模型／受控凭据和结果保留；Jina 仍不接入正式流程 |
| 父级 `.git`、`.agents`、旧源码／测试／文档、Sheets、`.planning`、Claude outputs 等 | 保留历史、输入与既有未提交工作；不为追求目录空白删除独立证据 |

Mission B 中旧验证解压目录不再是可直接运行的程序副本。需要运行或重新验证时，从对应 `release/` 正式 ZIP 重新解压；这些目录内原有结果和截图保留。正式工具的运行和构建方式查其 README 与构建脚本。

## 归档与恢复

本机备份位于 OpenSource 的 `.local-backups/2026-10-21-promotion/`，已加入忽略规则，不上传 Git：

- `documentation-before.zip`：整理前的入口文档。
- `working-tree-before.patch`：本次操作前已有的 Git 差异。
- `workbench-source-before.zip`：当前工作台根目录源码、脚本、依赖文件、静态界面与既有 fixture 备份。
- `legacy-server-outputs.zip`：旧 `server/outputs` 全部普通文件及目录清单；包内 `ARCHIVE_MANIFEST.json` 记录原相对路径、大小、修改时间和摘要。

恢复旧证据时先检查 [legacy-archive-verification.json](legacy-archive-verification.json) 的包摘要，将压缩包中的 `server/outputs/` 按原结构恢复到 MyPlan 根目录。若已有新结果，先恢复到独立目录对比，避免覆盖。仅恢复证据不等于恢复旧服务环境；旧环境需按旧锁文件重新安装。当前 OpenSource 的复核无需展开该归档。

## 文档与代码变化

- 现行说明分为业务契约、使用复核、运维、架构与试验索引；WORKBENCH 和 AGENT_HANDOVER 只保留稳定指向。
- 旧 MyPlan 的入口加历史范围说明；其审计报告和运行时 `server/recon_*.md` 正文保留。文档分类清单见 [documentation-inventory.json](documentation-inventory.json)。原 OpenSource README／WORKBENCH 转存 [历史资料](../../history/README.md)，不改写试采事实。
- `benchmark.py` 的 7 个旧回放样本复制到本项目 `fixtures/legacy-replay`，逐文件摘要一致，解除对父级 `tests/fixtures` 的读取依赖。来源见 [fixture-provenance.json](fixture-provenance.json)。本次未修改工作台采集、字段、身份、复核或导出实现。
- 忽略本机备份及可重建依赖／构建缓存，防止它们混入后续版本管理。

## 实际验证与空间结果

2026-10-21 18:33 的磁盘复测：D 盘可用空间由 **15.32 GiB 增至 27.64 GiB，增加 12.32 GiB**，已扣除归档实际占用。精确字节数与检查结果见 [verification.json](verification.json)。

同次观察中 C 盘约剩 6.99 GiB，系统分页文件约 45.35 GiB。本轮未清理 C 盘或修改系统分页设置；没有操作前分页文件大小，不能据此断言 C 盘变化由哪个进程造成。

- 196 项现有测试通过，日志为本目录 `unit-tests.log`；测试使用隔离数据。
- 离线回放通过：5 份个人页、1 份既有 60 条参考身份的名单和本机 HTTP 故障注入；名单参考差集为零。报告见 [replay-check/report.md](replay-check/report.md)。该结果不是全院真实人数或跨站完整性的重新验收。
- 当前数据库的任务／批次／决定／审计计数与操作前比较；56 条人工决定以内容摘要核对，SQLite 完整性检查通过。
- 源码基线、磁盘盘点、删除清单、归档摘要和当前文档链接核验分别保存于本目录。空间以实际磁盘可用量变化为主；文件逻辑大小可能受硬链接和同时发生的系统写入影响。

本次未启动工作台服务、未改 GitHub 权限或保护、未调用采集 API；清理前也未发现工作台端口正在监听。文档采用只改变当前入口，不代表已完成服务器部署或对全部学院作出完整性保证。
