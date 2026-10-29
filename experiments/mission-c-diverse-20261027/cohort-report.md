# 新增十五页固定样本与独立采集证据

对应 [#26](https://github.com/normaltank/NewPlan/issues/26)，规格 [#24](https://github.com/normaltank/NewPlan/issues/24)。这是结构分层的便利选样，不是统计随机，也不是学院完整性验证。18个候选中固定15页；其余3页保留未选原因，选中后失败不换样。旧五页结果没有覆盖。

2026-10-27 本机原版 Mission C CLI 逐页运行：**9页 `text_saved`，6页 `not_extracted/robots_unavailable`**。后者是本机无法确认读取规则，不能称原站不存在或永久主页失效。无付费API、DS、Jina、Firecrawl、登录或反爬绕过。生产代码未改。

## 查阅材料

- [固定清单](cohort.json)：15个URL、预期姓名、校院输入元数据、选样理由。预期姓名仅作参照，未传 `--name`；校院来自清单，不是采集器推断。
- [全部候选与结构证据](candidates.json)：18候选、官方身份线索、研究代理浏览器结构摘录、未选原因。浏览器摘录原始依据为资料代理的 Chrome 工具输出，没有伪称已另存HTML/截图；本机DOM以保存原件补证。
- [独立参照](references.json)：从官网原始HTML和实际原图人工读取，独立于采集器提取结果；[核对结果](cohort-reference-checks.json) 绑定原件hash。
- [运行摘要](cohort-results.json)：逐页状态、时间、source hash、实际字段和来源位置；[版本及验证](cohort-validation.json) 保存代码树hash、CLI测试及集成基线。

大原件与CLI输出保存在 `D:\Agent Workspace\Intern\MyPlan\OpenSource\Mission C\outputs\diverse-pages-20261027\cohort`。每页 `run.json`、`stdout.txt`、`stderr.txt`、`cli/teachers.json`、`cli/0001/source.html`、`biography.txt`，以及 `source-inventory.json`、独立 `independent-source-text.txt` 可对账；未读页面没有伪造source/hash。图片原件和失败见对应页 `image-sources.json`。根目录另有汇总。

## 逐页实际结果

1. **卫子安 / 中科大**：多导航、教育/工作分区；HTML邮箱为长十六进制串，没有解密或猜填。自动姓名误为“中文主页”，职称未取到；原件明确本人姓名及高级工程师。
2. **应晓英 / 浙大**：原件只有个人元数据和栏目名，未取得学习/工作/成果正文。自动姓名、职称为空；本人元数据写研究员。页脚平台邮箱不归本人；script存在不证明动态正文已验证。
3. **Zhi-Hua Zhou / 南大**：英文独立站、表格布局、分立CV/Publication导航、at/dot邮箱。原始title为 `Zhi-Hua Zhou's Homepage`，final URL仍为清单URL；CLI误取 `Hua Zhou's Homepage`，不是跳到另一位教师。主页研究与图书不能当作分立论文全文已读。
4. **李明松 / 北大**：CLI `robots_unavailable`，本机无原件。资料代理提供方实际打开官方16页PDF，PDF反向列本人主页；未证主页正向链接，未计本机PDF读取成功。
5. **许畅 / 大工**：复杂导航、教育内容表格（原件2个table）、中英论文、履历重复。自动姓名/职称为空；原件姓名和教授清晰可见，导师资格单独保留。
6. **冀晓宇 / 浙大**：CLI `robots_unavailable`；官方索引身份和资料代理超时只作线索，正文未读。
7. **Geoffrey E. Hinton / Toronto**：CLI `robots_unavailable`。资料代理提供方点开官方27页 `shortcv.pdf`，不冒充本机原件。
8. **肖跃龙 / 湘大**：学院CMS长文、新闻与前后教师链接噪声；姓名/教授/本人邮箱均与原件一致。
9. **夏冰楠 / 温商**：ASP.NET风格详情、侧栏“教授/副教授/博士”分类。本人仅列博士、专任教师、专业负责人，不能据侧栏补职称；姓名正确，职称邮箱留空。
10. **张耀坤 / 昌航**：站群导航、正文日期空格、中英论文。姓名/教授/空格写法本人邮箱均正确；普通照片alt含路径，不能当图片简历。
11. **张红岩 / 淮北师大**：已知困难样本复用；本次HTML正文确有3张表格式图片。第2/3张成功下载并视觉读到专利与教学/成果尾段，第一张下载 `network_error` 保留；另重看历史第一张原图，不宣称本次第一张取得。baseline姓名正确，未启用OCR，图片正文未进入简介。
12. **鲍相志 / 淮北师大**：已知困难样本复用；本次一张表格式PNG成功下载，hash与历史一致，已视觉核姓名、历史学博士/讲师、研究和尾部成果。baseline姓名正确，职称/图中正文缺失。
13. **Tom Mitchell / CMU**：官方独立站和同主机resume.pdf线索；CLI `robots_unavailable`，正文/PDF未读。
14. **Michael I. Jordan / Berkeley**：本人/管理员邮箱并列及同主机CV线索；CLI `robots_unavailable`，不据搜索填写字段。
15. **Qiang Yang / HKUST**：中英文简历及CV线索；CLI `robots_unavailable`，旧索引时态不当当前任职。

## 可说明的覆盖与限制

本机真实保存并核过学院CMS/ASP.NET风格详情、英文独立站、数据表格、多导航栏目、加密/变体邮箱、中英论文、两位教师图片简历。表格不能一律称数据表：南大两个table主要布局，大工教育表有真实行列。23个HTML短参照均在原件中存在且在baseline简介中保留；这只说明这些片段保留，不证明整页或分立材料完整。3张成功原图中的5个视觉参照均未进入无OCR的baseline简介；历史第一图参照另列，不混计。

异步正文、点击后完整标签、当前本机PDF解析均**未验证**。图片成功取回3/4张，非完整四图成功。九页拿到文字不等于九页本人字段正确：前四个可读模板中的姓名/职称均有失败；图片页面的 `text_saved` 主要保存HTML标题和周边文字。所有结果为实验候选，不是正式教师交付。

## 复现与验证

`cohort_run.py --manifest cohort.json --output <上述cohort目录> --collector <工作树Mission C/collect.py>` 只复用已有记录。要另作新运行需另选输出目录，原结果保留；manifest变更与既有结果不符会拒绝复用。`run.json` 先标记尝试，再启动CLI；中断后的未知结果不自动重发。

`cohort_inspect.py` 从原始HTML独立保存DOM计数、链接与文本，不调用生产提取器；`cohort_check.py` 对比人工原文参照；`cohort_image_sources.py` 只读已审两个固定页面 `.conTxt` 的四张图，保存失败并复用已有记录。

测试边界沿用用户确认的“URL/保存网页→本人字段、完整简介/研究/发表原文、来源、失败状态”。离线外部CLI测试先红（运行器尚不存在），实现后绿；实际验证字段、末论文全文和删掉输入后重入保持原teachers.json字节/修改时间。生产CLI套件14项：12通过、2项可选动态/OCR测试跳过。并入 `a16e1446a4dc690690075a22ba20f2c725eb0baa` 后重跑cohort测试。最终双轴审查、CI及PR由集成流程统一进行，本票没有推送或创建PR。
