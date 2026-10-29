# Mission C 无界面后台与扫描

对应 [规格 #43](https://github.com/normaltank/NewPlan/issues/43)、[实施票 #46](https://github.com/normaltank/NewPlan/issues/46)。当前用法由包内 [SERVER.md](<../../../Mission C/SERVER.md>) 维护；本页保存实施与验证范围，不作为运行依赖。

实施者使用独立 `codex/mission-c-batch-server` 工作树，从已验收核心集成提交 `d36e87c830f6a93720513618dae9189f96fe7447` 开始。实际读取本机 `~/.codex/skills/ask-matt`、`implement`、`tdd` 及 tests/mocking 引用、`implement-spec`、`to-spec`、`to-tickets`、`code-review`、`writing-for-agents`；沿用已经确认的公开 CLI/进程/导出产物边界。此实施票不独立派审查代理，整体集成由主代理按双轴审查。

## 行为与反例

- 首个公开 CLI 红例为 `server.py` 缺失；`8346a01` 实现逐文件内容 hash 扫描。相同内容重复扫描、改名副本不新增；目录新到一份文件只新增该份；内容变化建立新批次并保留原产物字节，大学 ZIP可核查。
- 损坏工作簿最初仍返回退出0；修复为保留可见导入问题并返回1。默认扫描不排队、不生成采集结果，无来源的付费参数返回2。
- 持续 worker 最初不支持轮询参数，watch 命令不存在；`b036a95` 加入持续处理。公开进程验证暂停→继续、只消费显式队列、缓存原件移除后仍能处理、后续新文件到达不重跑旧批次。
- 搬移后平台启动脚本最初不存在；Windows实跑 `server.bat`，使用中文/空格程序路径、外部 Python、外部数据根完成离线任务。Linux脚本保留可执行位和LF，实际 Linux执行由 CI 对应提交判定。
- 新增自检反例：扫描一个已在多文件批次中的输入时，旧逻辑会把目录外其他输入一并排队。修复为保留原批次并明示 `not_queued_reason`，要求显式对完整批次排队；已排队批次仍由共用 worker执行。
- Windows并发反例：核心锁初始化在获取锁异常转换之前读取第一个字节，另一个进程已经持锁时返回普通权限错误。公开 server worker 重现未重复采集，但忙碌语义失败；修复归属核心票集中处理，后台没有吞掉任意权限错误。

所有输入为虚构双 Sheet，运行仅使用缓存或 `127.0.0.1` 假站。没有真实19表的采集、真实 API、密钥读取、付费、推送、服务器部署或本机计划注册。

## 可重放验证

在仓库根目录使用已安装 Mission C 基础依赖的 Python（页面合入后另安装 `Mission C/requirements-web.txt`）：

```text
python -m unittest discover -s "Mission C/tests" -p test_server_cli.py -v
python -m unittest discover -s "Mission C/tests" -v
```

`test_server_cli.py` 从公开命令和进程验证扫描、坏文件、默认不运行、暂停/继续、持续发现、进程中断与恢复、并发锁和独立搬移启动；不写私有 SQL、不 mock 内部采集器。Windows/Linux矩阵安装独立基础及页面依赖，不把根 Windows锁安装到 Ubuntu；原根工作台 Windows检查保留。Linux可选浏览器/OCR没有作为本票验证结果。

最终合入版本、完整测试结果、独立双轴审查与准确 SHA 的 CI 由整体交付记录补齐；测试通过不证明学院完整性或未知网站适配。
