# Mission C · 教师个人主页采集

输入个人主页 URL，独立保存姓名、邮箱、职称、完整简介、研究方向与发表信息。整个目录可搬离主项目使用，不依赖工作台数据库、任务 A/B、旧 MyPlan 或 API 密钥。这是命令行脚本包，没有独立前端页面。

与主工作流的关系：复用了同款 HTTPX、BeautifulSoup、Playwright、pypdf、RapidOCR/pypdfium2 及四个本地判定/媒体模块；独立入口重新组织了调用。主流程的 Crawlee 队列和 DeepSeek 页面选区未移入本包，陌生页面改用可核对的容器规则与 `--selector`。因此它不是主流程逐行拆出的等效副本，不能直接沿用主流程的适配结论。

## Windows 使用

需要 Python 3.11+，已在 Python 3.12 验证。首次在本目录运行 `setup.bat` 安装基础依赖；需要动态页面和图片识别时运行 `setup.bat --full`。Windows 浏览器读取使用本机 Edge。

先用虚构样本检查安装，全程离线：

```powershell
cd "D:\Agent Workspace\Intern\MyPlan\OpenSource\Mission C"
.\run.bat --url "https://example.edu/teacher" --html ".\examples\teacher.html"
```

真实采集时替换以下个人主页地址：

```powershell
.\run.bat --url "https://学院网站/教师个人主页" --school "学校名称" --college "学院名称"
# 可选：在上述命令末尾添加 --render --ocr
```

这会访问指定网页及同主机 PDF 附件。`--render` 读取动态正文；`--ocr` 本地识别图片和扫描 PDF，结果保留为待复核候选。脚本不调用大模型或付费 API。

批量使用 `--urls-file ".\inputs\urls.txt"`，文件为 UTF-8、每行一个 URL，也可重复传入 `--url`。相同 URL 去重；不同 URL 不按同名合并。学校/学院是调用者提供的元数据，适用于本次全部输入，脚本不会凭域名猜归属；不同学校或学院应分批运行。

默认结果存入本目录 `outputs/时间-随机标识/`。`--output` 可指定尚不存在的目录，已有结果不会覆盖。退出码 `0` 表示各页取得文字，`1` 表示至少一页未取得文字，`2` 表示参数/文件错误；退出成功不代表已核实完整性。

其他平台或自行管理 Python 时，安装 `requirements.txt` 后执行 `python collect.py ...`。浏览器/OCR 分别安装对应可选依赖文件；非 Windows 浏览器另需 `python -m playwright install chromium`。全部参数见 `python collect.py --help`。

## 输出与复核

| 文件 | 内容 |
| --- | --- |
| `teachers.json` | 全部结构化记录、未截断简介、字段候选证据、媒体与失败状态 |
| `teachers.csv` | 中文字段、完整简介、研究/发表栏目、状态及原件路径，UTF-8 BOM |
| `teachers.xlsx` | 按项目十列、三个 Sheet 展示待复核结果，姓名批注注明状态 |
| `0001/biography.txt` | 正文及已读取附件的完整原文，保留 OCR 待复核标记 |
| `0001/source.html`、`record.json` | 原始响应字节、来源 URL、读取时间、SHA-256 和字段证据 |
| `0001/content.html`、`page.txt` | 选取的正文 HTML 和页面文字，用于核对正文边界 |
| `0001/rendered.html`、`media/` | 可选的渲染原件、已下载附件、逐页文字和 OCR 信息 |

Excel 简介超长时明确指向全文 TXT，JSON/CSV/TXT 始终保留全文。CSV 的公式样式文本会加文本前缀；JSON/TXT 保留原文。研究/发表字段按可识别栏目拆出，其他内容仍在完整简介中。

这是任务 C 的中间结果。主工作台的最终教师交付还需要身份、学校/学院归属、名单范围、替代主页及学院完整性证据。姓名冲突不会用输入值强行填补，导师资格不当职称，可识别的公共邮箱和论文联系人不当本人邮箱；复杂页面的字段候选仍需核实。

## 完整原文的范围

保留已取得正文与附件的原文，不作摘要或按字符数截断。先识别已知个人页模板，再选择唯一主内容容器；多个容器或边界不明时保存较宽的页面文字并标记待核实。可用 `--selector` 指定一个唯一正文容器，通过 `content.html` 与原件检查是否漏栏目。

同页已有的简介、研究、论文等一并保留。需点击标签、展开按钮、分页或其他 URL 才出现的内容不会自动遍历，相关链接/嵌入媒体保留在记录中；`--render` 仅取得初次加载后的 DOM。额外个人页可另行输入，并核对关联。

单次响应限 20 MiB、PDF 限 200 页、附件读取最多 100 项；超限留下缺口，PDF 解析失败保留已下载原件。附件仅自动读取与最终个人页同主机的 HTTP(S) URL；跨主机、嵌入页、未启用 OCR 的图片、robots 拒绝与访问失败分别记录。`--html` 严格离线，不执行网页脚本、不读取网络附件。

已验证合成样本的长简介、多栏目、字段归属、PDF、动态页面、本地 OCR、失败隔离和目录独立运行。另完成指定主页与四个新主页的 [有限真实对照](https://github.com/normaltank/NewPlan/issues/22)，本地结果在 `outputs/live-tools-20261027/`。单页读取和工具输出仍不代表任意网站适配或全院采齐；主包没有自动接入这些实验工具。

后续[固定20页多结构对照](https://github.com/normaltank/NewPlan/blob/codex/mission-c-live-tools/experiments/mission-c-diverse-20261027/REPORT.md)复用旧五页，新增15页Fetch与代表浏览器/框架、3张当前图OCR/Docling；总报告、机读摘要和证据索引位于 `outputs/diverse-pages-20261027/`。新增PDF本机转换及分立CV/论文导航仍未验证；全部为保留缺口的实验候选。

## 维护

基础验证：`python -m unittest discover -s tests -v`。安装可选依赖和浏览器后，设置环境变量 `MISSION_C_OPTIONAL_TESTS=1` 运行同一命令，加入动态页面和 OCR 验证。样本为虚构；网络用例只访问临时 `127.0.0.1` 服务。

字段判定、姓名形态、已知模板及 OCR 模块来自 `normaltank/NewPlan` 提交 `645ef433766580777c76946a157494631381a2c5` 的根模块；字段/模板模块仅调整相对导入。独立入口、采集和导出由本目录维护，主工作台调用链未改。任务与验证见 [Issue #20](https://github.com/normaltank/NewPlan/issues/20)。
