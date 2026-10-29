# HTTP 状态轮询 CI 跟进

关联 [#43](https://github.com/normaltank/NewPlan/issues/43)。本补记追加最终 CI 新发现，不改写本目录此前的分发包、69 个载荷文件、hash 或验收报告。

## 已知事实与边界

提交 `e7c802e50b75cd63ef51c90f7313aab88c7d32e0` 的 [CI 40805687803](https://github.com/normaltank/NewPlan/actions/runs/40805687803) 两个 Windows 作业通过；Ubuntu standalone 作业运行 94 项、跳过 9 项，仅一项 error。错误来自 `test_web.HTTPFlow.test_multifile_preview_is_not_collection_and_cached_download_preserves_full_text` 的状态 GET 轮询：`httpcore.ReadError: [Errno 104] Connection reset by peer` 转为 `httpx.ReadError`，不是内容断言或轮询超时。

原 CI 未保留测试服务的 `server.log`。无法据此判定 Linux 服务进程退出、请求处理错误或连接关闭竞态，更不能宣称 Linux 产品本身已坏。Windows 本机原单例修复前通过 1 项（46.619 秒），只能说明本次本机未复现原服务端条件。

## 可重复反例与最小修复

测试使用真实本机 HTTP/1.1 socket：先成功建立长连接，再在状态 GET 上发送 TCP RST。旧 `until` 两次稳定复现与 CI 相同的 `httpcore` → `httpx.ReadError` 及等待函数调用位置；随后同一存活服务接受新连接并返回正常状态。Windows 的系统错误码为 `10054`，Linux 原日志为 `104`。这证明了测试等待函数对可恢复读重置立即中断的缺口，未证明原 CI 对端为何重置。

修复仅涉及测试基础设施：状态 GET 遇到 `ReadError` 后，最多再读两次，恢复窗口从首次重置起最多两秒；其他成功条件、原等待次数、长全文、三 Sheet、来源字节和重复导入断言保留。读取成功仍必须满足原来的批次谓词。重试没有安装到共享 HTTP 客户端或产品中，因此不会重发开始、导入、付费等写请求。

服务退出在再次读取前失败；持续重置、恢复超时、连接错误及非 200 状态均失败。实际测试服务的失败信息附进程退出码与最多 8,000 字符日志尾部；不会把异常读、服务死亡或内容错误解释为批次成功。

## 验证与证据

公开边界为本机 HTTP → 状态读取／失败诊断，原场景仍为双 Sheet Excel → 本机服务 → 严格缓存 → ZIP/XLSX/全文。未使用私有数据库、内部模块 mock、真实网站、付费或实际密钥。

- 新增 `test_http_polling.py` 三项：暖连接重置后新连接恢复；持续重置在有界次数内失败；实际子进程退出后立即失败并含退出码和服务日志。旧实现红 3 项，新实现最终绿 3 项（5.283 秒）；原精确 RST 反馈脚本再跑通过（2.256 秒）。
- 修复后仅重跑原长全文 HTTP 单例，1 项通过（39.513 秒），原断言保留。未重复完整测试集、浏览器测试或另建 Linux 环境。
- 本机原始证据位于受控 TEMP：`mission-c-v2-ci-linux-e7c802e.log`、`mission-c-v2-ci-reset-probe.py`、`mission-c-v2-ci-reset-probe-exact-red.log`、`mission-c-v2-ci-reset-probe-repeat-red.log`、`mission-c-v2-ci-polling-focused-red.log`、`mission-c-v2-ci-polling-green.log`、`mission-c-v2-ci-original-pre.log`、`mission-c-v2-ci-original-post.log`。进度及精确冻结版本见 `mission-c-v2-ci-fix-progress.md` / `mission-c-v2-ci-fix-handoff.md`。

独立合入、受影响双轴复审、新准确提交的 CI 和分发包刷新由 #43 继续追踪。本补记不以本机通过替代后续 Ubuntu CI，也不把此前试生成包当作最终交付。
