# 组合版实际目录交付与执行证据

对应 [规格 #30](https://github.com/normaltank/NewPlan/issues/30)、工单 [#31](https://github.com/normaltank/NewPlan/issues/31) / [#32](https://github.com/normaltank/NewPlan/issues/32) / [#33](https://github.com/normaltank/NewPlan/issues/33) / [#34](https://github.com/normaltank/NewPlan/issues/34) 和 [PR #36](https://github.com/normaltank/NewPlan/pull/36)。沿用用户已经确认的组合方案、公开 CLI 验证边界和“离线验证 → 实际交付 → 独立查漏”顺序。

## 实际交付

主代理在 2026-10-28T10:35:55Z 完成用户 `D:\Agent Workspace\Intern\MyPlan\OpenSource\Mission C` 的实际运行验收。交付版本为集成提交 `048f4196843ba36eb5fd90a63872bc6f53235d59`；独立实施源 `478be29635b90a41ad6b2a3a248f41d3c1aa5a0c`，两者 tree 同为 `c6ff827ab4dc731ff53ee56aa1b5bc52df619db6`。受审运行时为 `45f8b6bb5ea38ff86c4d085a11d9e043c8c39a6e` / 代码提交 `5126110`，源最后一条提交只更新负责证据文档。

36 份受控 Mission C 文件在复制前检查既有文件 hash，复制后逐项等于集成代码。84 份便携输入（82 原件/元数据及清单/导入来源）复制到被 Git 忽略的 `Mission C/inputs/assisted-cache-20261028`，保留原字节与修改时间。原始输出、凭据和其他文件不在复制集合中；交付前后 53 项非 Mission C 变更的状态及文件 hash 相同。

实际运行使用这个独立目录自己的 `.venv/Scripts/python.exe`，由 `replay.bat` 进入公开 CLI：

```powershell
cd "D:\Agent Workspace\Intern\MyPlan\OpenSource\Mission C"
.\replay.bat --cache-manifest .\inputs\assisted-cache-20261028\manifest.json
# 默认虚构示例：.\replay.bat
```

验收将输出显式指向新的 `outputs/assisted-delivery-20261028/actual20` 和 `example`，两者均预期退出 `1`，保留历史原站失败。再次运行应使用默认新建输出或另一个未存在目录。

实际20条结果为 13 本地正文、6 提供方待核正文、1 未取得正文；Fetch 19 有文字 / 1 历史失败；模型 4 份实际消费 / 16 缺缓存。13 份本地全文与冻结 `c87eeb7` 逐字及 SHA256 相等，4 页字段收益保持，82 份输入原件/元数据 hash 不变。HTTP、socket、DNS 计数均为 0，本轮付费调用 0。完整机器证据、逐页结果及原件留在上述受控本地输出，公开仓库只保存虚构样本。

## 真实角色与集成

全部子代理显式 `gpt-6.1-sol`、`high`、`fork_turns=none`；使用真实子代理，各实施票有独立分支/工作树。主代理负责调度、需求验收和最后实际目录复制。

| 工单/阶段 | 实际角色与成果 | 独立合入 |
| --- | --- | --- |
| #31 | 实施 `assisted_fetch_resume`；源 `e38b89e`，13 个新增公开 CLI 切片，完整36项通过 | `assisted_merger_resume` → `148519a`，独立13项和默认回放 |
| #32 | `assisted_fields_resume`、`fields_recovery_final` 保存检查点后中断；`fields_finish_after_disconnect` 完成源 `6921909`，8个新增 CLI 切片、完整44项通过 | `merge_32_recover` → `62df8a7`，独立8项/四页原件核对 |
| #33 | 实施 `delivery_20_cache_implement`；源 `2965fd3`，导入/搬移删除原目录的 CLI 红→绿、完整45项、20页及13页冻结基线实跑 | `merge_32_recover` → `626172e`，独立便携入口与原件核对 |
| 第一批审查修复 | `assisted_review_fixes` 后由 `review_fixes_resume_b_c` 接续；源 `03ae076`，完整50项及四页缓存 | `merge_repairs_resume` → `ad0e0e3`；复审仍阻塞，未据测试通过交付 |
| 标题/标签边界修复 | `heading_scope_recovery` → `be41e55`，完整55项、四页缓存；两轴复审仍有真实 P1 | `merge_final_recovery` → `9ac3cd6`，保留该次合入但不宣称验收通过 |
| 最终机制修复 | `ownership_mechanism_repair` 保存 `6c67ad6` 后中断；`ownership_finish_recovery` 发现其本人正例仍失败，修复为 `5126110`，合入当时集成后为 `45f8b6b`，最终证据源 `478be29` | `merge_final_recovery` → `048f419`，独立21项 CLI、前后默认回放各21项原件/正文/候选断言，tree 等于源 |

没有留下实际成果的失联/未启动调度不计为实施完成。每次恢复先检查 Git、已有日志和原件，保留旧输出。已有工单接口不支持原生依赖关系时，实际 GitHub 工单正文的 Parent / Blocked by 保存依赖，不把“发布了工单”当作实施证据。

## 最终验证与正式审查

最终运行时代码 `5126110` 上 `MISSION_C_OPTIONAL_TESTS=1 python -m unittest discover -s tests -v`：58/58，56.423 秒，无跳过，包含本地 Edge、OCR、PDF 和虚构提供方 I/O；原日志见 [完整验证](optional-tests.txt)。修复后的四份真实模型缓存再次只读回放，8 份原件/模型响应 hash 不变、4 份简介等于 `off`、字段等于既有 `assist-07`、网络计数全 0。

Standards 与 Spec 始终独立保存，失败报告没有被最终通过覆盖。原问题包括期望姓名冲突被模型恢复、公共/合作者邮箱、他人标题穿越以及修复引入的本人卡片误拒；具体机制与红绿见 [审查修复](review-fixes.md)。最终运行时之后仅改变证据文档，未改变受审行为。

- [Standards 最终报告](standards.md)：0 阻塞、0 非阻塞。`standards_mechanism_review` 独立运行14个针对性公开 CLI 测试通过。
- [Spec 最终报告](spec.md)：0 阻塞、0 非阻塞。`spec_mechanism_review` 独立运行19个非在线公共 CLI 测试通过。
- 交付代码 `048f419` 的 [CI 成功](https://github.com/normaltank/NewPlan/actions/runs/40674123729)。后续仅证据文件的提交仍按准确提交检查 CI，最终链接在 PR / Issue 执行记录。

## 交付后查漏

实际交付后另派独立子代理，功能与便携审计均已完成。实际角色、禁网回放及搬移证据、修正的交付文案和四类剩余事项见 [独立查漏](post-delivery-audit.md)。审计报告已落盘用户目录的 `outputs/assisted-delivery-20261028/audit/`。

## 限制与复盘

本轮保留已取得的全文，不证明原站全文或全院齐备。淮北师大两页本地文字仅82字、图片未在离线回放中读取；浙大/大连理工部分身份仍待核，6份 Fetch-only 正文缺模型缓存，Hinton 历史504，新增PDF、动态标签、独立CV/论文页及当前在线 DS 服务未验证。候选工具不因此自动进入正式运行。

中断恢复和反复修复暴露两个执行问题：代理树会随环境重建消失，内存中的“运行中”不是持久成果；20项绿日志也不能证明后来提交的第21项正例通过。恢复采用准确提交与落盘日志对照，新增实际 CLI 反例捕捉机械回归；现有 CI 已运行 Mission C 测试，无需再加文字规则或另建测试框架。标题归属的判断继续由独立规范/需求审查约束。额外的工具、遍历和真实调用需求另行安排，达到本轮验收点后停止。
