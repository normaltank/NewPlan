# Mission C 页面与维护

需要 Python 3.10+，将整个 Mission C 目录保留在一起。页面与批次 CLI 共用 [批次核心](BATCH.md)，不需要根工作台或根数据库。页面是本机单用户入口，仅监听 `127.0.0.1`，不作为公网认证服务。

## 安装与打开

在 Mission C 目录中，使用本程序自己的虚拟环境：

```text
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-web.txt
.venv\Scripts\python web.py --data-root data
```

Windows 也可运行 `setup.bat --web` 后运行 `web.bat`；Linux 使用 `./setup.sh --web` 后运行 `./web.sh`。打开 [本地页面](http://127.0.0.1:8768)，默认进入简化分发页。保持服务进程运行：关闭浏览器不终止批次；关闭服务进程会中断当前页，重启同一数据目录后按核心恢复规则继续已排队且未暂停的批次。

简化页的使用步骤见 [使用说明](使用说明.md)。选择原格式多份 XLSX 后自动预检，查看总条目及格式/关联问题，再显式开始。上传和预检不会采集；真实输入优先采用服务启动时指定的本地缓存，否则在服务允许时读取在线个人 URL，普通包保持 Fetch/模型/付费关闭；私人预配置包按下述固定方案执行。没有可用方式时明确提示联系维护人员。示例只有“离线试用”创建的批次使用虚构缓存，普通上传不会自动套用示例。

进度为实际处理条目/总数及百分比；暂停在当前页结束后生效。可关闭、刷新或重新打开同一 `?batch=批次ID` 地址；本浏览器记住最近批次，新浏览器打开根地址会恢复服务中最近批次。结果自动准备，按学校下载教师 Excel 和全文来源 ZIP。教师表保持三表/十列，ZIP 内 `records.json` 保留全部已处理记录，`exceptions.csv` 保留待核、暂不可用、失败等输入去向，并有原件、全文与学院关系。处理结束不代表学院完整性已核实。

完整维护工作台保留在 [工作台](http://127.0.0.1:8768/workbench)：多文件选择后点击“上传并预检”，核对逐条来源、导入问题、质量原因和正文保存状态，再选择严格缓存或在线访问并显式开始。可查看候选/错误详情、历史批次，以及按下面策略开放的专业选项；点击“准备大学下载”生成相同交付。两个页面与 CLI 使用同一个 BatchService、队列和下载接口。

上传限 20 个 `.xlsx`，合计 20 MiB，解压总量每文件不超过 100 MiB；文件名不能含路径。损坏文件和坏行由核心报告，不静默丢弃其他合格输入。简化页显示必要导入问题和质量原因；完整工作台分页查看条目/问题，进度接口不传完整正文。

## 自己的缓存与在线选择

启动时指定缓存，简化页自动采用；完整工作台可选择“启动时指定的本地缓存”：

```text
python web.py --data-root data --cache-manifest "缓存/manifest.json"
```

清单格式见 [批次说明](BATCH.md)。HTTP 参数只接受配置好的缓存选项，不能指定服务器文件路径。开始时核心把缓存原件快照存入数据目录，后续恢复不依赖原缓存目录。

`web.bat` / `web.sh` 开放在线能力，简化页在开始前说明将读取表中个人主页，只有点击开始才排队。直接运行 `web.py` 默认仅允许缓存，需要在线时加 `--allow-live`。提供本地缓存时简化页优先使用缓存。普通包简化页保持 Fetch、模型和付费关闭；私人包由服务端固定方案，页面不提交运行选项。

完整工作台保留原专业选项：在线 Fetch/模型还需要服务加 `--allow-paid --paid-max-calls 正数`，并由使用者逐批勾选许可及正数预算，不能超过服务上限；HTTP 参数不能绕过服务策略。密钥沿用既有进程环境，两种页面都不接收密钥，也不保证提供方可用。持久预算和未知计费尝试由同一核心维护，保留 `paid-attempts` 以便恢复。

默认服务不会执行同一目录内由其他入口排入的在线或付费任务，除非启动策略明确允许。策略不符的任务保留排队状态并显示原因；已有明确允许运行的队列可由后台/CLI按其授权继续。

## 数据保存与搬移

批次、上传副本、队列、缓存快照及结果均在 `--data-root`，可与程序目录分开。先停止页面与其他 worker，再整体备份或搬移数据根；新位置启动时使用同一 `--data-root`，保留 `paid-attempts` 和原件。多个本机入口共用核心进程锁，不会同时执行同一批次。使用本机磁盘，不承诺网络文件系统或跨主机锁。

## HTTP 与浏览器验证

普通 HTTP 测试从公开接口导入、排队、暂停、恢复和下载；真实浏览器测试按需运行（需要 Playwright 及已安装的 Edge）：

```text
python -m unittest discover -s tests -p test_web.py -v
```

在 PowerShell 中先设置 `$env:MISSION_C_BROWSER_TESTS='1'`，可另设 `MISSION_C_BROWSER_EVIDENCE` 为截图输出目录。运行 `python -m unittest discover -s tests -p test_delivery_browser.py -v` 验证默认简化页；运行 `python -m unittest discover -s tests -p test_web_browser.py -v` 验证 `/workbench`。Linux 浏览器验证可安装 Playwright Chromium，并设置 `MISSION_C_BROWSER_CHANNEL=chromium`；HTTP/批次路径无需浏览器。

## 私人分发

公开源码可运行 `python build_package.py --output 普通包.zip`。构建通过封闭清单收录已知模块、前端资源和虚构回放/调度示例，不带输入、输出、缓存、data、日志、虚拟环境或私人目录。

所有者已授权的私人分发使用专属配置目录：`deployment.json` 内容为 `{"profile":"deepseek-private-v1","key_file":"credential.txt"}`，同目录 `credential.txt` 仅存凭据。此目录应放在 Git 忽略的 `.private/`，Linux 使用所有者可读写权限（600），Windows 限制为授权用户访问。只把这两个指定文件交给构建入口：

```text
python build_package.py --output Mission-C-PRIVATE.zip --private-config .private/deployment.json
```

私人包含共享付费凭据，仅供授权接收者；任何拿到包的人都能提取和使用该凭据，不能公开上传或任意转发。包使用相对路径，可整体搬移至 Windows/Linux。解压后照常安装依赖并启动 `web.bat` / `web.sh`，启动器自动发现 `.private/deployment.json`，也可通过 `web.py --private-config 路径` 显式指定。普通构建始终不携带该目录。ZIP 成员统一标注 Unix 格式：已知 `.sh` 脚本 755、普通文件 644、私人配置与凭据 600，避免在 Windows 构建时丢失 Linux 可执行位。

启动只读取方案元数据。上传、预检和离线示例不读取凭据或访问外网；实际输入明确点击开始后才检查凭据并排队。缺失、空白或非法凭据明确失败，不能静默降为普通处理。实际 HTTP 有效性与余额只有提供方请求能确认，本轮没有进行真实付费探测。

私人方案固定 Fetch supplement + model assist：每页最多一次 Fetch、一次模型，批次预算为去重任务数的两倍。模型沿用 [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) 与 [JSON Output](https://api-docs.deepseek.com/guides/json_mode/) 的 deepseek-flash 适配器。浏览器不能更改方案、预算或凭据路径；私人部署的完整工作台可查看明细，开始操作使用简版入口。管理员指定缓存与离线示例仍严格离线、零付费。

`data/paid-attempts` 同时保存按批次计数的预算与全局操作/URL/原件哈希尝试。仅在新的私人方案显式开始时，服务将批次 scope 与 2*N 预算一并持久保存。旧队列和普通付费批次没有 scope，继续按共享目录全部历史消费计入全局预算，升级和续跑不自动分配新额度。同一已完成或结局未知的操作不会因换批次或重启而重发。不得删除尝试记录来“恢复预算”。没有 scope 的原 CLI 保持全局预算兼容；有 scope 的批次预算一旦使用不能扩大。

付费失败、预算耗尽或未知结局会显示“辅助未完成”和原因，并写入 ZIP 的 `exceptions.csv`；已取得的可信教师资料仍可下载，提供方候选仍待核。该提示与教师资料是否可交付分别判断，不把本地成功冒充 DS 成功。
