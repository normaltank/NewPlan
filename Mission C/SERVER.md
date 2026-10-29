# 无界面后台与定时扫描

本入口与[批次命令](BATCH.md)、[操作页面](WEB.md)共用 `--data-root` 下的持久批次、显式运行选项和进程锁。它调用同一采集器，不需要根工作台。请将数据放在本机磁盘；不支持多个主机通过网络盘共用锁。

## 服务器同事精简包

交接同事时，可在**源码仓库的 Mission C 目录**执行 `python build_server_package.py --output "Mission-C-server.zip"`。此构建入口和 `server_distribution` 模板仅在源码仓库，旧完整页面分发包不包含它们；现有完整包继续使用下文的 server.py。普通精简包无凭据，支持 preview/status/demo。

获授权的分发者另加 `--private-config "受控目录/deployment.json"`，且输出文件名含 `PRIVATE`。复用已有 `deepseek-private-v1` 元数据，构建时只读取其受控 key_file，不把凭据写入公开源码或日志。PRIVATE 仅额外带 `.private/deployment.json`、`.private/credential.txt` 和 `PRIVATE.txt`。ZIP 记录 Unix 权限：sh 755、私人配置/凭据 600、其余644；Windows仍需接收者保护本机文件权限。

精简包内只有唯一 `run.py` 和四项基础依赖，精确取用17个现有核心模块，不含页面/FastAPI/开发材料/输入输出/缓存/日志/环境；核心在Git中仍只有一套。解压后读包内 README.md，逐文件用途见 FILES.md；Windows用 setup.bat/start.bat，Linux用 setup.sh/start.sh。config.json 只配输入、数据、输出目录与扫描间隔，相对路径支持整体搬移。

`preview` 不导入、不联网；`demo` 的虚构数据库与输出独立放在 data/offline-demo、output/offline-demo，不动正式队列。显式 `once`/`watch` 才读私人凭据并固定 Fetch supplement + model assist，为新批次按去重任务数保存2*N scope；旧无scope批次/队列保留并阻断，不重分额度。每次最多处理一页再检查停止信号，沿用核心全局unknown不重发；大学Excel与全文ZIP自动写入output，返回实际路径。收到停止信号后可按同一配置续跑，不重采已完成页，不覆盖原件与历史交付。安装脚本不注册系统任务或服务。

## 安装与第一次运行

需要 Python 3.11+（CI 使用 3.12）。Windows 在本目录执行 `setup.bat`；Linux 执行 `./setup.sh`，发行版可能需要先安装 Python 的 venv 支持。页面依赖分别用 `setup.bat --web`、`./setup.sh --web` 安装。Linux 的 `--full` 另安装浏览器/OCR及 Chromium，可能还需系统浏览器依赖；后台基本扫描不需要它们。

先用虚构离线批次检查环境：

```text
python batch.py --data-root "演示 data" demo
python batch.py --data-root "演示 data" list
python server.py --data-root "演示 data" worker --once
```

`demo` 生成双 Sheet、缓存、三项个人页任务和大学 ZIP。李明可入教师表；旧章节误候选保留身份待核，无身份404保留异常。完整性始终未验证。最后的 worker 没有未完成队列时直接退出，不重采演示结果。

所有下面的命令从 Mission C 目录执行；也可使用脚本的绝对路径。Windows 用 `server.bat`，Linux 用 `./server.sh` 代替 `python server.py`。脚本使用自身目录里的 `.venv`；已有独立环境时把环境变量 `MISSION_C_PYTHON` 设为 Python 可执行文件的完整路径。脚本、输入、数据路径均可含空格和中文，参数应带引号。

## 扫描、执行与持续处理

只导入输入目录的直接子文件（`.xlsx`，忽略 Excel 的 `~$` 临时文件），不启动任务：

```text
python server.py --data-root "批次 data" scan "原表目录"
```

给定缓存后，明确保存运行选项；`--run` 同时执行共用队列：

```text
python server.py --data-root "批次 data" scan "原表目录" --cache-manifest "缓存/manifest.json" --run
python server.py --data-root "批次 data" worker --once
python server.py --data-root "批次 data" worker --interval 5
python server.py --data-root "批次 data" watch "原表目录" --cache-manifest "缓存/manifest.json" --interval 30
```

`scan` 按原文件字节 SHA256 与已有批次的输入对照，每个新内容单独导入。相同内容改名、重复扫描或重启均复用旧批次；目录新增一个文件不会重新导入其余文件。内容变化新建批次并保存新原件，旧批次保留。跨文件需要合并预览时先使用 `batch.py preview/import 文件1 文件2`；目录扫描按文件保留独立批次。不同内容批次之间不会根据相同 URL 自动合并。

