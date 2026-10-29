# Mission C 组合缓存回放与便携包

用于核对 [#30](https://github.com/normaltank/NewPlan/issues/30) 的组合方案及 [#33](https://github.com/normaltank/NewPlan/issues/33) 的导入、离线回放和独立交付。当前操作入口见 [Mission C README](../../../Mission%20C/README.md)。实际 D 目录交付、最终58项验证、独立审查和角色/集成证据见 [交付记录](delivery.md)，交付之后的核查见 [独立查漏](post-delivery-audit.md)。

以下保存 #33 初次准备阶段的原始事实，起点为已独立集成 #31/#32 的 `62df8a73778d5ad0460233f801d902d64f9aee46`，对应源 `2965fd3`、首次集成 `626172e`；阶段性的45项验证与待执行说明不代表最终版本状态。后续审查修复没有覆盖这些历史结果。

## 输入与复现

只读材料为用户 Mission C 的 `outputs/live-tools-20261027` 与 `outputs/diverse-pages-20261027`。库存由主代理提前清点，20 条含 13 份可用 HTML、20 份 Fetch 原响应、4 份绑定相同 HTML hash 的模型原响应。LZJTU 的 39 字节浏览器 DOM 是 HTTP 412 失败原件，按失败保存。

实际证据根为 `%TEMP%\mission-c-assisted-delivery-20261028`；`portable\Mission C` 是独立包，`cache\manifest.json` 为包内相对路径清单。`commands.json` 保存本轮逐次完整命令、退出码和 HTTP/socket/DNS 阻断计数；每条命令有单独日志和 `*-network.json`。`verification.json` 保存逐页基线、字段、媒体、正文差异与输入核对。真实原件和详细结果只存受控本地，未提交 Git。

可在新的输出目录复现；使用已具备基础依赖的 Python（本轮为用户 `.venv\Scripts\python.exe`）：

```powershell
python docs/maintenance/2026-10-28-mission-c-assisted-cache/verify_replay.py `
  --package "本工作树\Mission C" `
  --inventory "只读库存清单.json" `
  --baseline "冻结c87eeb7\Mission C" `
  --output "尚不存在的证据目录"
```

验证程序调用公开 `prepare_cache.py`，搬移其产物到独立包，再调用独立包 `replay.py`；13 份 HTML 各以 `--url --html --output` 经过冻结 `c87eeb7d8083da935717abe0d64b8a83b5ed9406` 的公开 `collect.py`。没有传 `--name`、手工正文选区或预期字段。进程级边界同时阻断 HTTPX、socket 连接与 DNS；每个子进程退出时写真实计数。阻断器仅用于验证，不是运行包依赖。

## 实际结果

- 组合公开 CLI 正常完成 20 条，退出 `1`：13 条 `text_saved`、6 条 `provider_candidate`、1 条 `not_extracted`。
- Fetch 为 19 条 `text_saved`、1 条 `read_failed`。失败项 Hinton 原响应为提供方 504，保留原站历史 `robots_unavailable`；不填正文或字段。
- 4 份模型原响应均为 `evaluated`，其余 16 条明确 `cache_missing`。模型响应中的 usage 是历史用量，本轮 HTTP 请求、socket 连接、DNS 查询均为 0，付费调用为 0。
- 13 份本地正文与冻结基线逐字相等，全文 SHA256 相同，原件输出副本 hash 相同。USTC 本地 1,738 字与基线相同；188 字 Fetch 独立保存，不替换原文。
- 82 份输入资产与元数据在导入前后、回放后逐项 hash 相同，复制后的修改时间纳秒值保持。失败原件也包含在核对中；历史时间未知的条目继续为 `null`。
- SoDa 本人邮箱由缺失变为通过个人引用核验；ECNU 的姓名、专业职称与邮箱由缺失变为有证据候选。NCEPU 与 SHU 既有正确字段保持，NCEPU 的教授与博士生导师资格分开记录。
- SoDa、NCEPU、SHU 的 CSS 提议因 `would_shrink` 拒绝；ECNU 因 `identity_not_confirmed` 拒绝。4 页正文长度仍为 4,789 / 11,087 / 6,208 / 745 字。

7 条缺可用原站 HTML：LZJTU、PKU Limingsong、ZJU Jixiaoyu、Toronto Hinton、CMU Mitchell、Berkeley Jordan、HKUST Qiangyang。其中 6 条仅提供方候选，不因 Fetch 含姓名或邮箱便自动采用；没有模型缓存时保持字段缺失。

## 验证范围与保留缺口

13 份正文保持说明这次辅助没有截短已取得原文，不证明原站全文齐备。ZJU Yingxiaoying 与 DLUT 的身份仍未解决；CHNU 两页本地文字仅各 82 字，图片未读取，独立 Fetch 分别有 4,808 / 697 字候选。所有 Fetch 差异与额外行留在 `verification.json`，没有自动拼接进本地全文。

图片、嵌入页、附件、动态标签、分页和额外个人页仍按原状态标记，离线回放不读取网络媒体；本轮没有新增 PDF、OCR 或动态子页的真实读取证据。19 条 Fetch 有文字不等于完整率，原站 200 与提供方 200 也不相互替代。真实付费适配器只沿用 #31/#32 的虚构边界验证，本票没有读密钥或访问真实教师站点。

红绿日志在 `%TEMP%\mission-c-delivery-{red,green}-01.log`：公开导入命令缺失时失败，新增导入与推荐入口后通过；测试删除原材料目录后从搬移独立包回放，检查本地末段、Fetch、失败 412 与模型缺失。

最终 `MISSION_C_OPTIONAL_TESTS=1 python -m unittest discover -s tests -v` 仅执行一次：45 项在 81.451 秒通过，包含既有 44 项及本票 1 项；Edge、OCR 和虚构边界实际运行，没有跳过项。对应运行时代码提交 `b330e80dd9452433d2752f5375681759c6f5534b`，日志为 `%TEMP%\mission-c-delivery-final-optional.log`。随后仅补充本段验证事实。

另通过 `git checkout-index` 将已提交 Mission C 检出到独立目录，4 个虚构缓存资产的 SHA256 均匹配清单；从任意当前目录运行检出包 `replay.py`，预期退出 `1`，陈晨模型选区实际采用、周宁原失败及缺模型保持，HTTP/socket/DNS 计数均为 0。证据为同一证据根的 `checkout-verification.json`、`checkout-demo.log` 与 `checkout-demo-network.json`；沿用已有 `examples/assisted-cache/.gitattributes` 的原字节保护。

本票准备独立包，整体审查与实际 D: 同步尚由主代理执行，不能据此宣称实际目录交付或 #34 查漏完成；#34 只在实际交付后进行。本地实施提交尚未推送，准确提交 CI 由主代理按最终集成版本跟踪。

辅助字段固定基线审查后的三项归属修复及验证见 [审查修复](review-fixes.md)。
