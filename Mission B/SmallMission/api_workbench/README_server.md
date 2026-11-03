# Mission B Server 1.0.0 / engine 3.0.7

跨平台 Python 源码包，交给服务器同事安装并执行一次无人值守批次。仅采集指定师资名单链接、按学院去重并逐 URL 比较，不请求教师个人页，不代表服务器已经部署。

## 安装

使用 Python 3.12。以下命令在解压后的代码目录执行；数据目录用绝对路径，代码可只读。

Windows PowerShell：

```powershell
py -3.12 -m venv D:\missionb-env
D:\missionb-env\Scripts\python.exe -m pip install -r requirements.txt
D:\missionb-env\Scripts\python.exe -m playwright install chromium
$env:DEEPSEEK_API_KEY = '由运行人员设置'
D:\missionb-env\Scripts\python.exe -B server_run.py --check
D:\missionb-env\Scripts\python.exe -B server_run.py --input D:\missionb-data\input --output D:\missionb-data\run-001 --cache-dir D:\missionb-data\cache --limits server-limits.example.json
```

Linux shell（Chromium 系统依赖安装可能需要管理员权限）：

```sh
python3.12 -m venv /opt/missionb-env
/opt/missionb-env/bin/python -m pip install -r requirements.txt
/opt/missionb-env/bin/python -m playwright install --with-deps chromium
export DEEPSEEK_API_KEY='由运行人员设置'
/opt/missionb-env/bin/python -B server_run.py --check
/opt/missionb-env/bin/python -B server_run.py --input /srv/missionb/input --output /srv/missionb/run-001 --cache-dir /srv/missionb/cache --limits server-limits.example.json
```

不要把真实环境变量写进脚本、共享配置或日志。包不带密钥、SMTP配置或浏览器二进制。可用 `PLAYWRIGHT_BROWSERS_PATH` 指向运行人员安装的外部 Chromium；代码只读时安装浏览器到用户目录或外部路径。`-B` 防止 Python 在代码目录写字节码。

## 入口与输入输出

`server_run.py --help` 列出全部选项。默认 deepseek，需要环境变量 `DEEPSEEK_API_KEY`，模型为共享核心默认 deepseek-flash。`--check` 仅检查配置，不联网、不要求密钥、不创建输出；不会验证实际网站可达或名单计划是否正确。

`--input` 是 CSV、TSV、TXT、XLSX、XLSM、XLS 所在目录。表中提供学校、学院、师资URL、教师URL；已有输入适配及逐URL集合判定沿用核心。每次 `--output` 必须是新目录，已有目录拒绝运行；`--cache-dir` 可复用外部模型缓存。务必保留输出中的原始输入副本和审计证据。

规则模式需要人工核实的显式 `--plans` JSON，使用 UTF-8（允许 BOM），格式如 `{"plans":{"http://127.0.0.1/list":{"selector":".roster"}}}`。仅给已确认名单区域，不把空示例当作自动识别计划。例：`python -B server_run.py --mode rules --plans /data/plans.json --input /data/input --output /data/run-002 --cache-dir /data/cache`。

规则模式搭配本地HTTP或 `--replay` 保存页面可用于离线验收；一般 rules 批次仍会请求给定网页。deepseek 的 `--replay` 只回放页面，模型缓存未命中仍可能联网付费，不能当作离线开关。`--no-browser` 禁用 Chromium 回退，会减少动态页面能力。

标准输出给出完成事件和结果路径；标准错误给出进度事件。输出中的 `progress.jsonl` 留有限进度计数，`server-status.json` 给出 completed/failed/cancelled 和退出码。退出0表示批次完成，允许含特殊情况；配置/路径错误退出2，致命运行失败退出1，中断退出130。中断/失败保留当时已经写入的证据，不承诺完整结果ZIP；重新运行必须用新目录。外部调度可直接读取退出码和状态文件，无内置常驻服务或调度器。

