# 工具试验与保留方案

OpenSource 已作为当前项目使用；本目录继续承担隔离对照，不把试验安装自动并入主环境。报告中的结果属于对应时间、样本、参数与版本，不能当作任意学院的准确率保证。

| 目录／报告 | 内容与当前定位 |
| --- | --- |
| [DeepSeek Fetch](deepseek-fetch-20261018/REPORT.md) | 保存主流程副本进行典型学院对照；当前未替换主流程获取模块 |
| [网页与文档工具对照](tool-comparison-20261018/REPORT.md) | Firecrawl、Jina、Docling 的页面／文档样本；Docling 本地环境和模型保留供后续验证 |
| [本地工具补测](local-tools-20261018/REPORT.md) | Scrapy、Scrapling、ScrapeGraphAI；保留源码、锁文件、输入与结果，不能凭返回 JSON 推断整院采齐 |
| [Jina API／MCP 对照](jina-mcp-20261018/README.md) | 用户决定：仅作保留，暂不接入正式流程，也不自动用于失败回退 |
| [最早对照报告](../docs/history/initial-report-20261014.md) | 2026-10-14 初始试验的历史结果，不能代替当前工作台说明 |

Stagehand 是候选参考，不在此宣称已经完成全流程实测。是否扩大或替换工具，需用相同原件、身份及字段依据比较漏人、错人、完整简介、人工量和费用，再按用户决定实施。

试验的代码、环境、数据库、输出和密钥保持隔离。当前 Jina MCP 配置仍保留于本项目 `.codex/config.toml`；它的存在不代表工作台会调用。密钥保留在受控的本机加密存储，报告与仓库不写入密钥内容。

2026-10-21 清理删除了本地工具试验的 `.uv-cache` 下载缓存，保留其虚拟环境和浏览器；Docling 的环境与模型也保留。历史试验结果未重算。具体整理与恢复见 [维护记录](../docs/maintenance/2026-10-21-promote-and-clean/README.md)。
