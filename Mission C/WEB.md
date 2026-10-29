# Mission C 本地页面

需要 Python 3.10+，将整个 Mission C 目录保留在一起。页面与批次 CLI 共用 [批次核心](BATCH.md)，不需要根工作台或根数据库。页面是本机单用户入口，仅监听 `127.0.0.1`，不作为公网认证服务。

## 安装与打开

在 Mission C 目录中，使用本程序自己的虚拟环境：

```text
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-web.txt
.venv\Scripts\python web.py --data-root data
```

Windows 也可运行 `setup.bat --web` 后运行 `web.bat`。Linux 对应使用 `.venv/bin/python`。打开 [本地页面](http://127.0.0.1:8768)，保持服务进程运行。关闭浏览器不终止批次；关闭服务进程会中断当前页，重启同一数据目录后按核心恢复规则继续已排队且未暂停的批次。

1. 点击“载入离线示例”，或多选原格式 XLSX 后点击“上传并预检”。导入与开始分开；预检只报告格式、关联和去重，不代表个人链接有效。
2. 核对学校、学院、输入行及导入问题。选择严格缓存回放或显式在线访问，再点击“开始处理”。默认只提供虚构示例缓存，不访问网页、网络媒体、密钥或收费接口。真实表配示例缓存不会得到真实网页；缓存没有的 URL 明确留为读取异常。
3. 查看处理进度、逐条质量原因与正文保存状态。暂停在当前页处理完成后生效；继续只处理剩余条目。刷新或重新打开会恢复已有批次。重复上传完全相同的文件集合沿用核心的同一批次。
4. 点击“准备大学下载”，下载教师工作簿及全文来源 ZIP。三表与十列遵守项目交付契约；ZIP 内 `records.json` 保留全部已处理记录，`exceptions.csv` 保留待核、暂不可用、失败等输入去向，并有原件、全文与学院关系。学院完整性始终未验证。

上传限 20 个 `.xlsx`，合计 20 MiB，解压总量每文件不超过 100 MiB；文件名不能含路径。损坏文件和坏行由核心报告，不静默丢弃其他合格输入。网页使用分页查看条目和问题，进度接口不传完整正文。

## 自己的缓存与在线选择

启动时指定缓存，页面即可选择“启动时指定的本地缓存”：

```text
python web.py --data-root data --cache-manifest "缓存/manifest.json"
```

清单格式见 [批次说明](BATCH.md)。HTTP 参数只接受配置好的缓存选项，不能指定服务器文件路径。开始时核心把缓存原件快照存入数据目录，后续恢复不依赖原缓存目录。

`web.bat` 开放可选在线能力，上传后仍须在页面明确选择“访问在线网页”并开始；不会自动访问网站。直接运行 `web.py` 的默认策略仅允许缓存，需要在线时启动加 `--allow-live`。Fetch 和模型仍默认关闭。开放付费还需要启动服务时同时加 `--allow-paid --paid-max-calls 正数`，页面逐批勾选许可并给出不超过服务预算的上限；HTTP 参数不能绕过服务端策略。密钥沿用既有进程环境，页面不接收密钥，也不保证提供方可用。持久预算和未知计费尝试由同一核心维护，不能通过删除 `paid-attempts` 来续跑。

默认服务不会执行同一目录内由其他入口排入的在线或付费任务，除非启动策略明确允许。策略不符的任务保留排队状态并显示原因；已有明确允许运行的队列可由后台/CLI按其授权继续。

## 数据保存与搬移

批次、上传副本、队列、缓存快照及结果均在 `--data-root`，可与程序目录分开。先停止页面与其他 worker，再整体备份或搬移数据根；新位置启动时使用同一 `--data-root`，保留 `paid-attempts` 和原件。多个本机入口共用核心进程锁，不会同时执行同一批次。使用本机磁盘，不承诺网络文件系统或跨主机锁。

## HTTP 与浏览器验证

普通 HTTP 测试从公开接口导入、排队、暂停、恢复和下载；真实浏览器测试按需运行（需要 Playwright 及已安装的 Edge）：

```text
python -m unittest discover -s tests -p test_web.py -v
```

在 PowerShell 中先设置 `$env:MISSION_C_BROWSER_TESTS='1'`，可另设 `MISSION_C_BROWSER_EVIDENCE` 为截图输出目录，然后运行 `python -m unittest discover -s tests -p test_web_browser.py -v`。Linux 浏览器验证可安装 Playwright Chromium，并设置 `MISSION_C_BROWSER_CHANNEL=chromium`；HTTP/批次路径无需浏览器。
