# Mission C 服务器精简交接

承接 [#48](https://github.com/normaltank/NewPlan/issues/48) / [#49](https://github.com/normaltank/NewPlan/pull/49)，基线 a474ab5199afafdd2dfc967888f1b7ad55d37807。用户确认 Windows/Linux、共享DS密钥、每页Fetch/model各最多一次及批次2*N，验证只用虚构输入、离线与假外部HTTP；真实封包由所有者交付流程单独处理。

采用实际用户技能目录 `C:/Users/27451/.codex/skills` 的 ask-matt → implement/tdd（含 tests/mocking）→ code-review；一个可独立验收的服务器交接包沿用原任务，不新增票。当前文档见 [SERVER](<../../../Mission C/SERVER.md#服务器同事精简包>)，同事说明与逐文件清单在服务器包内。实施角色不代称独立合入、双轴审查或CI已完成；最终进度从原Issue/PR追踪。

外部行为测试：`python -m unittest discover -s "Mission C/tests" -p test_server_distribution.py -v`。第一片在入口不存在时失败，补齐preview/demo后通过；第二片在私人once尚未实现时失败，随后固定私人方案、自动交付与幂等扫描通过；打包片在builder不存在时失败，精确清单、权限和搬移启动通过；自检隔离反例原先把虚构批次写进正式数据库，修正为offline-demo子目录后通过。只假 httpx 外部站点/provider，不假核心服务或SQL。

测试覆盖无key预检/自检、缺失key启动失败、两去重页恰好4次辅助调用、SIGINT页间停止与重启续跑、旧无scope队列阻断且选项原样保留、unknown跨批次不重发、辅助异常与超长全文、自动Excel/ZIP、普通26文件与PRIVATE-FAKE29文件、嵌套排除、Unix权限和Windows/Linux搬移启动。CI矩阵在安装web依赖前先跑此测试，再跑原全套。

实施树Windows全套一次结果：115项（原108+新增7），106通过、9按原有开关跳过（7项真实浏览器、2项可选浏览器/OCR），290.436秒，0失败。新增7项均执行；Linux及准确提交CI终态由原PR后续记录，不以本机通过代替。

保留限制：首次导入成功而入队前中断不会自动补私人预算，保留并提示blocked交维护者核对；交付先同盘暂存再发布，强制退出可能留暂存或完整但未登记的快照，重启另存并保留旧件。已生成交付被外部移走时提示恢复，不覆盖历史结果。学院完整性未验证；未真实采集、付费、安装系统任务、重启或部署服务器。浏览器/OCR扩展未纳入四项基础依赖验证。