`results.zip` 只含四列“学校、学院、核验结果、特殊情况说明”的 `核验汇总.xlsx` 和 `更新链接/`（仅错误学院的已完成分组修正表）；说明允许空，无使用说明.txt。正确、特殊学院不混入更新目录。详细审计仍单独在 `results.json`、`manifest.json`、详细Excel、`evidence/`、`inputs/`、`corrected/`，后者包括全部已完成分组，不能当作下载目录整体发送。文件整体被拒绝时学校学院为空，特殊说明明确原文件名，不虚构归属。

遇特殊情况，先看四列说明及详细审计：输入受限则核实文件后提高有限配置；页面不全则检查来源与分页证据；计划不适用则人工确认名单区域。不要根据部分名单删改原表。给定来源全部读取且集合吻合才判正确，等量不同URL仍判错误。

## 有限配置

复制 `server-limits.example.json` 到数据目录调整；`--limits` 接受局部覆盖，未写字段取下列服务器默认。所有值必须是有限正整数，0不代表无限。桌面UI的20文件边界保留。

- `files_per_batch=200`：每批输入文件数；超限文件逐个记录特殊情况。
- `data_rows_per_batch=250000`：每批累计数据行；整文件超出时整体拒绝，继续其他可接纳文件。
- `input_file_bytes=67108864`：每个输入64 MiB；`xlsx_expanded_bytes=268435456`：每XLSX解压后256 MiB。
- `sheet_cells=4000000`：每工作表单元格范围；`merged_cells=500000`：每工作簿合并区域总展开单元格。
- `source_pages_per_college=1000`：学院给定来源和发现分页累计预算，触顶保留未读范围并标特殊情况。
- `api_calls_per_batch=20000`：每批模型请求次数，包括双路判断；这是次数预算，不是费用封顶。
- `model_input_chars=1000000`：每次模型输入字符预算；`model_output_tokens=8192`：每次输出token上限，截断响应不能冒充完整结论。
- `client_pages=1000`、`client_observation_seconds=600`：每来源客户端分页观察页数和秒数；仍保留同源边界、防循环、网络超时及取消机制。

默认是交接起点及有限余量，尚未测得服务器容量；按实际资源逐步调整。配置在 `limits.json` 和 manifest 中留档。程序/测试成功不独立证明全院名单完整性。

## 每个脚本用途与构建

- `server_run.py`：唯一服务器运行入口，解析参数、配置检查、一次批次、状态与退出码。
- `server_export.py`：服务器四列下载及仅错误学院文件过滤。
- `audit.py`：共享名单读取、来源抓取、去重、逐URL对账和审计引擎。
- `input_adapter.py`：共享表格/文档输入适配、整文件限额拒绝。
- `run_limits.py`：有限配置校验与桌面兼容默认值。
- `reporting.py`：共享详细审计、三类结论与Excel/HTML报告。
- `api_engine.py`：双路模型名单结构识别和分页编排。
- `ai_regions.py`：模型页面区域证据、计划应用与提示契约。
- `deepseek_api.py`：环境密钥、有限模型请求与防泄密记录；其历史工具入口不是服务器批次入口。
- `client_pagination.py`：有边界的真实浏览器客户端分页观察。
- `runtime_paths.py`：共享版本与跨平台浏览器位置。
- `requirements.txt`：固定Python依赖；两个example JSON分别为限额、空计划模板。
- `PACKAGE.json`：版本、来源提交、脏工作区标记与逐文件SHA256。

仓库维护者从同一核心运行 `python build_server.py --output /absolute/new/MissionB-Server-1.0.0.zip`。`build_server.py` 的明确 SOURCES 清单只复制上述依赖和本文，不复制第二套引擎；构建脚本保留在仓库，不要求同事拿到仓库。拒绝覆盖已有ZIP。最终分发须从已审查干净提交构建，核对 `source_dirty=false`，再记录ZIP SHA256。实际配置、凭据、任务数据、日志缓存、桌面UI与浏览器二进制均不在清单。
