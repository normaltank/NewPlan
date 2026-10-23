# 第一批工具隔离试验

用户授权测试 Firecrawl、Jina Reader、Docling，要求版本隔离。目录内保存小样本获取与解析比较；不修改生产、不重排旧工单、不写入原数据库，也不把单页结果冒充整院验收。

## 范围

- 26 个网页：16 个既有个人页反例/对照、7 个官方师资名单页、1 个内嵌 PDF 栏目、2 个新教师页。
- 网页提供方另读同一份三页 PDF 地址，共 27 个 URL。
- Docling：1 份多人 PDF、2 张真实图片简历、1 张带牌匾文字的人像照片；另加 PDF 第一页的栅格化扫描对照，共 5 次本地转换（4 份独立原件）。
- 已有 DS Fetch 的保存结果只作历史参照，不产生新的 DS 调用。当前普通 HTTP 读取用于核对网页变化，不等同于原系统的浏览器采集能力。

## 版本与隔离

- `.venv-web/`：单独安装网页试验依赖，完整版本见 `requirements-web.lock`。
- `.venv-docling/`：Docling 2.140.0，完整版本见 `requirements-docling.lock`。
- `models/` 和 `.cache/`：试验专属模型、下载缓存；模型文件哈希保存在 `versions.json`。
- Firecrawl 通过已有 MCP 访问托管服务；Jina 通过匿名 HTTPS 访问托管服务。不能锁定托管服务内部版本；请求配置、时间、工具 Schema、完整响应均保存，避免将客户端隔离误称为服务端版本固定。
- `baseline-before.json`、`baseline-after.json`、`isolation-check.json` 核对原代码、原依赖元数据及原人工决定。试验内无教师任务数据库。

## 复现与检查

请复制试验代码到新的同级目录后运行新采集，保留当前证据不覆盖。`prepare.py` 遇到已初始化目录会拒绝重新准备。

两个环境分别使用 Python 3.12.10，通过 `uv pip sync --python <对应环境的 python.exe> <对应 lock 文件>` 恢复。`web_runner.py` 支持原始 HTTP、Jina 自动正文、完整 Markdown、HTML 等独立配置，并可用 `--ids` 限定样本。Firecrawl 每次工具请求与完整响应保存在 `results/firecrawl/`；实际工具定义在 `firecrawl-tool-schema.txt`。

`docling_runner.py` 将中文 OCR、版面及表格模型下载到本目录，限制为 CPU 4 线程。`evaluate.py` 比较明确证据点保留、名单链接和嵌入资源；`evaluate_documents.py` 对照姓名、职称、邮箱行绑定，并保留解析器原始输出。原始返回与实验性整理分开保存。

测试入口：`.venv-web\Scripts\python.exe -m unittest -v test_adapters`。这些测试使用本次实际原件和响应，覆盖跨页表头、破碎 Markdown 姓名、嵌入 PDF 发现和扫描表格字段，不能代替整院完整性验收。

## 判断边界

姓名/邮箱出现在正文中，不代表已经正确提取并绑定到教师。每个学院是否采齐、动态分页是否全部执行、身份去重和最终三个 Sheet 的交付，均未在本轮重新验收。新页面只验证当前阅读配置，不代表新学院已验收。正常材料与失败材料都纳入比较，不将历史基线默认当作真值。

官方资料：

- [Firecrawl 页面获取](https://docs.firecrawl.dev/features/scrape)
- [Jina Reader 输出格式和请求头](https://github.com/jina-ai/reader)
- [Docling 高级配置](https://docling-project.github.io/docling/usage/advanced_options/)
- [Docling OCR](https://docling-project.github.io/docling/concepts/OCR/)

结论、实际费用计量与可查看的差异见 `REPORT.md`、`usage.json`、`summary.json`。本目录的整理适配没有发布到正式采集链。
