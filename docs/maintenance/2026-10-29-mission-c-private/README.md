# Mission C 私人预配置分发

需求：[Issue #48](https://github.com/normaltank/NewPlan/issues/48)。比较基线 `20cf31638d16ebccc5f0f6d6d46e66f48fd270d1`；本记录只覆盖假凭据、虚构材料与外部 HTTP 模拟，不代表 DS 在线可用、真实付费成功、全院完整性或实际目录部署。

## 机制与验证入口

旧简版开始固定关闭 Fetch/模型，且批次共享目录中的历史尝试计数会消耗后续批次预算。本轮私人方案由服务端元数据固定；凭据载荷独立并在实际开始才读取。普通构建通过显式文件清单排除运行数据与凭据；私人构建仅添加指定配置和凭据，使用可搬移相对路径。私人包包含可提取的共享凭据，仅供授权接收者。

批次总预算按去重任务数设为 2*N，持久 scope 分别计数；全局操作/URL/原件哈希尝试继续拦截已完成和未知请求。每批次页面每类操作至多一次，scope 预算不能事后扩大。付费辅助失败与可信教师交付分别保存，页面和 ZIP 异常明细报告辅助未完成。

`Mission C/tests/test_private_delivery.py` 经公开 HTTP 或 CLI 验证：缺失/空/非法凭据失败，启动/预检/离线示例懒读取；两批重复行去重后分别调用 Fetch+model；重启与跨学校同 URL 全局去重；401/402/未知结局可见且保留原站教师；scope 预算耗尽且不能扩大；普通包不含凭据，PRIVATE 假包搬移后旧 replay 与 batch demo 可运行。只模拟外部 HTTPTransport，不模拟内部类或 SQL。

复现使用独立安装环境：

```text
python -m unittest discover -s "Mission C/tests" -v
python -m compileall -q "Mission C/mission_c" "Mission C/web.py" "Mission C/build_package.py"
```

完整 suite：103 项，9 项可选集成跳过，341.546 秒，退出码 0；旧 97 项加本轮 6 项。最终搬移 replay/demo 定向复验 1 项通过（4.243 秒）；Edge 默认页定向复验 1 项通过（14.921 秒）。compileall 与 git diff --check 通过。

Windows Python 3.12.10；httpx 0.28.1、FastAPI 0.115.12、uvicorn 0.34.2、openpyxl 3.1.5。Edge 真实默认页上传/预检、离线开始、重开恢复、窄屏和实际 Excel/ZIP 下载单项通过。Linux CI、独立合并与两轴审查由主协调代理跟进，本实施记录不将其记为已完成。

本机临时证据目录为 `mission-c-ds-private-evidence`：逐片 red/green、完整测试日志、普通/PRIVATE-FAKE 包与浏览器截图。假包只用于验证；真实凭据未由实施代理读取，实际 D 目录与运行服务未修改。

当前操作、共享边界和官方 Fetch/模型文档链接见 [WEB](../../../Mission%20C/WEB.md#私人分发)，历史报告保留当时事实。实际凭据预配置、真实私人包与准确提交 CI 另由所有者已授权的主协调代理处理。


## 独立审查后的集中修复

初版集成 `5aa533c3f600bb374bc009ce44946588c7def268` 的独立 Spec 审查发现：旧无 scope 付费队列续跑被无条件赋予新 scope，原历史支出被过滤，能够在原额度耗尽后多发两次请求。Standards 审查发现：按后缀递归封包会收入 `mission_c` 下任意运行材料或私人目录。协调代理另核实 Windows ZIP 成员 creator/mode 没有保留已知 `.sh` 的 Unix 执行位。以上反例来自假材料/实际 ZIP 元数据，没有真实泄密或 Linux 部署失败的观测。

修复后只有新私人方案显式开始才持久保存批次 scope；旧队列和普通付费批次沿用全局预算。原 20cf 的公开 BatchService 两页/预算2/先处理1页脚本独立复现：5aa 升级续跑再次发2次，累计4；修复后续跑0次，累计仍2，原无scope记录和旧队列事实保留。保留公开CLI先写无scope消费、普通队列持久保存后重启续跑的回归测试，不直接操作私有SQL或ledger。

封包采用精确模块与前端文件清单；隔离源码副本植入 data/outputs/cache/.private 与未列出的源码/静态文件，普通及私人包均排除，私人仅添加指定两项载荷与声明。输出 ZIP 一律 Unix creator3：脚本755、普通644、私有元数据与凭据600；搬移旧 replay 与 batch demo 继续可运行。权限验证为 Windows 构建输出的元数据检查，Linux 实跑由准确新提交 CI 跟进。status 同时复用单次验证的 binding，保持缺失/篡改原件判定。

审查原件及逐项红绿另存 `mission-c-ds-private-fix-*` 证据，保留初版报告和103项测试当时事实。本次按协调代理确定的范围执行受影响专项，未重复整套旧103或宣称真实 DS 在线成功。

最终受影响专项12项通过（97.629秒，无skip）：新3项预算/封包回归、原私人流程6项、原件缺失检测、HTTP多文件全文交付与中断恢复。此前逐片专项7项及权限/搬移2项分别通过。compileall与git diff --check通过；完整新版CI与两轴复审由协调代理跟进。

## 长简介字段扫描修复

后续 CI 长全文状态读取出现 `RemoteProtocolError`。离线定位确认 Mission C 独立字段模块的 `\S*@\S*` 对无空白、无 `@` 的连续简介逐起点回溯；本轮仅将该异常邮箱扫描改为逐个完整非空白 token 读取，再跳过无 `@` 的 token，保留原 token 范围、上下文、候选和异常规则，未改 HTTP 重试或主工作台字段模块。

`Mission C/tests/test_field_scan.py` 在公开字段/HTML 边界验证多 `@`、中文标点、完整/不完整地址混排、全角字符及跨行邮箱。新增十万字连续简介在旧实现达到 5 秒子进程期限而失败；修复后两项共 0.351 秒通过，核对完整简介、页面原文、正文 HTML 与姓名/职称/邮箱。期限包含导入和输出，本机有超过十倍余量；Windows 超时按独立 worker PID 清理其进程树，覆盖虚拟环境启动器的子进程。另有 1000 个短合成样本与旧字段实现的完整输出一致。

原 CLI、长全文 HTTP/ZIP、断点恢复、私人批次/搬移包、既有预算/封包回归和状态读取共 26 项通过（70.491 秒，2 项可选浏览器/OCR 跳过），compileall 与 diff 检查通过。诊断用同一真实 uvicorn/原状态读取 helper 与实际字段调用，在旧扫描复现断开，新扫描确认线程完成且邮箱正确；这支持 CPU/GIL 停顿与 keepalive 的机制，原 CI 现场的完整因果仍未确认。逐片红绿和诊断程序保存在临时 `mission-c-ds-private-ci-*` 证据中；准确提交的完整 CI、独立合入及两轴复审由协调代理跟进。
