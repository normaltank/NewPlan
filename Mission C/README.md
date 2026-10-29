# Mission C · 教师个人主页采集

输入个人主页 URL 或原格式双 Sheet Excel，独立保存姓名、邮箱、职称、完整简介、研究方向与发表信息。整个目录可搬离主项目使用，不依赖工作台数据库、任务 A/B、旧 MyPlan 或 API 密钥。提供操作页面、持久批次和 Windows/Linux 后台入口。

## 批次与操作入口

交服务器同事的精简包从源码目录运行 `python build_server_package.py --output "Mission-C-server.zip"` 构建；PRIVATE 预配置、唯一 run.py 入口与逐文件说明见 [SERVER.md](SERVER.md#服务器同事精简包)。精简包只含17个必要核心模块和四项基础依赖，操作说明随包独立交付。

Windows 首次执行 `setup.bat --web`，随后运行 `web.bat`；Linux 使用 `./setup.sh --web` 安装，再运行 `./web.sh`。打开显示的本地网址，默认是简化分发页：选择多份原表、预检、显式开始、查看进度、暂停/继续及按学校下载。关闭页面可恢复进度。使用者步骤见 [使用说明](使用说明.md)，维护配置及保留的完整工作台 `/workbench` 见 [WEB.md](WEB.md)。普通包默认不启用付费，私人包的预配置见 WEB；输入预检不访问表内网站。

先运行 `python batch.py --data-root "演示 data" demo` 验证虚构离线双 Sheet → 持久任务 → 大学 ZIP。大学教师工作簿保持三张表、十列；身份未确认、维护页、非个人页及无身份访问失败保留异常明细，完整原文与输入原件可在包内核对。任务完成不代表学院完整性已核实。

原格式 Excel、字段关联和公共批次命令见 [BATCH.md](BATCH.md)；无界面目录扫描、常驻队列、Windows/Linux启动与定时调用见 [SERVER.md](SERVER.md)。页面与后台必须配置同一个 `--data-root`；没有第二套运行队列。原单页 `collect.py` 和组合缓存 `replay.py` 继续按下文使用。

与主工作流的关系：复用了同款 HTTPX、BeautifulSoup、Playwright、pypdf、RapidOCR/pypdfium2 及四个本地判定/媒体模块；独立入口重新组织了调用。主流程的 Crawlee 队列未移入本包；陌生页面先用可核对的容器规则与 `--selector`，也可显式启用下述 DS 字段与选区辅助。因此它不是主流程逐行拆出的等效副本，不能直接沿用主流程的适配结论。

## Windows 使用

需要 Python 3.11+，已在 Python 3.12 验证。首次在本目录运行 `setup.bat` 安装基础依赖；需要动态页面和图片识别时运行 `setup.bat --full`。Windows 浏览器读取使用本机 Edge。

推荐先用组合入口检查安装，全程离线，实际消费虚构 Fetch 与模型响应：

```powershell
cd "D:\Agent Workspace\Intern\MyPlan\OpenSource\Mission C"
.\replay.bat
# 自行管理 Python：python replay.py
```

样本预期退出 `1`，因为其中一页原站历史失败，已有提供方待核正文；陈晨的本地全文、Fetch 补充和模型字段证据均可在结果中核查。`replay.bat` / `replay.py` 固定使用缓存、Fetch supplement 和模型 assist；缺缓存只报告缺失。默认输出目录遵循下述规则。原 `run.bat` / `collect.py` 继续支持单独读取与显式在线配置。

真实采集时替换以下个人主页地址：

```powershell
.\run.bat --url "https://学院网站/教师个人主页" --school "学校名称" --college "学院名称"
# 可选：在上述命令末尾添加 --render --ocr
```

这会访问指定网页及同主机 PDF 附件。`--render` 读取动态正文；`--ocr` 本地识别图片和扫描 PDF，结果保留为待复核候选。默认 Fetch 与模型辅助均关闭；提供方在线调用需要另外显式启用付费及预算。

批量使用 `--urls-file ".\inputs\urls.txt"`，文件为 UTF-8、每行一个 URL，也可重复传入 `--url`。相同 URL 去重；不同 URL 不按同名合并。学校/学院是调用者提供的元数据，适用于本次全部输入，脚本不会凭域名猜归属；不同学校或学院应分批运行。

默认结果存入本目录 `outputs/时间-随机标识/`。`--output` 可指定尚不存在的目录，已有结果不会覆盖。退出码 `0` 表示各页本地正文已保存，`1` 表示至少一页本地正文未取得（可能已有提供方待核候选），`2` 表示参数/文件错误；退出成功不代表已核实完整性。补充 Fetch 失败在 `fetch.error` 单独记录，已有本地全文仍可成功。

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

单次响应限 20 MiB、PDF 限 200 页、附件读取最多 100 项；超限留下缺口，PDF 解析失败保留已下载原件。附件仅自动读取与最终个人页同主机的 HTTP(S) URL；跨主机、嵌入页、未启用 OCR 的图片、robots 拒绝与访问失败分别记录。`--html` 从本地读取原件，不执行网页脚本、不读取网络附件；显式启用在线 Fetch 的条件见下节。

已验证合成样本的长简介、多栏目、字段归属、PDF、动态页面、本地 OCR、失败隔离和目录独立运行。另完成指定主页与四个新主页的 [有限真实对照](https://github.com/normaltank/NewPlan/issues/22)，本地结果在 `outputs/live-tools-20261027/`。单页读取和工具输出仍不代表任意网站适配或全院采齐；Fetch 按下节显式接入，其他工具仍是实验候选。

后续[固定20页多结构对照](https://github.com/normaltank/NewPlan/blob/codex/mission-c-live-tools/experiments/mission-c-diverse-20261027/REPORT.md)复用旧五页，新增15页Fetch与代表浏览器/框架、3张当前图OCR/Docling；总报告、机读摘要和证据索引位于 `outputs/diverse-pages-20261027/`。新增PDF本机转换及分立CV/论文导航仍未验证；全部为保留缺口的实验候选。

## Fetch 与严格离线缓存

先运行可搬移的虚构多 URL 样本：

```powershell
python collect.py --cache-manifest examples/assisted-cache/manifest.json --fetch-mode supplement --model-mode assist
# 等价的推荐入口：python replay.py
```

该样本预期退出 `1`：陈晨的本地最后一项成果保留，较短 Fetch 材料单独存放；周宁原站 `http_412` 保留，提供方原文以 `provider_candidate` 待核交付。陈晨的虚构模型响应实际核对字段并采用完整 `main` 选区；周宁没有模型缓存，`model.error.code=cache_missing`，字段保持缺失。单独 Fetch 材料不自动填字段。

`--fetch-mode off` 为默认关闭，`fallback` 仅在本地没有正文时读取 Fetch，`supplement` 也为已有本地全文保存独立材料。`fetch.mode/status` 记录实际选路。本地已取得文字始终保留；Fetch 差异、重复与额外段落可对照 `fetch-content.md` 核查，不自动拼接或压缩本地全文。

清单是 UTF-8 JSON：`{"version":1,"entries":[...]}`。每条 `entries` 用 `url` 绑定一份个人页，各 URL 独立失败；不传 `--url` 时使用全部条目，也可用重复 `--url` 或 `--urls-file` 选择子集。实际示例与 SHA256 见 `examples/assisted-cache/manifest.json`。

- `source`：`path`、`sha256` 为清单目录内的相对文件路径及原字节 SHA256，可附原 `observed_at`、`final_url`、`http_status`、`content_type`。原读取失败时用 `error:{code,message}`；若仍有失败原件，可同时给路径和 hash，它会保存但不作为正文解析。未知历史时间为 `null`，本次回放时间另记 `replayed_at`，不会冒充原采集时间。
- `fetch`：提供方原响应 `path`、`sha256`、`provider_http_status`，可附原 `observed_at`。响应应为含字符串 `content` 和可选 `title` 的 JSON；非成功状态、空内容、截断标记、畸形 JSON 均保留失败原响应。`origin_http_status` 始终未知，不把提供方 200 当成原站 200。响应无原时间时保持 `null`。
- `model`：模型原响应 `path`、`sha256`、`source_sha256`、可选 `observed_at`。默认 `source_kind: "html"`，绑定本次 HTML 原字节；仅有 Fetch 待核正文时须显式为 `"deepseek-fetch"`，绑定 `fetch-content.md` UTF-8 内容的 SHA256。类型或 hash 不匹配明确失败。默认 `--model-mode off` 只校验和保存响应；`assist` 才应用下节核验。

各项可额外给 `url`，必须与条目 URL 相同；响应自带 URL 时也须一致。SHA 不匹配、越界路径或缺缓存会明确失败。清单模式整个调用链严格离线，包括附件；即使给付费参数也不取环境密钥、不执行浏览器、不回退联网。清单不能与 `--html` 或 `--render` 同用。输入缓存保持只读，结果另存新目录。

`fetch.response_file` 保存提供方原 JSON/错误字节，`fetch.content_file` 保存未摘要的 Markdown；两者分别记录 SHA256。原件仍是 `source.html`，本地正文仍是 `biography.txt`。提供方成功也保留 `completeness: not_verified`。使用缓存只验证既有材料，不能证明当前网站状态或学院完整性。

### 导入历史缓存与搬移

已有只读库存时，先导入一个新目录，再运行组合入口：

```powershell
python prepare_cache.py --inventory "库存清单.json" --output "cache\historical20"
python replay.py --cache-manifest "cache\historical20\manifest.json"
# 或 .\replay.bat --cache-manifest "cache\historical20\manifest.json"
```

`prepare_cache.py` 的库存格式与运行清单分开：库存使用 `entries` 列表，每项给 `id`、`url`、`source:{path,sha256}` 或 `null`、`source_metadata` JSON 路径、`source_status:{http_status,error,text_saved}`，以及可选 `rejected_source:{path,sha256}`。`fetch` 给 `response:{path,sha256}`、`metadata` JSON 路径与 `provider_http_status`；可选 `model` 给 `response:{path,sha256}`、`source_sha256`、`source_kind` 和 `legacy_result` JSON 路径。库存路径可为绝对路径或相对库存所在目录；参考姓名不会用作 CLI 输入。元数据中的 URL 必须与条目一致。

导入先校验库存 SHA256，再复制原字节、文件修改时间与历史元数据。原站失败保留原错误；失败原件可以留存但不会作为成功 HTML。历史 `observed_at` 缺失时保持 `null`。生成的 `manifest.json` 只引用包内相对路径；`import-provenance.json` 的原绝对路径仅用于核对历史来源，运行不依赖它。输出目录必须尚不存在；复制中断后的目录保留供核查，重新导入使用另一新目录。

搬移时保留整个 Mission C 与导入后的缓存子目录，在新位置安装基础依赖即可运行；Python 环境按机器重新建立。运行不需要根工作台、旧输入路径、临时脚本或密钥。真实缓存含原始个人资料，只保存在受控本地；Git 中仅提供虚构样本。

上一版已在搬移后的独立包实跑历史 20 条，冻结基线的 13 份可用 HTML 逐页对照；实际数量、字段变化、网络阻断计数与媒体缺口见[缓存交付维护记录](https://github.com/normaltank/NewPlan/blob/main/docs/maintenance/2026-10-28-mission-c-assisted-cache/README.md)。该历史记录不把有文字或 HTTP 成功解释为全文完整率，也不是独立包的运行依赖。

## DS 字段与正文选区辅助

`--model-mode assist` 在附件读取与本地字段刷新后消费 chat 响应。缓存要求 `choices[0].finish_reason` 为 `stop`，`message.content` 为 JSON 字符串，格式如下；原样响应、用量、输入及响应 hash、提议与逐字段判定保存在 `model` 和 `model-response.json`。

```json
{"name":{"value":"陈晨","evidence":"陈晨"},"title":{"value":"教授，博士生导师","evidence":"职称：教授，博士生导师"},"email":{"value":"chen@example.edu","evidence":"电子邮箱：chen@example.edu"},"body_selector":"#profile"}
```

引用必须出现在可见来源中，并在个人身份范围内关联目标姓名。输入预期姓名未被确认且模型提议另一人时，保留身份冲突及字段待核原因。引用旁的独立他人标题会阻断向外借用身份；分散在相邻标题或 dt/dd 中的中英文公共邮箱、合作者标签同样参与核验。Fetch 纯文本出现多个独立个人身份时，模型字段保留待核，原文继续保存。已识别的侧栏、公共邮箱、论文合作者、师从与导师上下文不能作为本人字段；未知归属保留 `unconfirmed`。专业职称与导师资格分别记录为 `professional_value`、`qualifications`；已有可信值保留，模型相同时 `corroborated`，不同时 `conflict`。通过核验的缺失字段标为 `found_model_evidence`，其引用和输入 hash 另存 `field_evidence`。这些检查不代替人工身份与学院完整性核验。

CSS 必须唯一匹配、确认本人身份并包含现有完整原文；错误、多个匹配或会缩小正文的建议保留原文及具体原因。模型摘要不进入简介。Fetch-only 纯文本输入保留 `source_kind: deepseek-fetch`、原站失败与 `provider_candidate`，核验后的字段为 `provider_model_candidate`；CSS 状态为 `not_applicable_plaintext`。模型缓存缺失时明确失败，不伪造响应或联网。

## 显式在线 Fetch 与模型

不使用缓存清单时，启用 `--fetch-mode fallback` 或 `supplement`、`--model-mode assist` 中所需入口，并同时提供 `--allow-paid --paid-max-calls N --paid-attempts <持久目录>` 以及环境变量 `DEEPSEEK_API_KEY` 才可调用在线适配器。Fetch 与模型共用同一总预算及持久目录；兼容原 Fetch 的 `--fetch-max-calls`、`--fetch-attempts`，共享参数优先。默认预算为 0；沿用已有受控环境注入密钥，不将密钥写进命令行或日志。`--timeout` 约束提供方请求。`--html` 配合这些显式参数可只向提供方请求补充材料；原件和附件仍从本地读取。

适配器固定 `POST https://api.deepseek.com/v1/tools/fetch`，请求 `{"url":"..."}`。当前公开契约见 [DeepSeek Search & Fetch](https://api-docs.deepseek.com/guides/search/)。本项目验证使用虚构 HTTPX 外部边界，未以真实凭据探测在线服务。明确 robots 拒绝不会自动路由到在线 Fetch。

模型固定 `POST https://api.deepseek.com/chat/completions`，默认 `--model deepseek-flash --model-thinking disabled`，要求 JSON output，输入明确包含 URL、来源类型及 SHA256。模型可配置，不运行探测请求。接口和 JSON 模式契约参见 [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) 与 [JSON Output](https://api-docs.deepseek.com/guides/json_mode/)；本票只验证虚构外部 HTTPX I/O，未运行真实付费调用。

调用前原子保存 `fetch-<URL SHA256>.json` 或绑定 URL 与输入 hash 的 `model-*.json` 的 `unknown` 尝试；未指定 scope 的 CLI 将同一持久目录内所有已登记请求（含未知）计入预算；新私人方案显式开始的批次使用持久 scope 独立计数并保留全局尝试去重；旧队列和普通付费批次保持全局预算，不因升级自动取得 scope。同一操作/URL/原件哈希不自动重发。超时或断开仍保留未知状态，没有重试、probe 或重定向。并发锁残留时明确停止，需人工核对。保留该目录以跨运行防止重复付费，未知结局先核对提供方账单/记录。

完整响应保存后原子登记 `completed`，HTTP 失败也计为一次已完成尝试。文件只保存脱敏响应、状态、时间、用量（提供方有返回时）、原响应 SHA256 及落盘响应 SHA256；密钥回显含 JSON 转义时也脱敏，并标记 `response_redacted`。未知响应、超限和损坏材料不当成完整正文。

## 维护

姓名候选保留内部连字符和撇号，识别个人页标题后缀；学校前缀后的姓名需要正文身份范围内的同名文字佐证。排除已识别的栏目、研究组和学校名称，冲突仍留待核。已验证范围与剩余模板缺口见 [Issue #28](https://github.com/normaltank/NewPlan/issues/28)。

基础验证：`python -m unittest discover -s tests -v`。安装可选依赖和浏览器后，设置环境变量 `MISSION_C_OPTIONAL_TESTS=1` 运行同一命令，加入动态页面和 OCR 验证。样本为虚构；网络用例只访问临时 `127.0.0.1` 服务。

字段判定、姓名形态、已知模板及 OCR 模块来自 `normaltank/NewPlan` 提交 `645ef433766580777c76946a157494631381a2c5` 的根模块；字段/模板模块仅调整相对导入。独立入口、采集和导出由本目录维护，主工作台调用链未改。任务与验证见 [Issue #20](https://github.com/normaltank/NewPlan/issues/20)。

私人分发包的构建、预配置与共享边界见 [WEB 私人分发](WEB.md#私人分发)。普通源码包不含凭据。
