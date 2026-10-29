# Mission C：工具资料核对与新主页便利样本

日期：2026-10-27（Asia/Singapore）。角色：research 资料代理；本文件只交付官方资料和样本查证，不实施适配器、不合并、不审查代码。需求与基线由主代理提供：`7a544cd482c2eb20a1fbad4fb7c3aeadf3f0bef5`。原版兰州交通大学目标页 HTTP 412 属于主代理实跑结果，资料代理没有重复请求该页。

## 范围与方法

已读仓库 AGENTS.md、CONTEXT.md、experiments/README.md、docs/agents/workflow.md 和实际 `C:/Users/27451/.codex/skills/research/SKILL.md`。依 research 技能，本文以第一方文档、第一方源码和大学官网为证据。任务路线、Issue、集成与验收由主代理负责；本角色只写本文件，不改 Git、不读取密钥、不调用收费 API。Jina 仅保留，Firecrawl 托管调用未经本轮单独授权，二者均未测试。

检索先使用 Context7 resolve，得到 `/unclecode/crawl4ai`、`/apify/crawlee-python`、`/microsoft/playwright-python`，分别查询全文、浏览器与 robots 用法。达到本题三次 resolve/query 限额后，Trafilatura 直接读第一方文档。Crawlee 在线 API 当时显示 1.11，故不能直接冒充本机 1.10.4；以下关键参数另用已安装包签名及源码只读核实。

已安装环境：`D:/Agent Workspace/Intern/MyPlan/OpenSource/.venv/Scripts/python.exe`。`importlib.metadata.version` 实际输出：Crawl4AI **0.9.4**、Crawlee **1.10.4**、Playwright **1.64.0**、Trafilatura **2.3.1**。没有安装或升级任何包，没有运行下面的采集工具示例。

## 四种工具与全文保留

### Crawl4AI 0.9.4

