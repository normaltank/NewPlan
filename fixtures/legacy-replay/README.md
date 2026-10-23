# 离线回放样本

2026-10-21 从旧 MyPlan 的 `tests/fixtures` 复制 7 个既有样本，并逐文件核对 SHA-256。原始路径和摘要见 [来源清单](../../docs/maintenance/2026-10-21-promote-and-clean/fixture-provenance.json)。

当前 `benchmark.py replay` 只读取本目录，不再依赖父级旧测试目录。样本中的页面与标注保持原样；历史 DOM 范围不是独立人工标注的完整简介真值。回放的具体范围由 benchmark.py 和生成的报告说明。
