# 逐文件用途

构建时从现有核心按精确清单取用；源码只保存一套核心。普通包 26 个文件，PRIVATE 另加最后三项。

- `run.py`：唯一无界面入口，preview/once/watch/status/demo；扫描、持久导入意图、固定私人排队、逐页续跑和自动交付。
- `config.json`：三个目录和扫描间隔，路径相对配置文件解析。
- `requirements.txt`：四项固定版本基础依赖（Beautiful Soup、httpx、openpyxl、pypdf）。
- `setup.bat`：Windows 首次创建环境、安装依赖、准备 input。
- `setup.sh`：Linux 首次创建环境、安装依赖、准备 input。
- `start.bat`：Windows 使用包内环境启动 run.py，透传参数。
- `start.sh`：Linux 使用包内环境启动 run.py，透传参数。
- `README.md`：同事安装、预检、启动、停止、续跑、备份说明。
- `FILES.md`：本逐文件清单。
- `mission_c/__init__.py`：核心 Python 包标识。
- `mission_c/assisted.py`：缓存证据、DS Fetch、持久付费预算与 unknown 防重发。
- `mission_c/batch.py`：原格式 Excel 导入、学院关联、持久任务、进程锁、条件首次入队及逐页运行。
- `mission_c/batch_delivery.py`：按大学生成教师工作簿、完整证据与异常 ZIP。
- `mission_c/batch_quality.py`：个人页与身份质量判断，决定教师表或异常去向。
- `mission_c/cli.py`：单个人主页实际采集流程，批次复用此入口。
- `mission_c/export.py`：教师三表十列、CSV/JSON 和超长简介全文导出。
- `mission_c/extract.py`：正文、姓名及页面结构提取。
- `mission_c/fetch.py`：原站 HTTP、robots、重定向和访问失败证据。
- `mission_c/media.py`：附件和图片的保存、内容处理与来源绑定。
- `mission_c/model_assist.py`：DS 模型请求、建议引文校验，保留原文而非摘要。
- `mission_c/ocr_media.py`：已有媒体/OCR解析接口；可选 OCR 依赖未随基础包安装。
- `mission_c/person_names.py`：人名清理和身份判断。
- `mission_c/private_deployment.py`：校验私人配置；显式启动后延迟读取凭据。
- `mission_c/profile_layouts.py`：已支持的个人主页布局。
- `mission_c/quality_fields.py`：职称、本人邮箱及可信字段判断。
- `mission_c/render.py`：已有可选浏览器渲染接口；浏览器依赖未随基础包安装。
- `.private/deployment.json`（仅 PRIVATE）：固定 deepseek-private-v1 配置，只引用同目录 credential.txt。
- `.private/credential.txt`（仅 PRIVATE）：共享 DS 凭据，勿公开、勿写入命令或日志。
- `PRIVATE.txt`（仅 PRIVATE）：授权接收范围及凭据可提取声明。

运行后目录：`input/` 放原表；`data/` 保存 batches.sqlite3、imports 原件、results 尝试、paid-attempts 持久预算/未知计费记录、server-import-intents 输入拥有意图（SHA/原文件名/批次ID/排队阶段）、locks、exports 和 server-deliveries 自动交付收据；`output/` 放按批次和大学分开的 Excel/全文 ZIP，`.pending-` 是同盘交付暂存目录；`data/offline-demo/`、`output/offline-demo/` 只存离线自检材料和结果，不进入正式队列；`.venv/` 是本机安装环境。备份 data 必须完整，导入意图与付费账本一起保留；旧无 scope 队列保留并阻断，不自动赋新预算。上述目录都不进入构建包。