它把浏览器读取、HTML 清理和 Markdown 生成组合起来。`result.html` 是留存网页证据的关键；`cleaned_html` 已经过清理。`raw_markdown` 表示对所选 HTML 的未过滤 Markdown 转换，不能仅凭名字认定它来自原始 HTML；本机 `DefaultMarkdownGenerator` 的 `content_source` 默认实际为 `cleaned_html`。应显式用 `content_source="raw_html"`，另存 `result.html`。`fit_markdown`/`fit_html` 是内容过滤结果，可能丢掉履历、短字段或末尾成果，不能当作完整简介。Markdown 转换仍不是逐字保真的 HTML 归档。[CrawlResult 官方说明](https://github.com/unclecode/crawl4ai/blob/main/docs/md_v2/api/crawl-result.md)、[0.9.4 主流程源码](https://github.com/unclecode/crawl4ai/blob/v0.9.4/crawl4ai/async_webcrawler.py)、[Markdown 官方源码](https://github.com/unclecode/crawl4ai/blob/main/crawl4ai/markdown_generation_strategy.py)。

本机额外核实：`BrowserConfig.enable_stealth=False`；`ignore_https_errors` 默认却为 True，正常读取对照应显式改 False。`CrawlerRunConfig.check_robots_txt` 默认 False，应显式 True；`magic`、`simulate_user`、`override_navigator` 保持 False。没有使用验证码绕过、代理轮换或 stealth。[配置官方源码](https://github.com/unclecode/crawl4ai/blob/v0.9.4/crawl4ai/async_configs.py)。

最小调用要点（放在 async 函数内；保存路径和 URL 由调用方显式提供）：

```python
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

browser = BrowserConfig(headless=True, enable_stealth=False,
                        ignore_https_errors=False)
run = CrawlerRunConfig(check_robots_txt=True, max_retries=0,
    markdown_generator=DefaultMarkdownGenerator(
        content_source="raw_html", content_filter=None))
async with AsyncWebCrawler(config=browser) as crawler:
    result = await crawler.arun(url=URL, config=run)
    # 先记录 success/status_code/error_message，再核对正文和末段。
    html = result.html
    markdown = result.markdown.raw_markdown if result.markdown else ""
```

`result.html` 是浏览器获取的 HTML；需要服务器响应字节、子资源或附件时，还须独立保存对应原件，不能声称 Markdown 已包含这些材料。

### Crawlee 1.10.4

它主要提供请求队列、处理器、浏览器与存储管理；`PlaywrightCrawler` 适合需要 JavaScript 的页面，静态页可用 HTTP/BeautifulSoup crawler。它不会自动产出满足项目契约的完整教师简介；应在处理器中保存 DOM，另保存主响应，并自行核对字段和末段。不要在本轮单页样例调用 `enqueue_links()`。[官方用法](https://github.com/apify/crawlee-python/blob/master/README.md)、[PlaywrightCrawler 官方 API](https://crawlee.dev/python/api/class/PlaywrightCrawler)。

1.10.4 实际参数名是 `respect_robots_txt_file`，不是 `respect_robots_txt`。本机默认 `retry_on_blocked=True`、`max_request_retries=3`、`max_session_rotations=10`；本轮应明确关闭自动阻挡绕过和自动重试，并关闭指纹生成。`Configuration` 从 `crawlee.configuration` 导入；存储目录放本次独立输出，不复用其他任务队列。robots 允许性与 crawl-delay 是不同事项；本机源码提示一般请求管理器不会自动执行 crawl-delay，需要相应节流请求管理器或主动限速。[固定 1.10.4 BasicCrawler 源码](https://github.com/apify/crawlee-python/blob/v1.10.4/src/crawlee/crawlers/_basic/_basic_crawler.py)。

```python
from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
from crawlee.configuration import Configuration

crawler = PlaywrightCrawler(
    configuration=Configuration(storage_dir=ISOLATED_STORAGE),
    max_requests_per_crawl=1, max_request_retries=0,
    max_session_rotations=0, retry_on_blocked=False,
    respect_robots_txt_file=True, fingerprint_generator=None,
    use_session_pool=False, headless=True)

@crawler.router.default_handler
async def handler(context: PlaywrightCrawlingContext):
    html = await context.page.content()  # 完整当前主框架 DOM，非摘要
    await context.push_data({"url": context.page.url, "html": html})

await crawler.run([URL])
```

本段只是用法要点，没有把其浏览器管理、队列成功或 handler 成功当作正文完整性证据。

### Playwright 1.64.0

它是浏览器自动化基础层，适合正常打开页面后读取 DOM、等待明确的正文节点或保存截图。`page.content()` 返回当前主框架完整 HTML（含 doctype）；DOM 与最初服务器响应可能不同。主资源 `response.body()` 适合作为另一份响应证据；iframe、附件和滚动后才加载的内容需单独检查。它不自动做教师正文识别，也不自动执行 robots 规则。[Page 官方 API](https://playwright.dev/python/docs/api/class-page#page-content)、[Response 官方 API](https://playwright.dev/python/docs/api/class-response#response-body)、[Python 官方源码](https://github.com/microsoft/playwright-python/blob/main/playwright/async_api/_generated.py)。

```python
from playwright.async_api import async_playwright

# 先在外层检查 robots；拒绝、无法确认的失败情形保留原因。
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(ignore_https_errors=False)
    response = await page.goto(URL, wait_until="domcontentloaded")
    # 如有正文 selector，等待它；不靠固定延时证明内容已齐。
    html = await page.content()
    response_bytes = await response.body() if response else b""
    await browser.close()
```

`networkidle` 不应被当作通用内容就绪判据；官方文档明确不推荐依赖它。正常浏览器仍可能得到拦截页、空 DOM 或 HTTP 412，均需如实标注。

### Trafilatura 2.3.1

它对已经取得的 HTML 做正文抽取，也有 HTTP 下载辅助函数；不是 JavaScript 浏览器。`favor_recall=True` 偏向保留更多内容，`include_tables=True` 保留表格候选，`include_links=True` 带上链接，仍不保证每个教师字段或全部末段都留下。`deduplicate=False` 避免主动合并重复段落；原 HTML、附件仍要单独存。不能把抽取文本称为原始网页全文。[2.3.1 官方核心函数文档](https://trafilatura.readthedocs.io/en/latest/corefunctions.html)。

```python
import trafilatura

# html_bytes 来自已检查 robots 的正常 HTTP/浏览器读取；先保存它。
text = trafilatura.extract(html_bytes, url=URL, output_format="txt",
    favor_recall=True, include_tables=True, include_links=True,
    include_comments=False, deduplicate=False)
# None 是抽取失败；空值不能解释为官网没有简介。
```

共同验收：同时保存状态、最终 URL、时间、原 HTML/响应与抽取输出；逐项检查姓名、职称、本人邮箱、学校/学院关联、正文开头及末段。四工具的成功信号都不能证明学院采齐。正文中链接到附件并不等于附件正文已被纳入。

## 新样本搜索与选择记录

这是**便利抽样，不是统计随机抽样**。没有随机种子、抽样框或入选概率；有搜索排名偏差，且为小规模工具对照有意选不同 HTML 结构。首次并行搜索精确查询如下：

1. `site.edu.cn 师资 教授 电子邮箱 个人简介 王`
2. `site.edu.cn 教师 个人主页 教育经历 科研成果 联系方式`

工具把两查询结果合并返回。结果顺序中，何剑约为个人页第1个、李艳青第2个、王健第3个、张惠芳第5个、王丽萍第9个；并非学校内随机教师。实际选择顺序为：何剑（个人站点模板）→王健（学院长文章）→张惠芳（表格及长成果清单）→王丽萍（带 uid 的详情页，动态候选但未证实）。王丽萍失败后，以同次搜索已出现的李艳青作为第4个可读取样本。检索候选 URL 时，对 experiments 使用 `rg` 没有命中，因而没有拿既有试验名单充当新样本；“未命中”仅限该目录可搜索文件，不宣称检查了所有外部历史。

随后为替补预备又作 `site.hust.edu.cn "教授" "个人简介" "邮箱" "研究方向"` 与 `site.swjtu.edu.cn "个人简介" "电子邮箱" "教授"` 搜索，返回 HTML/PDF 候选；但李艳青已通过普通 HTTP 成功，故未读取或纳入额外主页，未借机扩成更多样本。四个最终样本都属于常规 HTML；本轮没有确认必须动态渲染或正文依赖附件的样本，不把 URL 参数或 script 标签误判为动态，也不为凑类型追加读取。

读取控制：每个最终主页一次 web open、一次普通 urllib 请求，共至多两次；没有读取名单页面或跟进个人链接。web 工具读取 robots 不可用时，回退一次普通 urllib；五个候选站点（web.suda、electric.ncepu、physics.shu、math.ecnu、faculty.ecnu）的 `/robots.txt` 都返回 HTTP 404。此事实只表示这次没有取得 robots 文件，不表示站点对所有用途作出授权。本轮没有绕过访问控制、忽略 TLS 错误、爬学院或深爬。请求是低量单页核对；实际工具对照由主代理另行执行并记录请求次数。

### 1. 何剑：苏州大学未来科学与工程学院

- URL / 第一方来源：[官方个人主页](https://web.suda.edu.cn/hj1/)。
- 普通 HTTP：200，响应 56,322 字节；姓名和内容在初始 HTML 中存在。
- 可核对字段：姓名何剑；标题为教授；学院为未来科学与工程学院；本人邮箱 `drhejian@suda.edu.cn`。专业技术职务一栏本身为空，职称应指向页首/简介证据，不能假称该空栏有值。
- 结构：个人资料、教育/工作经历、简介、研究领域、课程、项目、论文、专利、荣誉及招生。多段分区都应保留，不能只取“个人简介”。
- 末段核对标记：招生专业含 `085501`；随后出现 `drhejian@suda.edu.cn`。这比只检查首段姓名能发现更靠后内容丢失；页脚与重复联系方式不必算个人简介。
- 未见明确的页面更新时间，不用工作经历日期、论文年份或版权年份冒充材料日期。

### 2. 王健：华北电力大学电气与电子工程学院

- URL / 第一方来源：[官方教师信息](https://electric.ncepu.edu.cn/szdw/jsxx/gdyyjyjsyjs/a207300faea944298a27ba0a6d0c6c7b.htm)。
- 普通 HTTP：200，响应 136,513 字节；主要教师正文在初始 HTML 中。
- 可核对字段：姓名王健；教授；博士生导师资格另记；院系为电气与电子工程学院、高电压与绝缘技术研究所；本人邮箱 `wangjian31791@ncepu.edu.cn`；页面日期 2025-10-09。
- 结构：大量导航后才到正文；含简介、学术兼职、教学/招生、成果。不能把导航里其他机构混到教师归属。
- 末段核对标记：参考清单 `[50]`，末条页码 `4623-4633`；正文后才出现学院版权和办公地址。只保留首个简介段会漏掉明显的后续成果。

### 3. 张惠芳：上海大学理学院物理系

- URL / 第一方来源：[官方教师个人主页](https://physics.shu.edu.cn/info/1082/5653.htm)。
- 普通 HTTP：200，响应 68,065 字节；身份表格与长正文都在初始 HTML 中。
- 可核对字段：姓名张惠芳；副研究员；硕士生导师资格另记；本人邮箱 `hfzhang1967@shu.edu.cn`；学校/学院系由页面标题、地址及工作经历支持。页面明确发布时间 2023-06-25。发布人张晓智是另一人，不能误作教师姓名。
- 结构：字段表格、学习工作经历、代表论文、专利、科研项目、毕业学生、其他。表格抽取质量与长列表末段都值得检查。
- 末段核对标记：`其他`段最后包含“鼓励和督促学生学习考研”；其后是上一篇/下一篇导航，应划出教师正文边界。

### 4. 李艳青：华东师范大学物理与电子科学学院

- URL / 第一方来源：[官方教师个人主页](https://faculty.ecnu.edu.cn/_s41/lyq2/main.psp)。
- web open 超时；随后普通 urllib HTTP 200，响应 26,213 字节。正文在初始 HTML 中，故本次普通 HTTP 成功不能被 web 工具超时覆盖，也不能据此推断所有客户端都成功。
- 可核对字段：姓名李艳青；教授；页面部门写物理与电子科学学院；本人邮箱 `yqli@phy.ecnu.edu.cn`。浏览器标题写物理学院，与部门字符串不同，保留各自来源，不直接用标题覆盖部门。
- 结构：个人资料、教育/工作经历、个人简介和研究方向；后面若干模块标题无对应正文，不能凭标题编造内容。
- 最后有内容的研究方向标记：“柔性光电材料与器件集成”。其后课程、项目、成果等空模块及页脚不视作额外履历。HTTP 文本中还有注释里的模板内容，直接剥标签会把注释带进文本，提取时须区分可见文本和源码注释。
- 未见明确材料更新时间，保留未验证状态。

### 未入选候选：王丽萍

来源为同次搜索找到的[华东师范大学数学科学学院详情页](https://math.ecnu.edu.cn/facultydetail.html?uid=lpwang)。搜索摘要称王丽萍、教授/博导、邮箱 `lpwang@math.ecnu.edu.cn`，但页面两次读取分别是 web timeout 与普通 urllib TLS `UNEXPECTED_EOF_WHILE_READING`，因此这些摘要字段**尚未由本轮主页正文核实**，也没有末段依据。保留失败，未忽略 TLS、未继续重试、未将其称为动态抓取成功样本。

## 交付限制

上述 4 个最终 URL、字段和末段标记已传给主代理，供同 URL 工具对照。资料代理只做查询、只读包核对和低量公开网页阅读；没有执行 Crawl4AI/Crawlee/Playwright/Trafilatura 的联网采集，没有保存或覆盖主代理原件。普通 HTTP 响应长度是该次读取事实，不是永久内容长度，也不是完整性评分。浏览器工具、代理或地域不同可能返回不同内容；主代理应留存其运行原件并核对差异。

本文件是研究交付，不能替代正式适配器验证、字段裁决、独立审查、CI 或整院完整性证据。
