# 运维手册

本文只适用于 OpenSource 工作台。命令从 OpenSource 目录执行；旧 MyPlan 启动脚本和服务代码已删除。当前工作目录保持原路径。

Mission C 的可搬移程序使用独立环境与数据根，默认简化分发页及维护工作台见 [WEB.md](<../Mission C/WEB.md>)，Windows/Linux 无界面扫描、持续 worker/watch 和定时示例见 [SERVER.md](<../Mission C/SERVER.md>)；不使用下文工作台的加密启动或根数据库。

## 安装与本机启动

首次使用安装 Python 3.12 与 uv，并执行 `./setup.ps1`。该脚本按 [requirements.lock](../requirements.lock) 创建本目录 `.venv`。浏览器采集当前使用本机 Microsoft Edge，入口见 [browser_capture.py](../browser_capture.py)。

已有本机加密密钥时，双击 [start-workbench.bat](../start-workbench.bat)，或执行：

```powershell
./start-workbench.ps1
```

默认打开 [本机工作台](http://127.0.0.1:8765/)。密钥尚未配置时执行以下命令，在隐藏输入提示中填写 DeepSeek 密钥：

```powershell
./secure-api-run.ps1 -Initialize
```

密钥使用当前 Windows 用户的 DPAPI 加密保存到 `.secrets/deepseek-api-key.dpapi`；已有文件不会被初始化命令覆盖。也可由运行环境注入 `DEEPSEEK_API_KEY`。密钥不要写进 Markdown、命令参数、日志或版本库。更换机器／账号后不能假设旧 DPAPI 文件可直接解密，应重新配置。

只查看复核材料、不启动采集 worker 时：

```powershell
./.venv/Scripts/python.exe workbench.py --review-only --port 8767
```

该模式不要求采集 API 密钥，但仍能保存人工操作及更新派生评估，不是数据库只读模式。实际工作端口以启动命令为准。`-SeedNantong` 或 `--seed` 每执行一次都会新建批次，普通启动不要带它们。

## 定时与无界面运行

已有单批无界面执行和每日定时入口：

```powershell
./secure-api-run.ps1 -PythonArgs @('workbench.py','--batch','my-batch.json')
./secure-api-run.ps1 -PythonArgs @('workbench.py','--nightly','02:00','--schedule-config','my-batch.json')
```

`my-batch.json` 为实际批次配置，结构参考 [ntu-batch.json](../ntu-batch.json)。每日时区为 Asia/Singapore；进程需要在指定时刻保持运行，当前调度不会自动追补关机期间错过的时间。同一配置每日触发的记录在数据库保存；批量执行和重试仍需关注任务状态及 API 用量。

上述入口是现有能力，不等于服务器部署已完成。目前仅监听 `127.0.0.1`，有 Host 与同源请求校验。服务器多人使用仍需配置身份认证、访问控制、HTTPS、进程守护和备份；外部推送尚未配置，复核链接先集中展示于工作台。不要仅修改监听地址就宣称已具备公网服务能力。

## 数据与备份

| 内容 | 位置与处理 |
| --- | --- |
| 当前队列、人工决定和审计 | `runs/workbench/workbench.db`；必须备份，不能当作缓存删除 |
| 原始 HTML、图片、附件、结果与评估历史 | `runs/`；复核和重采可能引用旧运行材料，不能只保留数据库 |
| 当前依赖 | `.venv/`；可按锁文件重建，但清理期间保留以确保可运行 |
| 当前密钥 | `.secrets/`；单独受控保存，移机重新配置 |
| 隔离试验 | `experiments/`；保留源码、版本、原件和报告，独立环境不混入主环境 |
| Mission B | `Mission B/SmallMission/`；独立工具的源码、输入、结果与 `release/` 正式包保留；当前 API 辅助核验见[本地完整版](../Mission%20B/SmallMission/api_workbench/README.md)，仅供输入和下载的版本见[精简版维护说明](../Mission%20B/SmallMission/api_workbench/README_lite.md) |
| 本机当前项目备份 | `.local-backups/`；只在本机保存，不纳入 Git 或公开交付；旧 MyPlan 证据归档已按用户要求删除 |
| 学院输入表 | `inputs/colleges/`；从旧父目录迁入，逐文件校验一致 |

一致性备份宜先结束采集并暂停写入，复制数据库及其关联运行目录；在线备份 SQLite 时使用 SQLite backup 接口，不直接只复制可能仍在写入的主文件。恢复时数据库中的运行目录引用也必须存在。当前部分记录使用绝对路径，移机或迁移目录需要检查引用，不能只拷贝一个数据库。

当前项目材料存储与可重建依赖分别管理。清理前核对运行进程、任务引用和路径边界；重解析生成的新评估与原件分开保存，原件和人工决定优先保护。旧 MyPlan 已由用户明确授权清除，先前保留的旧证据 ZIP 也已删除，不能再按早期整理记录恢复。最新范围见 [清除记录](maintenance/2026-10-21-retire-legacy/README.md)。

## 排障与验证

- 网页打不开：检查对应端口是否已启动；8765 与 8767 来自不同启动方式。端口冲突或数据库锁应先确认现有进程，避免启动多个写入 worker。
- 任务失败或数量偏少：查看学院状态、运行日志、入口与分页覆盖、个人页或附件失败；不凭任务结束判定采齐。
- 字段为空：先区分官网未列、材料未读、访问失败或归属冲突，再复用保存材料定位解析问题。
- 修改后验证：先使用隔离数据运行根目录 `test_*.py`；需要外网采集或付费 API 时按具体任务范围执行。

```powershell
New-Item -ItemType Directory -Path runs -Force | Out-Null
./.venv/Scripts/python.exe -m unittest discover -s . -p 'test_*.py' -v
```

工具对照的离线回放使用 `./run.ps1 -Mode replay`；样本已放入本目录 `fixtures/legacy-replay`，不依赖已删除的旧测试目录。这是保存页与队列机制验证，不证明真实入口发现和全院覆盖。依赖、浏览器和正式包的重建方式分别查安装脚本、相应试验 README 和 Mission B 构建脚本。

[离线回归 CI](../.github/workflows/tests.yml) 保留 Windows / Python 3.12 根工作台检查，另以 Windows/Linux 独立环境安装 Mission C 自带基础及页面依赖，执行公开 CLI/HTTP 离线契约；Ubuntu 不安装根 Windows 依赖锁。它不配置采集密钥，不涵盖 Mission B 的全部测试、Linux可选浏览器/OCR、真实学院采集或完整性验收。每次提交以 GitHub 对应提交的最终检查结果为准；配置了 CI 作业不代表该版本已通过。自动发布和服务器部署尚未配置。

## 源码仓库

从公开仓库 [normaltank/NewPlan](https://github.com/normaltank/NewPlan) 获取代码后，按本文安装依赖并配置本机密钥。仓库根目录就是 OpenSource 的内容，不再包含旧 MyPlan 的业务代码和历史提交。`runs/`、`inputs/`、`.secrets/`、本机环境和发布包不上传；这些数据需要按上面的备份方法另行管理。不要将父目录的旧 Git 变更提交到本仓库。
