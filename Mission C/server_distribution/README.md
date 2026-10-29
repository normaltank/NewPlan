# Mission C 服务器交接

本包接收原格式 Excel，持续处理教师个人主页，自动按大学输出教师 Excel 和全文来源 ZIP。Windows/Linux 需要 Python 3.11+（CI 使用 3.12）。没有操作页面。

1. 解压到本机可写目录；Windows 运行 `setup.bat`，Linux 运行 `bash setup.sh`（可能需先安装 Python venv 支持）。仅首次安装依赖需访问软件源。Linux 解压工具未恢复执行权限时可用 `chmod +x setup.sh start.sh`。
2. 运行 `start.bat demo` 或 `./start.sh demo` 做离线自检：虚构数据独立保存在 `data/offline-demo`，示例输出在 `output/offline-demo`；不改正式队列、不读取私人凭据、不联网。普通无凭据包可执行本步骤。
3. 把写完的 `.xlsx` 原子移入 `input`；支持多文件，忽略 `~$` 临时文件。Sheet1 为 ID/学校/学院/师资URL，Sheet2 为学院ID/个人URL；同文件内同学校相同个人URL去重并保留学院关系，跨文件保留独立批次。执行 `start.bat preview` 或 `./start.sh preview` 查看条目与输入问题，不访问表内网址。
4. 获授权后执行 `start.bat once`（处理一轮后退出）或 `start.bat watch`（持续扫描）；Linux 用 `./start.sh once` / `./start.sh watch`。PRIVATE 包自动读取自身 `.private` 配置，无需使用者填 API；普通包或缺失/损坏凭据会在导入前明确失败。
5. `start.bat status` / `./start.sh status` 查看持久批次、质量、辅助异常与输出目录。完成事件中 `deliveries` 按学校列出 `excel`/`zip` 相对输出目录的路径；每批次独立子目录，`teachers.xlsx` 是教师表，`sources.zip` 包含完整原文、字段来源、异常和原表副本。实际访问失败、未读、身份待核及辅助失败分别保留；任务结束不证明学院完整性。

`config.json` 仅配置输入、持久数据、输出目录和正数扫描间隔（秒）。相对路径以配置文件所在目录为准，支持中文/空格，也可用 `start.bat --config "另一目录/config.json" once`。默认每 30 秒扫描一次。准备好的 Python 可通过 `MISSION_C_PYTHON` 指向其完整路径。

运行方案固定为 DS Fetch supplement + model assist：每个任务最多一次 Fetch、一次模型调用，新批次按去重条目数 N 保存 2*N 预算。未知计费结果不自动重发；跨批次保留全局 URL 尝试去重。辅助失败会输出 `assistance_errors` 并写入 ZIP 异常表，完整原文和可信字段保留。原先无私人 scope 的旧批次/队列会显示 `blocked`，保留原额度与队列，请交维护者核对；本入口不会给它们重新分配预算。若首次导入成功而排队前进程中断，也按此规则保留并阻断，请交维护者核对。不要删除 paid-attempts 来重试。

Ctrl+C（Linux 也支持 SIGTERM）在当前页面完成后退出。重新运行同一配置接着处理未完成页面；重复扫描、原表改名或重启不会重新采已完成条目，也不覆盖原件、旧结果及已生成交付。修改内容生成新批次。交付先在同盘 `.pending-` 目录写齐 Excel/ZIP，再发布完整目录；强制结束时可能保留暂存目录，重启使用新快照，不覆盖它或历史完整结果。异常退出后的尝试记录保留，unknown 不重发。输入问题、辅助/读取/程序缺口、旧队列阻断返回 1；配置或启动失败返回 2；0 仍可能含身份待核，请核对质量和 ZIP。watch 遇单批次缺口继续处理其他批次。

备份/搬移前停止全部写入进程，完整复制程序目录（保留 `.private`）及配置指定的 `data`、`output`、`input`，新机器重跑 setup；无需复制旧 `.venv`。不要只复制 SQLite：原表、结果、锁和 `paid-attempts` 必须一起保留。用同一相对配置搬移整个目录即可续跑。仅支持本机磁盘与单主机运行，不通过网络盘共享数据；不自动安装定时任务或服务。

PRIVATE 包包含可直接提取的共享付费凭据，仅供获授权同事，勿公开上传或转发。逐个文件的用途见 [FILES.md](FILES.md)。本包验证使用虚构离线/假外部接口，未真实采集、付费或部署服务器；浏览器/OCR扩展未包含在四项基础依赖内。
