# 辅助字段归属审查修复

关联 [#30](https://github.com/normaltank/NewPlan/issues/30)、[#32](https://github.com/normaltank/NewPlan/issues/32)。固定审查基线为 `626172e3a10b184281dc411c0b0aa701988cbb76`；两份独立报告确认 3 项 P1，未列其他发现。本轮是同一集中实施修复，正式复审及集成由主代理随后执行。

## 反例与机制

- A：原件只有王宁而输入预期陈晨，模型曾恢复王宁及其字段。`076ecff` 在身份冲突时保留待核，阻止依赖该身份的提议。
- B：`学院邮箱` 在 dt、邮箱引用在 dd，或合作者标题与邮箱在分散节点，原来仅检查最小引用而漏掉标签。`8381798` 核对相邻标题与关联标签；`c8c4ce4` 补相同英文 Department email / Collaborator 反例，普通个人 Email 仍采用。
- C：陈晨外层标题包围周宁独立 h2 与邮箱，原来向上穿越借用陈晨身份。`5f598b6` 保留最小引用节点并在独立他人标题处停止，`7589d48` 保留明确公共/合作者上下文的拒绝理由。
- Fetch 纯文本没有 DOM 边界，`914a9a9` / `5d67c79` 遇到另一独立个人身份时保守待核，区分职称等字段标签，保留原文、原站失败和引用。不改变纯文本候选的来源状态。

均通过公开缓存清单到 CLI 产物边界验证。新增测试在 `Mission C/tests/test_assisted_fields_cli.py`；人工构造来源与 SHA 绑定模型响应，HTTPX 发送被禁止。虚构在线适配器既有用例仍只经过 fake IO。

## 证据与限制

红绿原件位于 `%TEMP%/mission-c-review-{red,green}-A.log`、`-B.log`、`-C.log`、`-plaintext.log`、`-B-english.log`。C 和纯文本初次扩大到既有测试时分别发现拒绝理由变化、职称标签误判，均已修复；最终日志为实际通过结果。

最终运行时代码 `c8c4ce4` 用只读 `%TEMP%/mission-c-fields-real4/manifest.json` 再回放四页，新目录为 `assist-review-fixes-c8c4ce4`，旧 `assist-07` 保留。`verification-review-fixes-c8c4ce4.json` 记录 8 份原件/模型响应 hash 未变、四份简介逐字和 SHA256 等于原基线。苏大邮箱、华东师大姓名/职称/邮箱的辅助收益保持；华北电力与上海大学可信字段保持，教授和导师资格分开。HTTP、socket、DNS 均为 0。

本轮未重跑旧 20 页/13 页全部材料，未访问真实教师网站、实际密钥或付费接口。验证字段归属边界与四页缓存兼容性，不证明全院完整性、真实在线接口或全量材料覆盖。没有推送、PR、部署或用户目录同步；准确集成版本的 CI 与正式复审由主代理后续记录。

最终完整验证仅运行一次：`MISSION_C_OPTIONAL_TESTS=1 python -m unittest discover -s tests -v`，运行时代码 `c8c4ce4`，50 项于 89.241 秒全部通过，无跳过，包含动态页面和 OCR；日志为 `%TEMP%/mission-c-review-final-optional.log`。相对原 45 项增加 A、B、C、Fetch 纯文本和 B 英文 5 个公开 CLI 回归测试。指定集成基线 `626172e` 已是本分支祖先，合入检查显示 Already up to date。

## 标题层级补修

对 `03ae076` 的独立 Standards 复审发现 C 原因仍未闭合：`陈晨 h1 → 周宁 h2 → 联系方式 h3 → 邮箱` 会因只检查最近 h3 而再次借用陈晨身份。本轮从集成版本 `ad0e0e334fc7c9bcc0a08d132720977b5e3a563b` 继续同一修复任务，沿用已确认的公开缓存清单到 CLI 产物测试边界，未新增测试边界或外部调用授权。

`2b02300` 按标题级别保留仍生效的标题链：普通 h3/h4 子栏目不消除外层 h2；后续相同或更高层级标题才关闭前一个同级栏目。DOM 祖先各自检查其标题链，因此嵌套联系人区域仍受外层归属约束。`6809cf1` 将同一标题链用于公共/合作者排除，并保留 dt/dd 标签关联，没有扩充“联系方式”等通用栏目词表。

新增 2 项公开 CLI 测试覆盖他人标题后的 h3/h4、嵌套联系人结构，中英文公共/合作者标题后的 h3/h4，以及新个人栏目和合法个人联系正例。`%TEMP%/mission-c-heading-red-C.log` 显示两个子例曾错误采用周宁邮箱；`mission-c-heading-red-context.log` 显示 8 个公共/合作者子例曾错误采用邮箱。`mission-c-heading-green-C.log` 与 `mission-c-heading-green-context.log` 保存对应绿例；后者 15 项辅助字段 CLI 测试于 4.572 秒通过，包含原 A/B/C、英文、Fetch 多身份及 WebPlus 个人卡用例。

运行时代码 `6809cf1732a92688a54f4bf65e5de0fa9ac79c17` 再以只读四页清单回放到新目录 `%TEMP%/mission-c-fields-real4/assist-heading-scope-6809cf1`。`verification-heading-scope-6809cf1.json` 逐项记录 8 份输入资产的 SHA256 未变，4 份简介与 `off` 基线逐字及 SHA256 相等，姓名/职称/邮箱与旧 `assist-07` 相等。苏大邮箱及华东师大姓名/职称/邮箱收益保留，华北电力教授与导师资格仍分开；HTTP/socket/DNS 均为 0。复现脚本与日志为 `%TEMP%/mission-c-heading-real4-verify.py`、`mission-c-heading-real4.log`，旧输出未改。

首轮完整验证仅一次：`MISSION_C_OPTIONAL_TESTS=1 python -m unittest discover -s tests -v`，运行时代码 `6809cf1`，52 项于 105.028 秒全部通过，无跳过，包含动态页面、OCR 及 fake IO；日志为 `%TEMP%/mission-c-heading-final-optional.log`。相对上轮 50 项增加 2 项标题层级公开 CLI 测试，随后先以 `4f55399` 保存当时文档证据。

主代理随后依据代码提出同一 C 的具体嵌套反例：`周宁 h2` 在 `<header>` 中，邮箱在后续 `<div>` 的“联系方式 h3”下。`mission-c-heading-red-wrapper.log` 证实该例仍错误采用周宁邮箱，因此首轮全绿不构成此变体已修复的证据。`393d7e8` 令只含标题内容的包装节点在标题层级判断中透明；有独立正文的相邻个人卡仍作为独立块。未新增通用标题词表。新增公开 CLI 回归及全部辅助字段测试共 16 项于 4.765 秒通过，见 `%TEMP%/mission-c-heading-green-wrapper.log`。

最终运行时代码 `393d7e85eccea02ba0a0354bb30cd520964fc483` 再回放四页到全新 `assist-heading-scope-393d7e8`。同目录 `verification-heading-scope-393d7e8.json` 确认四页字段、四份全文及八份原件 SHA256 均满足上文基线，HTTP/socket/DNS 仍全为 0；复现脚本与日志为 `%TEMP%/mission-c-heading-wrapper-real4-verify.py`、`mission-c-heading-wrapper-real4.log`。所有前轮输出保留。

包装变体真实失败修复后，对新运行时代码再次进行一次 `MISSION_C_OPTIONAL_TESTS=1` 完整验证：53 项于 56.139 秒全部通过、无跳过，包含动态页面、OCR、PDF 和 fake IO。最终日志为 `%TEMP%/mission-c-heading-wrapper-final-optional.log`；这是新增失败及代码修改后的必要重验证，没有覆盖首轮日志。此后仅更新证据文档。

专用实施分支合入当时 `codex/mission-c-assisted` 的 `ad0e0e3` 时为 Already up to date；独立 merger、Standards/Spec 复审及最终集成版本 CI 仍由主代理完成。本轮没有真实站点、真实密钥、付费接口、`secure-api-run`、推送、PR、用户目录或集成工作树写入；不据缓存兼容性声称学院完整性。
