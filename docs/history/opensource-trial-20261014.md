> 历史说明，保存于 2026-10-21；正文中的当前状态指当时实现。实际使用请从 [当前项目入口](../../README.md) 开始。

# OpenSource 对照试验

首轮结论、候选项目及证据入口见 [REPORT.md](../../REPORT.md)。本目录用于比较开源组件获取网页、名单和个人页的能力；业务定义仍以 [CONTEXT.md](../../../CONTEXT.md) 为准。

## 本机运行

已在 `.venv` 安装 Crawl4AI 0.9.4、Crawlee 1.10.4、Trafilatura 2.3.1。全部依赖锁在 `requirements.lock`。对照脚本运行后退出；新增的实时采集与人工复核工作台按 [WORKBENCH.md](../../WORKBENCH.md) 启动。Docker 引擎未启动，因此使用独立 Python 环境。

在本目录打开 PowerShell：

```powershell
# 重建环境（需要 Python 3.12 和 uv）
.\setup.ps1

# 本地保存页回放，不访问学校网站
.\run.ps1 -Mode replay

# 小范围访问：一份名单及前三个个人页
.\run.ps1 -Mode live

# 获取对照：4个固定名单页面，HTTP与浏览器各访问一次
.\.venv\Scripts\python.exe acquisition.py

# 跟进湖南中医药大学信息学院名单分页及其个人链接
.\.venv\Scripts\python.exe faculty_pilot.py
```

`acquisition.py` 使用本机 Microsoft Edge 的独立无头实例，未连接用户浏览器会话。Crawl4AI 0.9.4 在这里需设置 `chrome_channel='msedge'`；仅设置 `channel` 会尝试不存在的默认 Chromium。其他机器需安装 Edge 或调整浏览器配置。

`faculty_pilot.py` 的入口和名单选区已配置；从真实“下页”链接跟进，最多10份名单页、100个同站个人页；超过范围会记录，原观察保留。它是单站实验适配器，不是自动判型或通用学院采集器。73仅作为用户提供的对照数，不控制停止条件。

每次执行建立独立 `runs/时间-模式/`，原件、SHA256、输出和状态保留在该目录。`inputs/`、`runs/`、虚拟环境和缓存被本目录 `.gitignore` 排除，实验数据不进入生产数据库。

## 怎么判断这轮有没有价值

先检查原始页面、实际名单分页及个人链接有没有取得，再评估需要多少配置和人工介入。正文清理、字段分类和归属核验分开比较。重点读 `faculty-pilot` 的 `summary.json`、`records.json`、`pages.json` 和每页的 `source.html`；正文另存 `body-text.txt` 和工具生成的文本。

保存页回放使用现有回归材料，不能当作未见网站验证；正文节点保留指标不衡量导航污染或字段正确性。HTTP 200、HTML非空和人数对上均不能单独证明全院完整。

早期普通HTTP实验启用 robots 允许/禁止检查，并串行执行，但没有接入 Crawlee 的 `ThrottlingRequestManager`，不自动执行 robots 的 Crawl-delay。后续阜阳试验已接入该机制，并保留请求前等待2秒。仍未验证进程崩溃后恢复、登录、验证码、扫描件OCR或同URL的AJAX翻页。

## 阜阳师范大学化材学院试采集

2026-10-14 的结果见 [试采报告](../../runs/20261014-091002-654625-fynu-collection/report.md)、[逐姓名查阅](../../runs/20261014-091002-654625-fynu-collection/records.md)。四个师资分支共16份名单页，另有一份文本型博士PDF；136个不同姓名中98个有对应标题的正文。身份同一性与当前在职范围未逐人确认，全院完整性未验证。

脚本分工：

