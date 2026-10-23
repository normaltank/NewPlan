# Jina MCP 隔离接入记录

2026-10-18。用户授权配置 Jina MCP；本次仅完成接入、一个教师页的 MCP 读取及一次完整 Markdown 对照。

## 配置与隔离

- 名称：`jina_test`。配置保存在 `OpenSource/.codex/config.toml`，限定该目录及其子目录的 Codex 会话；父目录 MyPlan 的会话不会自动读取子目录配置。
- 使用官方 HTTPS 服务，只注册 `read_url` 和 `search_web`。搜索已注册，尚未调用验证。
- 使用 Codex 原生 HTTP 连接及 `http_headers_helper`；没有安装 mcp-remote 或其他新依赖，也没有更改生产采集器、工作台、数据库或既有依赖。
- 密钥存放于当前 Windows 用户的 `.codex/credentials/jina-test.dpapi`，采用当前账号的 Windows DPAPI 加密；文件权限仅授予当前用户。配置、脚本、报告中没有密钥。认证辅助程序仅通过被捕获的 stdout 向客户端提供请求头，不应直接输出至终端或保存为日志。
- 测试环境：Codex CLI 0.159.0、PowerShell 7.6.5、Python 3.12.10；辅助程序版本 1.0。本次官方远程 MCP 自报版本 1.9.0。云端服务会由 Jina 更新，不能保证固定版本；本地文件哈希和实际响应留在本目录。
- `max_tokens=0` 关闭 MCP 服务的长度截断，但不会关闭上游正文筛选。没有启用 OCR、购买套餐或安排批量采集。

## 实际验证

Codex CLI 能识别该配置。使用相同配置中的认证辅助程序完成了 MCP `initialize`、`tools/list` 和一次 `tools/call`，并保存响应。当前这轮会话没有动态加载新工具；在本目录重新打开会话后检查 `jina_test`，如未刷新再重启客户端。

样本：[东南大学土木工程学院邓小鹏主页](https://civil.seu.edu.cn/dxp/list.htm)。

| 路径 | 实际内容调用 | 返回字符数 | 姓名 | 已知本人邮箱 |
|---|---:|---:|---|---|
| 官方 MCP `read_url` 默认读取 | 1 | 19,511（含响应包装） | 保留 | 丢失 |
| Reader API，显式完整 Markdown | 1 | 25,546（正文） | 保留 | 保留 |

两个字符数统计位置不同，不用于计算完整率。这里只验证一个页面，不代表全院完整性或全部工具能力。MCP 的连接验证成功，已知邮箱覆盖检查失败；失败结果保留在 `verification.json`，没有当作全部通过。

官方源代码 `src/utils/read.ts` 的普通读取没有指定 `X-Respond-With: markdown`，而 MCP 的输入参数没有暴露此格式设置。完整 Markdown 对照沿用同一密钥、同一 URL 和相同基础请求头，仅增加上述格式设置；邮箱恢复。这与此前匿名对照中自动正文漏掉信息卡的现象一致。

**结论：MCP 可作为交互测试入口；正式教师采集不能把默认 MCP 输出视为完整原件。若后续接入 Jina，应优先验证显式完整 Markdown，并在需要时保留 HTML。** 本次没有把 Jina 自动接入生产工作流。

本次共 2 次网页内容请求（MCP 1 次、直接 Reader 1 次），没有调用搜索、OCR 或 DeepSeek。Reader 对照返回 16,580 tokens；MCP 的包装响应未提供账单计量，合计 tokens 和扣款金额未知，未查询账号账单。不能把已知的一次计量当作两次请求总量。

## 文件与复用

- `jina-headers.ps1`：读取加密密钥的认证辅助程序。
- `save-key.ps1`：交互式加密保存密钥；已有凭据时拒绝覆盖。DPAPI 文件不能直接迁移到其他 Windows 账号或服务器。
- `probe.py`：连接和工具列表验证；`--read` 还会检查样本姓名及邮箱。已知默认 MCP 漏邮箱，因此该完整性断言会失败。
- `reader_control.py`：完整 Markdown 对照。两个内容测试均用独占的 attempt 文件避免意外重复扣量；重新试验时应另建一份实验目录。
- `initialize.json`、`tools.json`、`read-result.json`、`reader-control-result.json`：原始响应；`verification.json` 和 `reader-control-summary.json`：验证结果。
- `isolation-check.json`、`evidence-sha256.json`：源代码/全局配置核对、凭据扫描和本次文件校验。

停用只需将项目配置中 `[mcp_servers.jina_test]` 的 `enabled` 改为 `false`，重新加载客户端。无需改生产采集代码或删除其他 MCP。

## 来源

- [Jina 官方 MCP](https://github.com/jina-ai/MCP)：端点、工具、筛选及截断参数。
- [本次检查的官方普通读取实现](https://github.com/jina-ai/MCP/blob/b938c00f0870a75b39a78d5dff1f5bf645151a6e/src/utils/read.ts)：保存了该提交的源码；远端实际部署提交无法从版本号独立确认。
- [Codex 官方 MCP 配置](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)：项目配置及认证辅助程序。

配置诊断：最初尝试系统 Windows PowerShell 时，继承的模块路径导致安全模块无法加载，尚未发出网络请求；改用已安装的 PowerShell 7.6.5 后成功。没有修改系统执行策略或全局模块路径。
