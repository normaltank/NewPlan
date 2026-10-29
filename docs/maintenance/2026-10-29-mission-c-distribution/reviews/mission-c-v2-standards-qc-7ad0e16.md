# Standards · QC 修复增量复审

固定范围：`1636ea9fb1117dfe0c246a80f12480eaede0c39c...7ad0e16a3ef55656613fc08962d5cd74cbbbbb31`；tree `f6ba8c91dc4fac5e6a2f026ecd1f4e12ef8c65ec`。全部三文件（BATCH.md、batch_quality.py、test_batch.py）均审读；沿用已读实际 code-review 技能、本树 AGENTS/CONTEXT/GLOSSARY/docs/agents 规范及十二项 Fowler 启发式，跳过工具强制项。

## Blocking

0。未发现新增身份准入、原件保留或隔离验证的阻塞规范问题。新增新闻/维护反例通过公开 Excel→CLI→缓存→导出检验，保留原姓名候选、完整正文与原 HTML，排除教师三表；个人页复用 news/article/time 模板的正例仍准入。符合 AGENTS.md:18（具体反例、原件及成功样本）和 CONTEXT.md:25、43–45（身份疑点保留、完整性不由程序成功推定）。原 extract.py Git blob 前后同为 `d755b843547d219fda7fba98833800ac0a08f795`。

## Nonblocking

[P3] 当前文档有窄范围例外未说明。规则 `docs/README.md:45` 要求“当前说明应与实现相符”；新 `Mission C/BATCH.md:52` 写“只有公告标题则页面身份待核”。但 `<title>/<h1>系统维护公告</…>`、正文仅“这是一份历史公告，原内容已归档。”会先命中旧 `batch_quality.py:19,24`，得到 `temporarily_unavailable`，没有走新增 `:26` 的 `identity_review`。建议文字说明带系统/网站前缀的旧标题强规则优先，或按预期统一类别。该条仍 `eligible_for_workbook=false`，不会复发误入教师表阻塞。已从公开 CLI 实际复现，完整 argv/stdout 在 `mission-c-v2-standards-qc-title-7ad0e16.json`。

十二项 smell 未见本增量新增可行动发现；原 run/enqueue 重复选项建议维持延后。

## 实际验证与边界

独立运行 award_news、maintenance_notice、personal_navigation 三个公开 CLI 回归：3 项通过，12.669 秒，日志 `mission-c-v2-standards-qc-tests-7ad0e16.txt`；另执行上述纯虚构标题边界反例。结束 HEAD/tree 精确且源树 clean。未全套/浏览器重跑，无真实网站、paid/key、私有 SQL 或源代码写入。后续 UI 简化、准确新版本 CI 和物理分发交付不在本次固定范围。结论：blocking 0；nonblocking 1。
