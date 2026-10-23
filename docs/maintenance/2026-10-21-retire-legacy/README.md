# 2026-10-21：清除旧 MyPlan

所有者在上一轮整理后明确要求：旧 MyPlan 已失败，凡不影响现有项目的内容都删除。本轮按这个授权清除旧工作区和旧归档，不再保留它们的展开副本或另做旧资料备份。

## 实际范围

- 删除旧 `server`、`Opus`、旧测试、脚本、依赖配置、数据库、输出、维护计划、文档和启动入口。
- 删除 `.runtime`、`.planning`、旧缓存、旧 Claude 资料、旧采集插件，以及先前保留的 `legacy-server-outputs.zip` 等旧归档。
- 将原 `Sheets` 中 4 份学院输入文件迁入 `OpenSource/inputs/colleges/`，逐文件校验 SHA-256 一致后删除旧位置；旧教师结果表不作为新项目数据沿用。
- 保留整个当前 OpenSource 项目的源码、运行环境、原件、复核库、密钥、工具试验、Docling、Jina 保留配置、Mission B 及其正式包。只在本项目内删除明确列出的旧 MyPlan 归档文件。

精确路径、删除前文件数和逻辑大小见 [retirement-manifest.json](retirement-manifest.json)；逐项完成记录见 [deleted.jsonl](deleted.jsonl)。删除前逐个校验绝对路径及白名单，区分普通文件与重解析点。1439 个旧测试链接仅删除链接对象、不递归进入目标；清除链接并再次检查后，才递归删除其旧目录。

## 剩余外层目录

MyPlan 外层只保留 `OpenSource/`、`.git/`、`.agents/skills/`、`skills-lock.json`、`.gitignore`、README、AGENTS 和 CLAUDE 简短入口。这里不再运行旧业务代码。

Git 元数据仍用于当前工作区及其他关联工作树，通用技能仍被当前开发环境引用，因此保留。没有删除远端仓库、改动 GitHub 权限或清理其他聊天的工作树。操作使用 `codex/retire-legacy-myplan` 分支，未提交或推送；旧源码在 Git 中可能仍可追溯，旧未入库采集证据的本地归档已经删除。

## 当前项目与文档

当前代码不读取旧 `server` 或旧数据库；离线回放的 7 份 fixture 在上一轮已迁入本项目。少数隔离试验会将父级 `server` 文件列入可选的防改动快照：目录不存在时枚举为空，不影响采集或新的隔离测试。其旧快照和历史报告仍表示当时版本，不能拿来宣称本轮源码完全相同。

项目入口、AGENTS、运维、架构和历史索引已更新，不再提供旧项目启动或归档恢复指引。权限核对说明迁为当前 [项目访问保护](../../project-access-protection.md)。上一轮整理记录保留历史事实，在顶部明确标注后续删除及恢复指引失效。

## 核验

结果见 [verification.json](verification.json)：

- 94 个受保护的源码、静态界面、依赖、fixture、加密凭据和配置文件摘要与删除前一致。
- 当前工作台的 9 个批次、92 个任务、56 条人工决定及审计等表计数保持一致；人工决定内容摘要一致，SQLite 检查通过，91 个已有运行目录仍可访问。
- 删除旧目录后重新执行 196 项工作台测试，并完成保存页及本机 HTTP 故障注入回放。回放名单与其 60 条参考身份一致；这不等于全院真实人数或全网完整性验收。
- 学院输入迁移记录见 [retained-inputs.json](retained-inputs.json)，回放结果见 [replay-check/report.md](replay-check/report.md)。当前文档相对链接另行检查。

本轮没有真实院校采集、付费 API 调用或后台服务重启。本轮删除 35 项旧目录／文件，逻辑大小 3.42 GiB；D 盘可用空间由 28.93 GiB 增至 32.35 GiB。精确字节数见核验结果；可用量也会受到同机其他进程影响。
