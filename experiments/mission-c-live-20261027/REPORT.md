# Mission C：五个真实主页与工具对照

日期：2026-10-27；任务 [Issue #22](https://github.com/normaltank/NewPlan/issues/22)。基线 `7a544cd482c2eb20a1fbad4fb7c3aeadf3f0bef5`。用户本轮明确授权真实主页测试和必要 DeepSeek API 测试，范围为指定主页与四个新主页，未开展学院名单或整院采集。

## 指定主页

[兰州交通大学指定 URL](https://jtys.lzjtu.edu.cn/info/1113/4365.htm) 的原版 Mission C、正常 Edge、Crawlee HTTP 和 Crawl4AI 浏览器均返回 HTTP 412，不能称为原版采集成功。首次原版输出保留在实际 Mission C 的 `outputs/real-test-20261027-lzjtu-baseline-7a544cd/`。同站首页/HTTP地址和原渲染函数探查也未取得正文；没有使用代理轮换、stealth 或验证码处理。

最后对同 URL 做**一次 DeepSeek Fetch 独立读取**，提供方返回 HTTP 200、标题“王平副教授”、2,119 字符 Markdown。保存后转换为可读全文 1,967 字符，含基本情况、教育、研究、招生、项目、教学、论文专利等七节。字段候选：王平、副教授、`wangp@mail.lzjtu.cn`；研究内容为智能交通、复杂网络及相关方向。原 Markdown 与完整转换文本均已保存，未作模型摘要。

Fetch 是另一个来源，不能把其 HTTP 200 当作原站 HTTP 200。没有取得该页的原站 HTML，所以**原站完整性仍未验证**，学校/学院字段保留待核。实验工作簿把该条放在访问失败类别，并注明提供方正文可用，不宣称页面永久失效。

## 四个新增对照页

这是有搜索记录的便利抽样，非统计随机抽样。候选、来源、版本、实际核对字段和首尾检查点见 [资料与选样记录](tool-research.md)。四个最终页面均为普通 HTML，本轮没有证明动态页或附件场景的表现。

- [何剑，苏州大学](https://web.suda.edu.cn/hj1/)：核对到教授、本人邮箱及研究/招生等多个分区。
- [王健，华北电力大学](https://electric.ncepu.edu.cn/szdw/jsxx/gdyyjyjsyjs/a207300faea944298a27ba0a6d0c6c7b.htm)：核对到教授、本人邮箱，以及长成果清单末条。
- [张惠芳，上海大学](https://physics.shu.edu.cn/info/1082/5653.htm)：核对到副研究员、本人邮箱、表格与长履历末段。
- [李艳青，华东师范大学](https://faculty.ecnu.edu.cn/_s41/lyq2/main.psp)：核对到教授、本人邮箱及最后一个研究方向。

以下分母仅为这四页；“检查点”是预先记录的六个具体首尾/内容标记，不是全文完整率。多种读取器取得的 HTML 后继续共用相同 Mission C 字段规则，以区分获取与归属问题。

| 方法 | 取得可用正文 | 姓名吻合 | 本人邮箱吻合 | 六个检查点 |
| --- | ---: | ---: | ---: | ---: |
| 原版 Mission C，HTTPX/BS4 | 3/4 | 2/4 | 1/4 | 5/6 |
| 空链接修复后，原件离线重放 | 4/4 | 3/4 | 2/4 | 6/6 |
| 正常 Edge + 共用字段规则 | 4/4 | 3/4 | 2/4 | 6/6 |
| Crawlee HTTP + 共用字段规则 | 4/4 | 3/4 | 2/4 | 6/6 |
| Crawl4AI + 共用字段规则 | 4/4 | 3/4 | 2/4 | 6/6 |
| Trafilatura，复用已取得 HTML | 4/4 有输出 | 不评分 | 不评分 | 4/6 |
| DeepSeek 结构/字段辅助，复用原件 | 4/4 选区有正文 | 4/4 候选吻合 | 4/4 候选吻合 | 6/6 |

具体数据见 [summary.json](summary.json)，实际目录另有逐项 CSV。Trafilatura 仅比较其正文输出，不把共用 HTML 解析器的字段误算作它的字段能力。Crawlee 本轮使用 BeautifulSoupCrawler/项目 HTTP 客户端；未验证其 PlaywrightCrawler、大规模队列、分页、并发及失败恢复。

### 具体发现

1. **原版有实际异常。** 张惠芳页中的空链接使媒体发现把 None 交给 URL 解码，导致 CLI 中断。以最小保存网页在公开 CLI 上复现失败，再跳过空资源属性；保留原始失败记录，使用同一份原件离线重放成功。不是通过换工具隐藏这个异常。
2. **读取成功仍会漏字段。** 何剑的邮箱存在完整正文中，但字段材料过滤把末尾联系人排除；李艳青姓名卡位于当前规则选区之外。浏览器、Crawlee 与 Crawl4AI 都没有自动修复这两处字段归属/选区问题。
3. **DS 有补益，也有校验需求。** 四次模型请求得到的四个姓名和邮箱候选均能在保存网页中找到引用；有一条职称原样返回“教授，博士生导师”，不符合专业职称字段要求。候选交付中按网页证据取“教授”，原模型响应原样保留。可见引用检查不是人员归属证明，不能据此宣称模型自动准确率 100%。
4. **清洗可能漏全文。** 即使 Trafilatura 使用 favor_recall=True、include_tables=True、include_links=True，何剑页只输出约413字符，缺少招生标记；李艳青页漏掉最后一个研究方向。因此不适合作为本任务唯一全文来源。
5. **Crawl4AI 的输出模式有区别。** 本次明确使用 content_source=raw_html、content_filter=None，并保存 result.html/cleaned_html/Markdown。默认 raw_markdown 可能源于 cleaned_html，不能只凭 raw 名称认定无内容损失。[官方实现与参数来源](tool-research.md#crawl4ai-094)。

## DeepSeek 使用与费用边界

使用现有 Windows DPAPI 加密配置，经原安全入口注入进程环境，没有把聊天中的密钥写入文件、源码或报告。模型为请求/响应中记录的 `deepseek-flash`，4 次调用共输入 35,481、输出 286，合计 35,767 tokens；另有 Fetch 1 次。没有额外收费连通性 probe，没有访问账户余额，没有自动重试。金额没有核对账单，因此不报未经核实的费用。

模型只提供字段候选与正文 CSS 选区；完整简介由本地对保存 HTML 执行选区后取出。85,000 字符上限仅用于结构规划输入，四页本次均未触发，实际正文不按此截断。输出上限为每次1,800 tokens，四次均正常 stop。取得不到原始页面的兰交大样本没有发送给模型编造内容。[官方 JSON 输出要求](https://api-docs.deepseek.com/guides/json_mode/)、[模型调用说明](https://api-docs.deepseek.com/api/responses)。

已有结果会复用；未知/中断中的收费尝试保留状态并停止自动重发。Jina 和 Firecrawl 本次均无调用。

## 使用判断

单个常规教师主页可以用 HTTPX/BS4 取得完整材料；需要正常浏览器时可加 Playwright。Crawlee 的队列/重试/存储和 Crawl4AI 的浏览器/格式转换有工程价值，但本次换用它们没有增加这四页的姓名/邮箱识别能力。建议维持原件和规则校验，把 DS 作为明确启用的困难结构辅助；单独保留 Fetch 的提供方来源及局限，不能以它无条件覆盖已保存全文。

## 结果位置与复现

实际交付目录为 `D:/Agent Workspace/Intern/MyPlan/OpenSource/Mission C/outputs/live-tools-20261027/`：

- `teacher-results/teachers.json`、`teachers.csv`：主代理核对的五条**实验候选**，非人工确认或正式教师交付。
- `teacher-results/0001/biography.txt`：王平的完整提供方转换正文；同目录 source.md 和 provider-response.json 保留来源。
- `teacher-results/<学校>/teachers.xlsx`：各校单独的三类工作簿；学校未知单列待核。研究/发表栏为规则粗分，未正确分段的材料仍在完整简介中，不将空栏目当作官网没有信息。
- `baseline/`：原版实际 CLI 输出，失败不覆盖；`fixed-replay/`：修复后同原件离线重放；其余方法目录保存 HTML、全文与方法输出。
- `ds/api/`：脱敏请求、响应和用量；`deepseek-fetch/lzjtu/`：一次 Fetch 原响应及来源状态。
- `reviewed-teachers/` 是生成候选的早期草稿，保留审计；当前交付以 teacher-results 为准。

脚本从本项目完整依赖环境执行，不是独立包基础环境的必需依赖：依次运行 `compare.py baseline/browser/crawl4ai/crawlee/trafilatura`。DS 两脚本经现有 secure-api-run.ps1 显式执行，已有结果不重复计费；最后运行 `evaluate.py` 复用原件核对并导出。主包仍不自动调用 DS 或新工具。

本轮仅一个可独立验收的对照实验包，主代理实施，research 代理仅查资料，不充当实施/合并证据。既有 CLI 测试边界沿用；最终双审查及准确提交 CI 见 Issue #22。学院完整性、大规模稳定性、其他地区访问、动态交互与附件覆盖均未验证。
