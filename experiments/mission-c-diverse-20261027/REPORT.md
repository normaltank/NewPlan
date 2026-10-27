# Mission C：20个固定教师主页的有限工具对照

2026-10-27；规格 [#24](https://github.com/normaltank/NewPlan/issues/24)，本票 [#27](https://github.com/normaltank/NewPlan/issues/27)。前置为[四页Fetch补测](fetch-four-report.md)与[新增15页独立基线](cohort-report.md)。这是结构分层的便利选样，失败页不换样；不代表统计随机、学院完整性或正式教师交付。

**本票15次Fetch全部落盘：14次提供方200且有文字，Hinton一次提供方504。正常Playwright、Crawlee HTTP、Crawl4AI各实际测试固定5页，Trafilatura离线处理9份原版HTML；RapidOCR与禁网本地Docling各处理当前3张原图。** Fetch取得文字不等于本人字段正确绑定或完整原文准确；中科大页明确漏掉整段本人简介和经历，图片页有识别差异。当前没有本地PDF二进制，PDF转换仍未验证。

## 查看结果

- [summary.json](summary.json)：20页URL、实际方法覆盖、原件/响应hash和时间、字段及局部正文证据、失败状态和调用统计。
- [EVIDENCE.md](EVIDENCE.md)：用户输出目录的简洁索引。大原件留在 `D:/Agent Workspace/Intern/MyPlan/OpenSource/Mission C/outputs/diverse-pages-20261027/`；本报告、摘要和证据索引也复制到该目录。
- [page-evidence](page-evidence/)：15页逐页原件定位、本人字段、首中尾与分节核对。用户输出中的同名目录另有**全部可见HTML长行**对照清单，包含导航噪声，不能把清单命中数当简介完整率。
- [image-comparison.json](image-comparison.json)：当前3图、前置票5个视觉参照的重新核查、OCR/Docling状态、版本、表格及定位。尾部媒体短参照经本轮复看有歧义，降为无法核实；其余4个清晰短参照均在3种识别文字中保留。
- `candidates/<id>/`：每人原始来源、未摘要的文字副本、本人字段解析结果和已知缺口。候选字段没有借预期姓名强制填补；学校/学院仍为输入元数据。图片OCR输出单独保存，未无声替换本人资料。

## 计费与运行边界

本票新Fetch **15次**，全轮新增 **19次**（前置四页4次+本票15次）；旧兰交大1次Fetch只复用缓存。旧五页所有Fetch均未重发。此前4次DS模型共35,767 tokens属于历史，**本票新模型0次**；Jina、Firecrawl、probe均0次。金额未查账单，不报估算费用。

每次付费调用通过既有DPAPI安全入口显式传脚本和参数；先独占创建 `attempt.json`，再发请求，45秒HTTP超时、无自动重试。15页均有最终 `result.json`，没有未知未决尝试；重复ID、缓存URL改变、未知attempt均拒绝调用。响应字节、提供方正文、SHA-256、开始/结束时间、失败与提供方状态保存；凭据不入文件。Fetch的原站HTTP状态全部为未知，提供方200不能替代原站状态。

其他工具只在固定5页或已有文件上运行，未整站发现、登录、验证码处理或stealth。Hinton保留robots/TLS/连接失败，浙大403保留为阻断结果，未绕过。Crawlee自身在robots文件网络失败后仍尝试目标页，运行时标准输出显示该过程；这是该框架本轮实际策略，不能称其robots规则已成功核实。其兼容HTTP客户端仅在特定TLS协商错误时切换到仍验证证书的HTTPX，重试配置为0不意味着这一兼容切换没有额外传输尝试。

## 方法和实际覆盖

原版Mission C对新15页的结果保持不变：9页存HTML/文字，6页 `robots_unavailable`。图片页的文字主要来自HTML标题，不能把 `text_saved` 当作图中简历已读取。

正常Playwright使用Edge普通无界面浏览器，校验证书、无stealth、导航30秒、额外networkidle最多8秒，读取前用原版规则检查robots。5页为浙大应晓英、南大周志华、大工许畅、淮北师大鲍相志、Toronto Hinton；前4页存HTML，Hinton未通过robots确认。浙大仅元数据和栏目，大工初始DOM与HTTP模板重复区不同；未执行展开/标签导航。

Crawlee使用BeautifulSoupCrawler和项目CompatibleHttpClient，单并发、配置重试0、session关闭、启用robots、处理器30秒；同5页中南大/大工/鲍存HTML，浙大403，Hinton TLS失败。日志同时提示未用ThrottlingRequestManager，robots的crawl-delay没有由框架自动执行；本次各固定URL只处理一次，另有1秒导航前间隔。未验证队列规模、分页或并发。

Crawl4AI同5页中南大/大工/鲍存HTML，浙大被识别为403阻断，Hinton连接关闭。参数为普通Edge、证书校验、stealth/simulate_user/magic关闭、重试0、页面30秒及外层50秒，首次 `CacheMode.BYPASS`，本地结果存在后复用；Markdown为 `raw_html`、无内容过滤器。HTML、cleaned HTML和原始Markdown分别保存。

Trafilatura只离线读取原版已保存的9份HTML，`favor_recall=True/include_tables=True/include_links=True`，原始提取文字在 `raw-extracted.txt`。它不负责本人字段。Crawlee的 `page.txt`来自共用Mission C页面解析；正常浏览器的 `raw-visible.txt`与Crawl4AI的 `raw-markdown.txt`是各自正文视图。**所有HTML方法的结构化姓名/职称/邮箱仍由同一个Mission C解析器生成**，换框架不是独立字段算法对照。Fetch只提供文字，字段出现位置与独立原件对照，没有冒充已执行结构化字段抽取。

版本：HTTPX 0.28.1、BeautifulSoup 4.15.0、Playwright 1.64.0、Crawlee 1.10.4、Crawl4AI 0.9.4、Trafilatura 2.3.1。OCR版本与实际参数见图片摘要；全部工具版本/参数保存于用户输出 `tool-parameters.json` 和 `docling/config.json`。网页方法的不同时间原件分别保留，不能假定每次远端内容逐字相同；离线Trafilatura才严格复用同一HTML字节。

## 逐页证据与缺口

旧五页保留原时间和结论，详情见[原报告](../mission-c-live-20261027/REPORT.md)及[四页Fetch逐节比较](fetch-four-report.md)。本票只读取已有文件：

1. [王平／兰州交通大学](https://jtys.lzjtu.edu.cn/info/1113/4365.htm)：原版与浏览器/框架旧结果412；旧Fetch有七节全文和王平/副教授/本人邮箱候选。无原站HTML，全文无法独立核实，不能称永久失效。
2. [何剑／苏州大学](https://web.suda.edu.cn/hj1/)：四页补测的教育、工作、研究、项目首尾、论文首尾、专利及招生均可对照；Fetch保留正文但漏专利小标题/空课程标签。旧共用解析器漏本人邮箱；旧模型候选是另一项历史方法。
3. [王健／华北电力大学](https://electric.ncepu.edu.cn/szdw/jsxx/gdyyjyjsyjs/a207300faea944298a27ba0a6d0c6c7b.htm)：教授/本人邮箱有本地原件；Fetch保留项目、论文首中尾及末篇页码。博士生导师不代专业职称；本页无独立专利条目，不记为遗漏。
4. [张惠芳／上海大学](https://physics.shu.edu.cn/info/1082/5653.htm)：副研究员/本人邮箱、教育、工作、项目和论文尾有证据；Fetch表格线性化。原版空链接故障、离线修复和成功结果仍分别保存。
5. [李艳青／华东师范大学](https://faculty.ecnu.edu.cn/_s41/lyq2/main.psp)：教授/本人邮箱有证据，Fetch教育/工作/研究尾保留；姓名卡独立教授标签遗漏，工作履历仍有教授。项目/专利仅概述，没有虚造明细。

新增15页按固定清单：

6. [卫子安／中科大](https://faculty.ustc.edu.cn/weizian/zh_CN/index.htm)：本地原件确认姓名、高级工程师、本人简介、教育与工作。原版误取“中文主页”、职称空；Fetch只给个人信息/联系方式，**简介首、研究中、工作尾与教育/工作标题均遗漏**。Fetch明文邮箱在本地原件中为编码串，未解码核实，不自动采用。分立科学研究/教学/获奖未跟随。
7. [应晓英／浙大](https://person.zju.edu.cn/0002306/732435.html)：本地元数据有姓名/研究员/药剂学，原版字段空；Fetch与正常Edge也只给元数据、栏目名。Crawlee/C4为403。页脚平台邮箱不归本人；学习/成果实际正文未取得，不能因有script就宣称动态内容成功。
8. [Zhi-Hua Zhou／南大](https://cs.nju.edu.cn/zhouzh/)：原件有Professor、本人at/dot邮箱和研究方向；各HTML方法仍裁错姓名、职称空。Fetch在首段、研究中和图书尾保留文字、变更Markdown格式。Brief CV/Publication分立，未覆盖完整履历或全部发表；未猜标准化本人邮箱。
9. [李明松／北大](https://faculty.pku.edu.cn/li/zh_CN/index.htm)：本地原版robots无法确认，无原件；Fetch有个人资料，但简介止于“中生代...”并列查看更多。分立科研/教育和CV PDF没有本机读取，提供方资料本身不能充当完整性真值。
10. [许畅／大工](https://faculty.dlut.edu.cn/xuchang1/zh_CN/index/1213400/list/index.htm)：原件有姓名/教授，原版字段空。Fetch保留主简介、教育表、研究、3篇代表作、2个项目和招生；主简介末尾另有研究说明。HTTP尾部重复模板的“2022.07 2026.08 美国德州农工大学 研究助理教授”不在Fetch，单独列遗漏，不能误报整段本人工作史全部丢失。表格线性化；明文邮箱未由本地编码解密核实。分立科研子页未跟随。
11. [冀晓宇／浙大](https://mypage.zju.edu.cn/xji)：原版robots无法确认；Fetch仅176字元数据/栏目外壳。无原件、无研究教育正文真值，不能算完整简历成功或永久失效。
12. [Geoffrey Hinton／Toronto](https://www.cs.toronto.edu/~hinton/)：原版/Edge robots不可确认、Crawlee TLS失败、C4连接关闭、Fetch提供方504。保留全部失败，未把同站CV/Brief Biography/论文导航当已读。
13. [肖跃龙／湘潭大学](https://math.xtu.edu.cn/info/1010/3525.htm)：原件确认姓名、教授、本人邮箱；Fetch首段、研究中与末论文DOI保留（DOI标点转义）。教育/论文分节及所有可见长行另存对照；邻近新闻和其他教师不是本人正文。局部命中不证明全部原文准确。
14. [夏冰楠／温州商学院](https://gl.wzbc.edu.cn/Art/Art_2480/Art_2480_134045.aspx)：姓名正确；本人只写博士/专任教师/专业负责人，职称邮箱留空。Fetch简介首、研究中、寄语尾保留；侧栏教授/副教授是分类，不属于本人。
15. [张耀坤／南昌航空大学](https://em.nchu.edu.cn/jyjx/content_176434)：原件确认姓名、教授和空格写法本人邮箱；Fetch简介首格式变化、研究中与末篇论文保留。研究/项目/发表范围保存在原正文和逐长行对照中；站群噪声与普通照片不当图中简历。
16. [张红岩／淮北师大](https://msxy.chnu.edu.cn/szdw/yjsdsfc/content_12638)：正文3图，本次第2/3图取得，首图network_error保持缺口。HTML方法只读标题/周边，均未OCR；Fetch却含3图文字，首图职称/教育仍只能称提供方材料，历史图不能冒充当前原件。当前图中科研/专利/教研尾可核对，Fetch还把整格文字与线性段落重复输出。
17. [鲍相志／淮北师大](https://msxy.chnu.edu.cn/szdw/yjsdsfc/content_149808)：当前单张原图取得；本人姓名、讲师（博士为学历）、研究、教育与4项成果可见。HTML字段只取姓名；Fetch/OCR能给图文，但有细字差异、跨列/行序和论文遗漏，详见下节。未把导师姓名归本人。
18. [Tom Mitchell／CMU](https://www.cs.cmu.edu/~tom/)：原版robots不可确认；Fetch有英文长文。无本地对应原件，不评分本人字段或全文；resume.pdf未读取，不能算PDF覆盖。
19. [Michael I. Jordan／Berkeley](https://people.eecs.berkeley.edu/~jordan/)：原版robots不可确认；Fetch有英文长文。本人/管理员邮箱分区和当前身份未由本机原件核实，字段不补填；jordan-cv.pdf未读。
20. [Qiang Yang／HKUST](https://home.cse.ust.hk/~qyang/bio/)：原版robots不可确认；Fetch有中英文历史简介。无本地原件和CV/PDF对照，不把材料旧时态或URL日期当当前任职。

## 图片实际对照

3张**当前**原图hash与下载状态见 `cohort-images.json`，未下载的第1张保留失败；没有用历史图凑4图覆盖。RapidOCR 1.4.4用现有Mission C本地OCR，CPU线程2/1；Docling 2.140.0 / docling-core 2.102.0 / RapidOCR 3.10.0复用既有模型，CPU4线程、中文OCR、layout/table开启、每图120秒，设置离线环境并禁止进程socket连接，无下载/升级/远程服务。

RapidOCR三图均为 `ocr_candidate`；Docling三图均SUCCESS，张图第2/3张各0表，鲍图1表。保存每行框/置信度、完整OCR文字、Docling文档JSON/Markdown和表格数据。两种方法共享RapidOCR技术路径且版本/模型不同，不称完全独立识别算法。

清晰的四处参照——张图专利“一种平面设计用品携带工具箱”、尾部“2019年十一届大广赛安徽赛区优秀指导教师”、鲍图“历史学博士、讲师”和“中国古代书画鉴定与研究”——在Fetch/RapidOCR/Docling中均有文字。但这不能证明全文：

- 鲍图有4项成果，RapidOCR把第2项主体变为“《，一中，中》”，不能交付为完整论文原文；Docling该项更完整，但同一成果单元格重复到两列，个人简历也重复。
- 张图第3张的2019年安徽省教学成果奖条目在Docling文档JSON和Markdown中均只剩“2，一 模式研究”（带项目号），发生大幅漏识/结构断裂；2020年校级三等奖条目保留，不能把两条不同年份奖项错配后宣称改字。末尾“共出版教材5部”被放到后面，另有重复编号。保留原图而不是仅看SUCCESS或置信度。
- 鲍图第3/4篇作品人名、导师姓名和尾部媒体字样在方法间有差异。原图只有621×696，早期短参照的媒体字样经复看不足以给确定真值，已在机读结果降为无法核实；不把推测改字包装为确定错误率。需高分辨率原件或人工进一步核实。
- Fetch张图含大量重复表格文字，且当前缺首图，不能确认整页图片简历完整。OCR新增文字未自动写回正式教师结果。

## 如何解释保留和遗漏

`retained`为短参照原样出现，`format_changed`只作NFKC/空白及Markdown标点反转义后匹配，`omitted`须在本地独立来源中存在而目标方法未见，`unverifiable`为无本地原件或视觉参照不确定。字段的文字出现和归属于本人分开；原始编码邮箱、公共邮箱、导师/合作者名称不据存在就填入。

新九页的独立HTML短参照和补充教育/研究/项目/论文检查与全部可见长行均可对账。全部长行清单包含站点导航、模板重复与噪声；它暴露待复核段落，**没有以命中比例、字符数、HTTP200或少量锚点计算全文准确率**。分立CV/论文/附件、点击后隐藏内容及异步接口均不在此次单页读取范围内。无法核实和官网未列不是同一状态。

这轮能支持的判断是：不同结构的字段/全文缺口确实存在；正常浏览器和框架获取到HTML仍可能留下同一字段错误，正文清洗/Fetch也可能省略本人材料，OCR/文档表格成功仍会改字或重复。不能由此排名“万能最好”。Crawlee PlaywrightCrawler、Scrapy/Scrapling、Stagehand、远程Docling、新PDF/扫描PDF、批量并发、登录或反爬场景均未在本票新增验证；历史工具结果保留自己的时间和范围。

## 复现、验证与交付阶段

生产Python未改。本票新增 `ds_fetch_once.py --manifest` 选样能力；CLI确认边界沿用“URL/保存网页→本人字段、完整正文、来源与失败”。先运行新增选样/缓存测试失败（旧CLI拒绝n01），最小实现后通过；重复ID/缓存URL冲突/未知attempt为同一外部边界回归。新4项加旧7项共11项通过，无真实计费测试。最终验证记录见 `validation.json`。

从完整通用Python运行 `run_tools.py browser/crawlee/crawl4ai/trafilatura`，从现有Docling环境运行 `run_images.py docling`；已有结果复用，不覆盖原版基线。图片离线尝试也先记录状态，已存在attempt不自动重做。`build_report.py`只读保存文件重建摘要/证据/候选，不联网、不调模型；大原件路径为受控本机目录。

本票由独立实施代理完成，提交前合入当时集成分支并核验；最终合并代理、Standards/Spec双轴审查、PR和准确提交CI由主代理统一协调。当前结果属于实施成果，不能以报告存在宣称审查/合并/正式教师交付完成。原目录其他并发修改未纳入提交。
