# Mission C 服务器精简交接

承接 [#48](https://github.com/normaltank/NewPlan/issues/48) / [#49](https://github.com/normaltank/NewPlan/pull/49)，基线 a474ab5199afafdd2dfc967888f1b7ad55d37807。用户确认 Windows/Linux、共享DS密钥、每页Fetch/model各最多一次及批次2*N，验证只用虚构输入、离线与假外部HTTP；真实封包由所有者交付流程单独处理。

采用实际用户技能目录 `C:/Users/27451/.codex/skills` 的 ask-matt → implement/tdd（含 tests/mocking）→ code-review；一个可独立验收的服务器交接包沿用原任务，不新增票。当前文档见 [SERVER](<../../../Mission C/SERVER.md#服务器同事精简包>)，同事说明与逐文件清单在服务器包内。实施角色不代称独立合入、双轴审查或CI已完成；最终进度从原Issue/PR追踪。

外部行为测试：`python -m unittest discover -s "Mission C/tests" -p test_server_distribution.py -v`。第一片在入口不存在时失败，补齐preview/demo后通过；第二片在私人once尚未实现时失败，随后固定私人方案、自动交付与幂等扫描通过；打包片在builder不存在时失败，精确清单、权限和搬移启动通过；自检隔离反例原先把虚构批次写进正式数据库，修正为offline-demo子目录后通过。只假 httpx 外部站点/provider，不假核心服务或SQL。

测试覆盖无key预检/自检、缺失key启动失败、两去重页恰好4次辅助调用、SIGINT页间停止与重启续跑、旧无scope队列阻断且选项原样保留、unknown跨批次不重发、辅助异常与超长全文、自动Excel/ZIP、普通26文件与PRIVATE-FAKE29文件、嵌套排除、Unix权限和Windows/Linux搬移启动。CI矩阵在安装web依赖前先跑此测试，再跑原全套。

实施树Windows全套一次结果：115项（原108+新增7），106通过、9按原有开关跳过（7项真实浏览器、2项可选浏览器/OCR），290.436秒，0失败。新增7项均执行；Linux及准确提交CI终态由原PR后续记录，不以本机通过代替。

后续独立Spec指出首次导入完成/入队前中断仍blocked，不满足续跑；修复在data/server-import-intents持久保存导入前SHA/原文件名、导入后批次ID及排队阶段，只恢复本入口拥有、全部pending、无运行选项/产物/相关已消费或unknown尝试的未开始任务。已入队scope沿用、无意图旧队列仍阻断。公开CLI在真实隔离data上用外部文件I/O故障复现红→绿，另验batchID未落盘且源文件移走仍可续跑、相关global消费/unknown账本原样保留；复现和新回归结果另存，不改上轮115项事实。

恢复修复Windows验证：服务器原7+新增3共10项通过（33.664秒），相关private两模块9项通过（24.077秒），0失败/跳过；旧115全套未重复。准确新版本双轴复审与Windows/Linux CI待原PR记录。

33d2b7d后独立双轴分别发现恢复和首次导入的并发覆盖窗口：扫描锁只协调本入口；其他公开入口抢先入队后，旧enqueue仍会替换免费方案并赋私人scope，首次导入反例实际触发2次fake provider请求。修复在既有公开enqueue增加默认关闭的first_only条件，首次导入与恢复共用；批次锁内BEGIN IMMEDIATE检查最新queue/tasks并INSERT，冲突抛错，保留已有方案/暂停/预算。相关账本在事务内重读并拒绝已有付费锁；首次入队不创建该独占文件，避免扩大硬中断后的残留锁窗口。独立collector与scope保存不完全串行，真实请求仍由原有全局identity/unknown reserve保护；未改预算核心或其他运行链。

本轮公开CLI回归先复现恢复覆盖为红，修复后验证fresh和recovery免费队列均blocked、fake调用0且无私人预算；另在核心status后/批次锁前插入公开peer enqueue，验证事务内重查及旧enqueue显式替换语义。原两份独立定序脚本和日志保留，使用固定33d2b7d重放旧事实；修复树另存回放。首次入队保留现有付费锁、移除peer锁后可入队且不产生新锁也单独验证。当前本机验证与准确提交另见原Issue/PR执行记录；完整CI、独立合入和双轴复审由协调者完成，不以实施通过代称完成。

并发覆盖修复Windows定向结果：最终服务器15项（原10+新增5）在四依赖环境通过，28.742秒，含取得批次锁前peer已完成并清空队列时仍保留原产物。相关private9项通过（24.490秒）、batch15项通过（56.959秒）；后两组验证默认enqueue路径，本轮最终调整仅触及first_only分支，最终服务器组重验。均0失败/跳过；只用虚构输入及fake外部HTTP/文件I/O定序，无真实provider调用。历史全套结果不改写，本轮未重复全套。

保留限制：交付先同盘暂存再发布，强制退出可能留暂存或完整但未登记的快照，重启另存并保留旧件。已生成交付被外部移走时提示恢复，不覆盖历史结果。学院完整性未验证；未真实采集、付费、安装系统任务、重启或部署服务器。浏览器/OCR扩展未纳入四项基础依赖验证。
