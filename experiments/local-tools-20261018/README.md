# 本地候选工具隔离对照

本目录补测 Scrapy、Scrapling、ScrapeGraphAI，承接用户已授权的工具试验。结论见 REPORT.md。

范围是固定材料的读取与字段提取，不是现代 `MyPlan/server` 主流程或整院完整性验收。未修改主项目代码、旧依赖、正式数据库、人工决定或服务。环境、浏览器、分词缓存和输出都在本目录。Docling 沿用前轮本地结果，本轮未安装或运行 Docling。

- `samples.json`：26 个固定网页；`sources/` 为前轮保存的同一批 HTML，带 SHA256。
- `.venv-fetch`：Scrapy 2.19.0、Scrapling 0.5、Patchright 1.64.1；精确版本见 requirements-fetch.lock。
- `.venv-graph`：ScrapeGraphAI 2.3.1、langchain-openai 1.7.2；精确版本见 requirements-graph.lock。
- PyPI 直连失败后使用清华镜像，未关闭 TLS 校验。
- Scrapling 0.5 不再导出旧文档中的 DynamicFetcher。本轮按实际安装版本使用 StealthyFetcher 读取公开页；不启用验证码求解、不使用代理轮换或外部付费服务。
- 分词文件下载曾导致首次启动等待。诊断和重启日志保留；最终缓存与官方分词文件 SHA256 相符。没有修改上游库代码。

复现时用独立新目录，先冻结新的 baseline，避免覆盖本次证据。运行顺序：prepare.py → 安装锁定依赖 → run_scrapy.py / run_scrapling.py → run-graph-secure.ps1 → evaluate.py → finalize.py。

模型调用：通过已有本地加密凭据，仅在子进程环境解密；使用官方 DeepSeek `deepseek-flash`，没有把凭据交给 ScrapeGraphAI 云 API。请求及响应正文记录在 api/，不记录 Authorization；本轮上限 24 次调用、已完成总用量达 250,000 tokens 后停止新增请求，实际值见 usage.json。

读取指标是已核实姓名、邮箱、指定论文、名单链接是否仍在材料里；不代表字段自动归属正确。ScrapeGraphAI 与直接 DeepSeek 控制组使用同一原始 HTML、任务要求、模型与输出字段。直接控制组输入原始 HTML，ScrapeGraphAI 会先转 Markdown；二者 token 差异不能解释为相对现有工作流的节省，也不能归功于独有算法。

已运行的网络请求仅限列明的 26 个网页和 robots 文件，Scrapy 与 Scrapling 静态/浏览器各一轮。浏览器还会加载网页自身资源。另匿名复测 Jina 的两个本地失败页面。没有测试新学院的入口发现、自动翻页执行、跨学院去重、人工复核 UI 或交付表格。

官方资料：

- https://docs.scrapy.org/en/latest/
- https://github.com/D4Vinci/Scrapling
- https://github.com/ScrapeGraphAI/Scrapegraph-ai
- https://jina.ai/api-dashboard/pricing/
