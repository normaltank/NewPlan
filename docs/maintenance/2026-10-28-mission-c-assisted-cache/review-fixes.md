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
