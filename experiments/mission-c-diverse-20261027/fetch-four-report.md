# 四个既有主页的 Fetch 补充对照

任务：[Issue #25](https://github.com/normaltank/NewPlan/issues/25)，属于 [规格 #24](https://github.com/normaltank/NewPlan/issues/24) 和 [原实验 #22](https://github.com/normaltank/NewPlan/issues/22)。起点 `1a2d63cbc5035361456a9bcf90a819c61d2139de`；实施分支 `codex/mission-c-fetch-four`。本轮仅完成四个既有主页的补充实验，生产 Mission C 未改。主代理统一负责索引、Issue、集成与双轴审查。

四页各一次 Fetch，均收到提供方 HTTP 200 和正文；新增 Fetch 共 **4 次**，新增 DS 模型、探测与重试均 **0 次**。历史兰交大 Fetch 缓存只复用，未重发。所有真实调用经既有 `secure-api-run.ps1` 和 Windows DPAPI 凭据入口执行；未读取、打印或保存密钥。金额未查账单，不报告费用金额。

## 核验结论与边界

四页的姓名、本人邮箱和专业职称都有保存官网原件依据，并能在 Fetch 文字中核对。Fetch 不返回独立、已归属的这些字段；下列字段是本次人工对照官网与提供方文本得到的值，未运行新模型。四个邮箱在 Fetch 原文中均被 Markdown 反斜杠转义；直接正则读原文可能漏邮箱。王健的“博士生导师”和张惠芳的“硕士生导师”均不作专业职称。

本次在简介首、中、尾和教育、研究、项目、论文、专利等已存在内容中选定短证据点。49 个内容/结构检查点里，46 个保留了文字（其中部分格式变化），3 个遗漏：何剑的专利小标题、空的“课程教学”标签，以及李艳青姓名卡上的职称组合。李艳青工作经历中的“教授”仍在；何剑专利条目仍在。上海页表格结构退化，不能仅因表格文字存在而认定结构无损。王健页与李艳青页没有可核验的独立专利明细，不记作 Fetch 漏抓；李艳青可核对的是简介中的论文、专利和项目概述。

这不是全文无损率或学院完整性结论。检查点命中和字符数均不能证明完整；未检查的文字、附件、图片、动态交互仍未验证。Fetch HTTP 200 属于提供方响应，`origin_http_status` 保持 null。保存官网原件在先前浏览器运行中为 HTTP 200；两次读取相差约两小时，访问次数等动态文字确有变化，不能把所有差异归因于转换。完整官网 HTML 和提供方响应各自保留，本轮不覆盖早期结果或教师交付。

机器证据见 [fetch-four-report.json](fetch-four-report.json)。其中保留每页官网原件路径、获取时间、SHA-256、原响应与正文 SHA-256、Fetch 起止时间/调用次数，以及各检查点官网/Fetch 引文行号。官网行号由保存 HTML 通过 BeautifulSoup 的 `get_text("\n", strip=True)` 得到；Fetch 行号对应原 `provider-content.md`。只有空白、NFKC 和 Markdown 标点转义被规范化，未去标点或用摘要补齐。已有 DS 选区结果也只离线对照，四份 DS 记录的来源 hash 与官网原件一致；`saved_ds_selected_text_contains` 只表示该选区有此文字，不能表示模型独立提取了字段。

## 调用与重入验证

调用期间为 2026-10-27 14:30:46 至 14:31:37 UTC（新加坡时间 22:30:46 至 22:31:37）。原件位于 `D:/Agent Workspace/Intern/MyPlan/OpenSource/Mission C/outputs/live-tools-20261027/`，新增响应仅写入 `deepseek-fetch/{suda,ncepu,shu,ecnu}/`，每份含 `attempt.json`、`provider-response.json`、`provider-content.md`、`result.json`。原响应保存原字节；本轮四次 `response_credential_redacted=false`，即无需改写响应字节。

实施采用本机 `C:/Users/27451/.codex/skills/ask-matt/SKILL.md`、`implement/SKILL.md` 与 `tdd/SKILL.md`，沿用已确认的 CLI/保存网页边界。单次选样可独立验收；更大样本和集成分别由 #26/#27 负责。新增参数 `--sample` 仅接受已有五个 ID，默认 `lzjtu`，`--output-root` 用于明确的隔离输出与离线测试。实际四页调用均使用既有默认输出根。

逐项红→绿证据（先运行失败再作最小修正，没有预写全部测试）：

1. 指定 suda 复用缓存：原脚本仍返回 lzjtu URL；加入明确选样后通过。
2. 错 URL 的缓存：原脚本退出码为 0；现在拒绝并保留缓存不变。
3. 单次 HTTP 响应与无密钥重入：原记录缺 `observed_at`；现在保留时间、响应 hash、全文、调用次数，第二次不触发 HTTP。
4. 外部 HTTP 超时：原堆栈输出测试假密钥；现在只保存异常类型和未知状态，第二次阻断，累计仍一次请求。实际密钥未用于此测试。
5. 两个同时启动的 CLI：外部边界记录到 `POST, POST`；使用独占创建 attempt 后只有一次 POST。
6. 提供方 HTTP 403：原结果没有明确失败类型；现在记 `provider_http_error`，`text_saved=false`，原站状态仍未知。
7. 旧默认缓存和预存未知 attempt：回归通过，无密钥也能复用旧缓存，未知 attempt 在取密钥前阻断。

最终七项 CLI 测试通过。真实四页加旧 lzjtu 默认缓存已在无密钥环境全部重入，重入前后所有 Fetch 证据文件 SHA-256 一致，无新增调用。传输失败只保存一次未知结果，或任何已存在未知 attempt，均不会自动重发；exclusive attempt 同时防止并发重复付费。返回格式未知/空正文会保存响应并记失败，不自动补调用。离线回放不能验证提供方今后的可用性。

复现（完整依赖环境 Python 为 `D:/Agent Workspace/Intern/MyPlan/OpenSource/.venv/Scripts/python.exe`）：

```powershell
python experiments/mission-c-live-20261027/test_ds_fetch_once_cli.py
python experiments/mission-c-diverse-20261027/compare_fetch_four.py
python experiments/mission-c-live-20261027/ds_fetch_once.py --sample suda
```

最后一条仅复用既有缓存；若在另一输出根首次运行，需要既有安全凭据入口且会产生一次真实调用。离线核验无需安全入口或密钥。报告脚本从未发网络请求。

最终验证：Fetch CLI 7 项通过；Mission C 合约 14 项通过（2 项可选浏览器/OCR 跳过）；工作台 203 项通过。首次工作台运行因未建立 CI 指定的 `runs/` 目录出现一项 FileNotFoundError，补齐同一 CI 前置目录后重跑通过，未改生产或测试源码。见 [验证摘要](fetch-four-workbench-tests.txt)。`content_sha256` 按提供方 content 字符串的 UTF-8 计算；Windows 文本写入可能转换换行，机器报告另存 `saved_content_file_sha256` 核对磁盘原件，未改旧缓存。

## 每页字段与检查点

下列“保留”指证据点文字存在，“格式变化”指规范化后存在，“遗漏”指官网原件存在而 Fetch 本文未保留该点，“无法核实”不算遗漏。

### 何剑（suda）

- 官网：https://web.suda.edu.cn/hj1/
- 官网原件时间：2026-10-27T12:35:07.140418+00:00
- 官网 HTML SHA-256：`bf04d8fcc2cb50fc0de6ed6bbb2ca009b9c507cb2b70807f52638d3ba4fc53c2`
- Fetch 起止：2026-10-27T14:30:46.554022+00:00 → 2026-10-27T14:31:01.502609+00:00
- Fetch 响应 SHA-256：`f1640f7c903118568c17aadf9a42fce9b8deb1382f61300765acdc0441125da8`
- 字段（官网原件人工归属，Fetch 文本核对）：name `何剑`（保留）；title `教授`（保留）；email `drhejian@suda.edu.cn`（格式变化）。

- 简介首：**保留**；证据点“何剑，苏州大学教授、博导，电子科技大学博士”。
- 简介中：**保留**；证据点“中国微米纳米学会微系统与微执行器分会理事”。
- 简介尾/招生：**保留**；证据点“085501 机械工程（专硕）”。
- 教育：**格式变化**；证据点“2009.09-2014.12, 光学工程, 电子科技大学, 博士”。
- 工作：**格式变化**；证据点“2026.03-至今, 苏州大学未来科学与工程学院, 副院长”。
- 研究：**保留**；证据点“无人平台：具身智能、无人值守、人工智能算法、测试评估”。
- 项目首：**保留**；证据点“基于铁电单晶电畴精密调控的太赫兹产生机理”。
- 项目尾：**格式变化**；证据点“9、xxx传感器件, 2019.01- 至今, 主持, 航天、兵器集团等单位横向课题, 3000万”。
- 论文首：**格式变化**；证据点“Chip-less,Self-powered electronic patch for wireless sensing and communication”。
- 论文尾：**格式变化**；证据点“Flexible wide-range multidimensional force sensors inspired by bones embedded in muscle.”。
- 专利首：**保留**；证据点“一种高密度微纳线圈柔性异质集成方法”。
- 专利尾：**格式变化**；证据点“ZL202311617338.7.”。
- 软件著作：**格式变化**；证据点“运动数据同步分析工具软件V1.0”。
- 奖励尾：**保留**；证据点“自驱动智能感知微系统技术及应用”。
- 招生尾邮箱：**格式变化**；证据点“欢迎联系：drhejian@suda.edu.cn”。
- 专利小标题：**遗漏**；证据点“专利：”。
- 空课程教学标签：**遗漏**；证据点“课程教学：”。

专利小标题和空的课程教学标签遗漏；专利首尾和六条专利正文仍在。 标题/列表、邮箱及英文标点大量反斜杠转义；这不是独立字段抽取结果。


### 王健（ncepu）

- 官网：https://electric.ncepu.edu.cn/szdw/jsxx/gdyyjyjsyjs/a207300faea944298a27ba0a6d0c6c7b.htm
- 官网原件时间：2026-10-27T12:35:16.908711+00:00
- 官网 HTML SHA-256：`66bb6a155765c474408572867ef40d009bd98e53a0d86d69024321f37c428ba4`
- Fetch 起止：2026-10-27T14:31:08.285689+00:00 → 2026-10-27T14:31:13.197332+00:00
- Fetch 响应 SHA-256：`5c181f8f5ac1253a445ec51b5cb2b19365b589b3054850ef697ad8dc10146337`
- 字段（官网原件人工归属，Fetch 文本核对）：name `王健`（保留）；title `教授`（保留）；email `wangjian31791@ncepu.edu.cn`（格式变化）。

- 简介首：**保留**；证据点“王健，男，1985年12月生，教授，博士生导师”。
- 教育：**保留**；证据点“2017年在华北电力大学获得高电压与绝缘技术博士学位”。
- 研究：**保留**；证据点“先进绝缘材料（Advanced Insulation Materials）”。
- 简介中/学生培养：**保留**；证据点“中国研究生“双碳”创新与创意大赛二等奖”。
- 项目首：**保留**；证据点“高经济性多端异构换流装备轻量化集成研制”。
- 项目尾：**格式变化**；证据点“高压大功率****寿命及可靠性强化技术”。
- 奖励尾：**保留**；证据点“2023年日内瓦国际发明铜奖”。
- 论文首：**格式变化**；证据点“Gas-Generation Mechanism of Silicone Gel in High-Temperature Thermal Decomposition”。
- 论文中：**格式变化**；证据点“Motion Analysis of the Spherical Metal Particle in AC Gas-Insulated Lines”。
- 论文尾/简介尾：**保留**；证据点“含苯硫醚基团的低介损聚酰亚胺薄膜合成及其性能调控机制”。
- 论文尾页码：**格式变化**；证据点“4623-4633”。

专业职称为教授；博士生导师另属导师资格，未代入职称。 官网本文无独立专利条目可核对，不能把该项记为Fetch遗漏。


### 张惠芳（shu）

- 官网：https://physics.shu.edu.cn/info/1082/5653.htm
- 官网原件时间：2026-10-27T12:35:23.864243+00:00
- 官网 HTML SHA-256：`fbe8b3c1da14819213ad8ef7fb8a9ab3b2d2f6506389ee8c4f6df09c55a3928a`
- Fetch 起止：2026-10-27T14:31:19.192611+00:00 → 2026-10-27T14:31:24.027717+00:00
- Fetch 响应 SHA-256：`23d33a0eeb7cc2d7e29066f502d54fe96eb834a0ce3f43d538d2f4900519d18b`
- 字段（官网原件人工归属，Fetch 文本核对）：name `张惠芳`（保留）；title `副研究员`（保留）；email `hfzhang1967@shu.edu.cn`（格式变化）。

- 简介首/本人身份：**格式变化**；证据点“姓名：张惠芳”。
- 教育：**格式变化**；证据点“1998-09 至 2003-07, 吉林大学物理学院, 光学专业, 理学博士”。
- 工作：**格式变化**；证据点“2005-04 至 今, 上海大学, 理学院物理系, 副研究员”。
- 研究：**保留**；证据点“微纳光子学、超材料、量子光学”。
- 简介中/论文：**保留**；证据点“Tunable surface plasmon polaritons in the graphene and metamaterials structures”。
- 论文首：**格式变化**；证据点“Tunable multiple plasmon-induced transparencies in multiple T-shaped cavities waveguide based on Dirac semimetals”。
- 论文尾：**格式变化**；证据点“Quantum-interference effects on the index of refraction in an Er3+-doped Yttrium Aluminum Garnet crystal”。
- 专利：**格式变化**；证据点“ZL03111442.3”。
- 专利批准号：**格式变化**；证据点“CN1188742.C”。
- 项目首：**保留**；证据点“11804219”。
- 项目尾：**保留**；证据点“基于飞秒脉冲整形和绝热传输实现超快相干布局转移控制研究”。
- 简介尾：**保留**；证据点“鼓励和督促学生学习考研”。

硕士生导师属于导师资格；官网表格明确专业职称为副研究员。 表格转为分散行并出现转义的---|---，姓名/职称/邮箱文字仍在，表格结构不再可靠。


### 李艳青（ecnu）

- 官网：https://faculty.ecnu.edu.cn/_s41/lyq2/main.psp
- 官网原件时间：2026-10-27T12:35:26.952498+00:00
- 官网 HTML SHA-256：`4481b16ede48017eb6e0058f81ad751f735964e6c194d676c05b2cc80998579b`
- Fetch 起止：2026-10-27T14:31:32.752125+00:00 → 2026-10-27T14:31:37.942455+00:00
- Fetch 响应 SHA-256：`2ec691db7d9694cc5058398f13c71e54713d9a5366429ddb77fac7191187c84a`
- 字段（官网原件人工归属，Fetch 文本核对）：name `李艳青`（保留）；title `教授`（保留）；email `yqli@phy.ecnu.edu.cn`（格式变化）。

- 简介首/教育：**格式变化**；证据点“2004年-2008年，香港城市大学，材料物理，博士”。
- 教育尾：**格式变化**；证据点“1997年-2001年，浙江大学，物理学，学士”。
- 工作：**格式变化**；证据点“2003年-2004年，新加坡材料研究及工程研究所（IMRE），研究助理”。
- 简介中/论文概述：**保留**；证据点“等期刊发表SCI论文200余篇，引用1万余次，H因子58”。
- 专利概述：**保留**；证据点“授权发明专利20余项”。
- 项目概述：**保留**；证据点“科技部国家重点研发计划课题”。
- 研究首：**保留**；证据点“新型显示发光材料与器件”。
- 简介尾/研究尾：**保留**；证据点“柔性光电材料与器件集成”。
- 姓名卡职称：**遗漏**；证据点“李艳青教授教授物理与电子科学学院”。

姓名卡中独立的教授标签被省去；2019年至今的工作经历仍明确保留教授。 官网科研项目/学术成果标题下无独立明细；本页仅能核对简介中的项目、论文和专利概述。
