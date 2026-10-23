# DeepSeek Fetch 隔离试验

问题：在现有学院采集、身份核验和交付流程中增加 DeepSeek Fetch，是否能补回正文和字段，以及是否引入错误？

本目录为独立试验，不能作为生产采集能力已经发布或全院采齐的证明。生产源码、数据库、旧运行和人工决定不修改。凭据只由现有安全启动器注入，不复制到本目录。

预定样本：

1. 阜阳师范大学，化学与材料工程学院：https://www.fynu.edu.cn/hxycl/
2. 南通大学，护理与康复学院：https://ntdxhk.ntu.edu.cn/ ，已知特殊师资入口 https://ntdxhk.ntu.edu.cn/xkjs/list.htm
3. 东南大学，吴健雄学院：使用既有任务中保存的官方学院入口，覆盖跨学院个人主页。

顺序：接口可用性检查；冻结当前采集源码副本；在独立数据库中运行现有方案和 Fetch 优先方案；检查名单、正文、字段、身份、失败分类和导出；按实际证据报告结果。

基线是本目录上方的 OpenSource 工作台，不是上层 MyPlan/server 类型库主流程。真实采集只执行一份；两组使用同一份名单、原始材料与业务规则，使差异集中在正文读取来源。Fetch 对入口和名单页面的返回另作诊断，不用于删改既有人员发现结果。

Fetch 增强方案保留原始 HTML、名单发现、分页和本地图片/PDF读取，测试 Fetch 作为正文读取来源。Fetch 返回的 Markdown 与本地原件分开保存；Fetch 404 不直接归类为原网页失效。试验不更改已有人员范围或自动放宽交付规则。

完整性：在独立核对官方分支、分页和逐人覆盖之前，一律为“完整性未验证”。

费用：按官方成功 Fetch 每千次 $0.75 估算；模型 token 另计。按调用逐项记录，不能把 Codex/DeepSeek Harness 服务端工具的免费安排直接套用到独立 API。

官方资料（2026-10-18 核对）：
- https://api-docs.deepseek.com/api/fetch/
- https://api-docs.deepseek.com/guides/search/
- https://api-docs.deepseek.com/quick_start/pricing/

结果入口为 [REPORT.md](REPORT.md)（仅在三个对照完成后生成）。费用见 costs.json，原件与逐项差异在 runs/，Fetch 原始响应与调用账本在 fetch-api/，选定反例见 spot-checks.json。测试使用 experiment.db，没有另启生产工作台或改变原人工决定。

吴健雄学院实际涉及 834 个不同姓名；串行采集段保留断点后由 continue_large_case.py 继续，原始段与续采段费用分别计入。续采仅在隔离启动器中启用三个并发和至少 1.1 秒的导航间隔，冻结的采集脚本不修改。

目录用于保存这一轮证据，不应在原目录重新执行 prepare.py 覆盖快照清单。新一轮实验应使用新的目录。API 凭据由原有 secure-api-run.ps1 临时注入进程环境，本目录不保存密钥。