- `fynu_probe.py`：读取首页及其明确链接的四个师资栏目；也可以传入指定URL做有限补查。
- `fynu_collect.py`：本次单站适配器，跟随真实分页并保存个人链接结果。固定复用本机两次探测和PDF目录，路径在文件顶部；需要这些原件才能复跑，不是通用学院采集器。
- `fynu_browser_check.py`：用独立Edge实例比较一个公开页面和一个权限提示页面。
- `fynu_report.py <运行目录>`：只读原件做离线核对，输出姓名索引、逐URL记录和报告，不重抓网站。它也依据原件补核首次运行遗漏的末页控件状态。

本轮的权限失败与无链接姓名均保留；没有为了得到更干净的文本丢弃记录。原始HTML、PDF、页面全文和来源保存在运行目录，可重新提取。Excel结果含姓名索引、个人页面、来源观察三个工作表；正文全文保存在表中对应的本地文本文件。

## DeepSeek API试验入口

`api_pilot.py` 从大学、学院和首页网址开始。模型选择已观察到的师资入口，返回名单、分页和正文的CSS规则；程序执行这些规则，保留原件。富文本名单和文本PDF由模型读取姓名，并检查姓名与引用是否确实存在于原文。历史名单只用于采集结束后的独立对照。

本机采用 `https://api.deepseek.com` 的OpenAI兼容格式，默认 `deepseek-flash`，关闭思考模式并请求JSON。模型列表及实际请求/返回保存在每次运行的`api/`下，密钥不写入这些材料。

Windows上的密钥已通过DPAPI加密存入 `.secrets/deepseek-api-key.dpapi`，该目录被Git忽略，只能由当前Windows账号解密。启动器仅在子进程运行期间注入`DEEPSEEK_API_KEY`。已有环境变量时优先使用环境变量；密钥不会进入命令行参数。不要将DPAPI文件直接当作服务器凭据复制。

```powershell
# 本机重新试采
.\secure-api-run.ps1 -PythonArgs @(
    'api_pilot.py', '--university', '阜阳师范大学',
    '--college', '化学与材料工程学院',
    '--url', 'https://www.fynu.edu.cn/hxycl/'
)

# 不访问网络的边界检查
.\.venv\Scripts\python.exe test_api_pilot.py
```

服务器使用进程环境变量或服务器的密钥管理机制提供`DEEPSEEK_API_KEY`，然后直接执行同一Python入口，不依赖Windows启动器。这只说明接口支持无交互运行；尚未部署服务器服务、计划任务或生产队列。

独立 CLI 默认上限为200个网页、20次模型调用、5个名单PDF附件；个人页PDF另有200份上限，每份不超过20 MiB和50页，仅同域访问。页码显示未到末页而下一页规则无匹配时，将失败规则和当前页面交回API重规划一次。仍失败、空入口、空正文、权限提示、图片未识别均记录为未解决项，不作为无师资结论。已增加浏览器空正文/名单兜底（可用 `--no-browser` 关闭），`--ocr` 启用本地图片与扫描PDF识别；邮箱和职称仍仅保留候选值。工作台的预算与复核流程见 [WORKBENCH.md](../../WORKBENCH.md)。

PDF读取新增 `pypdf==6.10.0`。本机PyPI轮包下载遇到TLS连接中断，本次从Codex附带的同版本Python包复制到独立虚拟环境，未改动附带运行环境；常规环境仍按`requirements.lock`安装。

首轮API试验见 [分页失败记录](../../runs/20261014-094801-940441-api-pilot/report.md)。模型将首页路径片段写进下一页选择器，导致只到达7份名单页；虽然PDF使姓名集合仍为136个，实际仅60个姓名取得正文。这个例子说明人数相同不能替代分页、个人链接和正文对账。

修订后的 [完整API试采](../../runs/20261014-095235-009606-api-pilot/report.md) 使用8次API调用，从首页取得16份名单页、136个姓名和98个姓名对应的107份正文，耗时约5分50秒。输入21051 token、输出6031 token，按当时官方峰时价估算约$0.0113；连接测试及两轮试验的合计用量另见该运行目录的`session-api-usage.json`。修订后的真实运行没有再次触发分页重规划；该分支由5项离线检查中的相对链接失败案例验证，不能把离线验证说成实际触发。