扫描不会重置已有运行选项，也不会解除暂停或重跑已完成条目。显式缓存/live选项会为匹配输入中尚未排队的未完成单文件批次保存运行意图；无选项的扫描只导入。若内容属于已有多文件批次，扫描保留 `not_queued_reason`，需核对整个批次后用 `batch.py enqueue` 排队，避免顺带执行扫描目录外的其他输入。`--run`、watch 和 worker 均只消费已经明确排队且非暂停的批次，包括由页面排队的批次。watch 每轮扫描后处理队列；worker 只处理队列，不读输入目录。建议使用一个常驻执行入口；并发入口由同一批次锁保护，忙碌批次在报告的 `busy` 中保留，下轮再查看。

将已经写完的 Excel 原子移动进输入目录，避免扫描到仍在编辑/上传的文件。损坏文件、无效行和学院关联问题保存在批次 `issues` 中；有效文件仍可独立处理。扫描只检查输入可解析性，不能保证个人URL指向正确教师。运行后查看 `quality_counts`、任务原因与大学 ZIP 的 `records.json`/`exceptions.csv`，区分非个人页、维护/验证页、身份待核和原站失败；这些不能当作教师成功记录。

暂停、继续和下载：

```text
python batch.py --data-root "批次 data" pause BATCH_ID
python batch.py --data-root "批次 data" status BATCH_ID
python batch.py --data-root "批次 data" resume BATCH_ID
python server.py --data-root "批次 data" worker --once
python batch.py --data-root "批次 data" export BATCH_ID
```

暂停在当前条目结束后生效，`resume` 只解除暂停。队列未清除时后续 worker 接着处理。结束进程后重新运行同一数据根即可恢复未完成条目，已绑定产物不覆盖；中断中的不完整尝试保留。缺失/修改产物标 `artifact_missing`，不自动重采。Ctrl+C 或 Linux SIGTERM 请求常驻循环在当前批次结束后退出；强制结束由系统释放锁，下次按持久状态恢复。不要把这些恢复操作解释成全院采齐。

stdout 每轮输出一个 JSON 对象（常驻时为 JSONL），采集器日志在 stderr。`imported` 为本轮新批次，`unchanged` 带原批次 ID、问题和质量计数；`worker.processed` 或 worker 的 `processed` 是本轮处理后的完整状态。退出码：`0` 本轮执行无读取/程序缺口（仍可能有待核）；`1` 有导入问题、读取失败、产物缺失或程序错误；`2` 参数、目录或无法启动的问题。常驻模式继续处理其他批次，正常退出时保留运行期间遇到的 `1`。进程被操作系统强制终止时退出状态由系统决定。

## 在线与费用边界

默认不访问网站，不使用 Fetch/model、不取密钥。严格缓存缺失不会回退联网。真实采集必须显式把缓存选项换为 `--live`；Fetch/model 和付费预算另需显式启用，详见 [BATCH.md](BATCH.md)。worker/watch 读取已经保存的运行选项；不要对未经授权的真实表添加 `--live`。

付费尝试继续在同一数据根的 `paid-attempts` 保存，共享预算及未知计费记录。重启、扫描、改批次都不能删除这些记录或自动重发未知请求。终结任务不会自动重新排队；变更运行选项应在核查原因后使用公开 `batch.py enqueue`。本轮验证仅虚构网页、缓存和回环服务，没有真实网站或付费调用。

## 操作系统定时调用

[调度示例](schedule-examples/)只提供文件，安装程序不会注册服务、定时器或任务，也没有部署未知服务器。

Windows 任务计划程序可以新建一个手动配置的任务：程序选已准备好的 Python 完整路径，参数填写下面一行，起始目录为 Mission C 所在目录；触发器选择所需时间，设置“如果任务已在运行，则不启动新实例”。选运行用户有权限读写的本机路径，不把密钥填进参数。

```text
"C:\Mission C\server.py" --data-root "C:\Mission C data" scan "C:\Mission C input" --cache-manifest "C:\Mission C cache\manifest.json" --run
```

也可让计划任务运行已按本机路径修改的 [windows-scan.ps1](schedule-examples/windows-scan.ps1)，它把 stdout/stderr分开保存并透传退出码。先手工执行一次，核对输入问题、输出和退出状态，再自行配置触发器。

Linux 提供 [watch service](schedule-examples/mission-c-watch.service)、[一次扫描 service](schedule-examples/mission-c-scan.service)及[timer](schedule-examples/mission-c-scan.timer)、[cron示例](schedule-examples/cron.example)。选择常驻 watch 或定时 scan 一种方式，替换绝对路径、运行用户、时间与缓存后再由服务器管理员安装；这些文件未在本机启用。systemd 的 timer 示例按服务器本地时区每日02:00触发，并可补跑关机期间错过的触发。cron 的时区、环境和日志由服务器配置确定。

迁移前先停止所有写入入口，复制整个数据根（原表副本、缓存、结果、SQLite、付费记录），新机器重建环境并给页面和后台相同的 `--data-root`；无需原输入目录即可续跑已排队缓存批次。不得只复制数据库。Windows/Linux基础离线CLI与搬移启动纳入 CI；Linux浏览器/OCR与真实站点、多人公网认证、跨主机共享数据和单文件EXE不属于本次验证。
