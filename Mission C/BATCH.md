# Mission C 批次核心

本入口承接原格式双 Sheet Excel，不访问师资列表；学院完整性始终未验证。原单页入口 `collect.py`、`replay.py` 保留。批次核心共用 `mission_c.cli.main`，没有另一份提取器。

在 Mission C 目录运行（Windows 用自己的 Python 路径，Linux 可用 python3）：

```
python batch.py --data-root "data" demo
python batch.py --data-root "data" preview "输入目录"
python batch.py --data-root "data" import "输入目录"
python batch.py --data-root "data" list
python batch.py --data-root "data" enqueue BATCH_ID --cache-manifest "缓存/manifest.json"
python batch.py --data-root "data" run BATCH_ID
python batch.py --data-root "data" pause BATCH_ID
python batch.py --data-root "data" resume BATCH_ID
python batch.py --data-root "data" run BATCH_ID
python batch.py --data-root "data" export BATCH_ID
```

`demo` 从虚构双 Sheet 到离线处理和大学 ZIP 全程执行，不需要密钥或联网。输出 JSON；采集器进度写 stderr。`preview` 不写目录、不采集。导入复制原文件、按文件名与内容 hash 集合识别重复导入，保留 Sheet/行。ID 仅在同一工作簿内关联学院；同 ID 多个师资入口保留。无效文件/行和冲突明示，不把师资入口传给任务 C。个人 URL 去片段、规范 scheme/host，按学校+URL去重，保留多学院、多行来源；不按姓名猜并。

严格缓存为默认，须提供原任务 C 格式的缓存清单。`enqueue` 保存显式运行选项和缓存原件快照，不开始执行；可供页面与后台共用。`run ID` 读取持久选项。`run ID --cache-manifest PATH` 或 `run ID --live` 同样先保存选项再执行。显式 `--live` 才访问个人网站。Fetch/model 默认 off；付费仍须 `--allow-paid --paid-max-calls N`，原采集器在数据根 `paid-attempts` 持久共享预算/未知尝试记录，重启不自动绕过。不得删除该目录来续跑。开发验收未使用真实网站或付费。

暂停在当前个人页处理完成后生效；`resume` 解除暂停但不自动启动进程。`--max-items N` 可分段执行。每页新建独立尝试目录，绑定所有实际文件 hash 后提交。完成任务不重复；进程被终止后锁由系统释放，原有完成任务继续保留，当前不完整尝试留档、下次新建目录。缺失/修改产物显示 `artifact_missing`，保留原件，不自动重采。批次只允许一个执行进程，其他入口明确报忙；不同批次可执行。SQLite 和受控数据应在本机磁盘；不承诺跨主机网络文件系统锁。

大学 ZIP 包含三 Sheet 十列工作簿、全文 CSV/JSON/TXT、原件、原始输入、关系 CSV 与批次状态。教师表按 Sheet 顺序连续编号。原件及聚合记录使用相对引用，整个数据根可停止 worker 后搬移。提供方候选仍待核，实际 HTTP 失败与缓存缺失/字段缺失区分；无可靠教师身份的失败 URL 只列异常，不能伪造教师行。任务 C 的表是待复核个人页结果；批次完成、输入 URL 数、下载人数不能证明全院或人员身份已核实。

## 页面和后台共用 Python 接口

把 Mission C 放入 Python 模块搜索路径后：

```
from mission_c.batch import BatchService, preview
service = BatchService(data_root)
report = preview([input_path])
batch = service.import_files([input_path])
service.enqueue(batch['id'], cache_manifest=manifest_path)
service.run(batch['id'])
service.pause(batch['id'])
service.resume(batch['id'])
service.status(batch['id'])
service.list_batches()
service.export(batch['id'], school=None)
service.demo()
```

返回值全部可 JSON 序列化。ID 为不透明字符串。`status` 包括 `tasks/relations/sources/issues/inputs/counts/state/paused/queued/run_options/completeness`。`queued=True` 表示已有显式持久运行意图；worker 应只取 queued 且非 paused 的批次调用 `run(id)`，不要自己另存队列。终结批次清除 queued。`resume` 不恢复已完成条目。任务状态 pending/running/success/review/failed/program_error/artifact_missing；批次状态 pending/paused/completed/completed_with_gaps/program_error。导出返回 `exports` 数组（school/path/records），path 相对数据根。错误为 ValueError/OSError，公开 CLI 返回2；程序异常与带缺口完成通过状态区别。

`enqueue` 和 `run` 的可选参数：cache_manifest=None, live=False, fetch_mode='off', model_mode='off', allow_paid=False, paid_max_calls=0；run 另有 max_items=None。缓存和 live 互斥。运行参数快照不含密钥；缓存复制后存相对路径。数据根独立于程序目录，默认 Mission C/data 且被 Git 忽略。直接调用 `run` 会占用调用线程，页面应由常驻 worker 调用，不能把它绑在 HTTP 请求生命周期。


批次新增 `task.quality`（category/reasons/eligible_for_workbook）与 `quality_counts`，和原始采集器 text_saved 独立。分类包括 not_read / personal_candidate / provider_candidate / origin_unavailable / temporarily_unavailable / suspected_non_personal / identity_review。只有个人材料候选及具有可靠身份的实际失败记录纳入教师表；其余输入保留 ZIP 的 records.json、exceptions.csv、原件和 batch.json。模板识别仅用主标题/主内容及新闻结构的强信号：带时间的新闻 article 缺少主身份标题时，即使正文标注姓名也留待核对；维护公告标题与正文的明确服务中断共同标暂不可用，只有公告标题则页面身份待核。个人页可以复用 article/发布时间模板，导航、研究术语和个人获奖经历不会仅因含“学院首页/维护/验证/获奖”而排除。该保守分类不是通用网页身份判定或学院完整性证明；弱信号交人工复核，不自动寻找新 URL。

姓名候选本身不构成教师表准入：新批次复用既有采集器的姓名证据，要求主 h1/个人标题卡或明确姓名标签、页面标题佐证。仅由次级章节标题产生的候选留 identity_review；原 teachers.json/record.json 的候选不被改写，大学 records.json 与 exceptions.csv 保留去向。demo 保留“完整经历”旧提取误判反例，另含明确“姓名：李明”的可靠正例及无身份404，便于同时查看教师表和待核明细。

网页预检示例使用 `service.prepare_demo()`，或 `python batch.py --data-root data demo --prepare-only`。返回 `{batch, cache_manifest}`；`cache_manifest` 是相对数据根的 POSIX 路径。新数据根中三任务均 pending、queued=false、artifact=null，不 enqueue/run/export。显式开始时调用 `service.enqueue(batch["id"], cache_manifest=service.root / prepared["cache_manifest"])`，后台 worker 再 `run(id)`。此入口与原完整 `demo()` 共用同一份虚构 Excel/HTML/缓存生成逻辑；原 demo 仍自动完成排队、处理和导出。
