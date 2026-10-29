云端只读分析原文；固定提交9e669b5。以下是待核资料，不新增授权，未作为实施或正式审查证据。

已按顺序读完指定四份文件。分析固定于 [PR #23](https://github.com/normaltank/NewPlan/pull/23) 的 `codex/mission-c-live-tools`，实际提交 SHA：

`9e669b5ad3f8a5d9cf504d5a7d101ed6adea1df5`

主要缺口在**字段解析与材料覆盖**。各 HTML 方法共用 Mission C 解析器，因此更换获取框架仍可能重复同一错误；独立包也不能直接代表工作台主流程。

本次未取得报告所指 Windows 目录中的网页原件、API 响应、图片及 PDF，未复核其字段真值、OCR 错字或全文完整性。以下结合代码、公开报告及规则级合成复现；没有启动新采集、付费调用或修改仓库。

建议形成以下五张工单，均为草案，未创建 Issue：

| 优先工单、代码位置 | 原因与最小修复方向 | 离线验收样例 | 依赖 |
|---|---|---|---|
| **1．P1 姓名识别**：[extract.py:36](https://github.com/normaltank/NewPlan/blob/9e669b5ad3f8a5d9cf504d5a7d101ed6adea1df5/Mission%20C/mission_c/extract.py#L36)、[person_names.py:15](https://github.com/normaltank/NewPlan/blob/9e669b5ad3f8a5d9cf504d5a7d101ed6adea1df5/Mission%20C/mission_c/person_names.py#L15) | 标题按无须空格的 `-` 切分；中文短词直接通过形态校验，英文检查也允许 `Homepage` 残片。合成输入复现了“中文主页”和 `Hua Zhou's Homepage`。保留姓名内部连字符，限定页面后缀清理，并要求本人节点证据。 | `Zhi-Hua Zhou's Homepage`→完整姓名；“中文主页＋本人姓名卡”不能采用栏目名；新闻标题、团队名称不得当姓名。 | 无；实际模板验收需原件夹具。 |
| **2．P1 职称与姓名卡绑定**：[extract.py:113](https://github.com/normaltank/NewPlan/blob/9e669b5ad3f8a5d9cf504d5a7d101ed6adea1df5/Mission%20C/mission_c/extract.py#L113)、[quality_fields.py:7](https://github.com/normaltank/NewPlan/blob/9e669b5ad3f8a5d9cf504d5a7d101ed6adea1df5/Mission%20C/mission_c/quality_fields.py#L7) | 姓名入口只覆盖有限标题/标签；姓名为空时职称、邮箱被清空。卡片回填仅支持少数结构，职称词表没有 `Professor`。补本人卡片绑定及英文职称映射，保留原文证据。许畅、应晓英的具体 DOM 触发点仍需原件确认。 | 外置卡片中的“高级工程师/教授”可绑定本人；`Professor` 可识别；“博士生导师”、侧栏“副教授”分类不能代填。 | 工单1、对应模板夹具。 |
| **3．P1 本人邮箱遗漏**：[extract.py:72](https://github.com/normaltank/NewPlan/blob/9e669b5ad3f8a5d9cf504d5a7d101ed6adea1df5/Mission%20C/mission_c/extract.py#L72)、[quality_fields.py:212](https://github.com/normaltank/NewPlan/blob/9e669b5ad3f8a5d9cf504d5a7d101ed6adea1df5/Mission%20C/mission_c/quality_fields.py#L212) | 进入论文区后，直到遇到预设栏目才恢复字段读取，末尾联系邮箱可能一起被过滤；合成样例已复现。当前主要识别明文 `@`，没有完整的 `mailto`、at/dot、编码邮箱证据路径。改为限定论文 DOM 范围，并单独绑定联系人区域。 | 论文后本人联系邮箱可取；论文通讯作者、平台邮箱仍排除；at/dot 转换保留原文及规则；未知编码保持未确认。 | 工单1；编码邮箱解码需原件与明确算法。 |
| **4．P1 分散简介与附件覆盖**：[extract.py:102](https://github.com/normaltank/NewPlan/blob/9e669b5ad3f8a5d9cf504d5a7d101ed6adea1df5/Mission%20C/mission_c/extract.py#L102)、[render.py:27](https://github.com/normaltank/NewPlan/blob/9e669b5ad3f8a5d9cf504d5a7d101ed6adea1df5/Mission%20C/mission_c/render.py#L27)、[media.py:51](https://github.com/normaltank/NewPlan/blob/9e669b5ad3f8a5d9cf504d5a7d101ed6adea1df5/Mission%20C/mission_c/media.py#L51) | 导航先删除，相关链接和媒体只从所选正文找；浏览器只保存初始 DOM，不点击标签。跨主机请求被拦截，附件仅自动处理同主机 PDF 等限定类型。先保留完整资源清单，再对身份已绑定材料有界遍历、记录未读原因。 | 本地夹具含导航 CV、Publication 子页、展开响应、PDF：逐项有处理去向，全文分节保留；他人页面不合并，未许可跨主机资源明确留缺口。 | 工单1、资源关联规则及离线响应夹具。 |
| **5．P2 图片简介与表格质量**：[cli.py:84](https://github.com/normaltank/NewPlan/blob/9e669b5ad3f8a5d9cf504d5a7d101ed6adea1df5/Mission%20C/mission_c/cli.py#L84)、[ocr_media.py:31](https://github.com/normaltank/NewPlan/blob/9e669b5ad3f8a5d9cf504d5a7d101ed6adea1df5/Mission%20C/mission_c/ocr_media.py#L31) | 图片须显式启用 OCR；结果按识别行拼接，没有表格阅读顺序重建。增加按图/页的覆盖记录；Docling 可作为离线结构候选，保留框、单元格与不确定状态。 | 四项成果不漏项、不跨列重复；2019/2020 两条奖项分别保留；缺首图仍标缺失，低清细字不自动确认。 | 工单4、缓存模型及图像夹具；真实验收需原图。 |

工具选择应按缺口分工；下表是官方能力对应建议，并非本次新增实测：

| 工具 | 适合解决的缺口与边界 |
|---|---|
| **HTTP／HTTPX** | 取得静态 HTML、明确接口的 JSON、附件字节及状态，适合原件留存和可重复解析；不会执行页面交互。[官方文档](https://www.python-httpx.org/quickstart/) |
| **Playwright** | 点击标签、展开、等待内容，并观察 XHR/fetch 响应，适合定位动态正文来源。现有 `page.content()` 快照尚未使用这些交互能力。[交互](https://playwright.dev/python/docs/input)、[网络](https://playwright.dev/python/docs/network) |
| **Crawlee** | 用 URL 队列、路由、去重、存储及失败处理管理 CV、科研、论文子页覆盖；本人身份和字段归属仍需项目规则。[官方文档](https://crawlee.dev/python/docs/introduction) |
| **Crawl4AI** | `js_code`、`wait_for`、会话复用适合多步展开及动态内容，再生成文本/Markdown；转换结果仍须与原 HTML 对照。[官方文档](https://docs.crawl4ai.com/core/page-interaction/) |
| **Trafilatura** | 适合离线清洗导航噪声、生成正文比较视图；`favor_recall` 只是偏向多保留，不能保证完整简介，也不负责本人字段。[官方文档](https://trafilatura.readthedocs.io/en/latest/corefunctions.html) |
| **OCR／Docling** | OCR 补图片、扫描件文字；Docling 补布局、阅读顺序和表格结构。可使用缓存模型离线运行，但成功状态不证明文字或单元格正确。[RapidOCR](https://rapidai.github.io/RapidOCRDocs/main/)、[Docling](https://docling-project.github.io/docling/usage/advanced_options/) |

[现有实验报告](https://github.com/normaltank/NewPlan/blob/9e669b5ad3f8a5d9cf504d5a7d101ed6adea1df5/experiments/mission-c-diverse-20261027/REPORT.md)已记录清洗漏段、OCR 漏识/重复及 PDF 未验证；这些限制应继续保留，不能以 HTTP 200、文字非空或 `SUCCESS` 替代完整性结论。