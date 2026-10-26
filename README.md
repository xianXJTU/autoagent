# autoagent

本地单用户的“需求 → 可运行源码”生产线与评测台。

用户用一句模糊需求开始，系统多轮追问、生成可审阅的需求文档；通过后由策划者拆分计划、验收者先写测试、编码者并行实现、验收者整体把关，最后交付可启动的源码，并对整次运行做全量评测。

## 已实现

- 需求对齐：轮次制提问，最多 5 轮；问题逐题独立成卡片，可一键采用推荐做法或自行填写，用户可随时说“够了”。
- 文档审阅：版本对比、修改意见、显式通过后才开工。
- 代码计划：后台可见，模块数不超过 7，接口、文件归属与测试清单齐全。
- 测试先行：验收者在编码前生成测试并冻结，编码者不得修改测试。
- 并行编码：每个模块独立工作树，技能召回后注入，最多 5 轮修复。
- 合并与验收：按依赖顺序合并，合并后跑集成测试，验收最多 2 轮。
- 交付：启动脚本、依赖清单、测试脚本与压缩包；预览按需启动。
- 记忆：会话、项目、全局偏好、案例四层；置信值、衰减、冷备、冲突裁决。
- 上下文压缩：窗口六成与 20 万 token 取小，硬约束从磁盘重注入。
- 评测：确定性指标 + 模型评审、分项证据、每次运行全量数据、独立页面、黄金集。
- 界面：React + Vite，浅色 Codex 式布局，包含对话、文档、文件预览与评测页。
- 项目删除：支持彻底删除生成物与记忆；可选择保留匿名轨迹或连轨迹一起删除，也可在删除前导出源码。

## 环境要求

- Windows，Python 3.13，Node 18+，MySQL 8.0。
- 本地模型接口：DeepSeek 对话模型与 Qwen 向量模型（OpenAI 兼容）。
- 不需要容器运行时。

## 快速开始

1. 准备本地配置

```powershell
Copy-Item .env.example .env
# 编辑 .env，填写数据库密码、DEEPSEEK_API_KEY、EMBEDDING_API_KEY
```

2. 数据库

```sql
CREATE DATABASE IF NOT EXISTS autoagent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS autoagent_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'autoagent_app'@'127.0.0.1' IDENTIFIED BY '你的本地密码';
GRANT ALL PRIVILEGES ON autoagent.* TO 'autoagent_app'@'127.0.0.1';
GRANT ALL PRIVILEGES ON autoagent_test.* TO 'autoagent_app'@'127.0.0.1';
FLUSH PRIVILEGES;
```

3. 后端

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe scripts\seed_skills.py
```

4. 前端

```powershell
cd frontend
npm install
npm run build
cd ..
```

5. 启动

```powershell
.\scripts\run.ps1
```

打开 http://127.0.0.1:8010 。

如果 8010 已被占用，可以换一个端口：

```powershell
.\scripts\run.ps1 -Port 8011
```

然后打开 http://127.0.0.1:8011 。确认旧实例是否占用端口：

```powershell
Get-NetTCPConnection -LocalPort 8010 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess
```

需要停止旧实例时：

```powershell
Get-NetTCPConnection -LocalPort 8010 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

## 测试

```powershell
.\scripts\test.ps1
cd frontend; npm run test:e2e
```

- 后端：pytest，覆盖单元、集成与完整链路端到端（假模型）。
- 前端：Playwright 冒烟与逐题卡片、项目删除测试，独立端口 8020（避免占用正在使用的 8010）。
- 真实模型冒烟：`python scripts/smoke_live.py`（会消耗少量额度）。

## 目录

- `INFO.md`：业务需求文档（已通过）。
- `PLAN.md`：代码计划（已通过）。
- `QUESTION.md`：实现过程中的问题与决策记录。
- `backend/`：FastAPI、编排、代理、记忆、技能、评测。
- `frontend/`：React 界面。
- `skills/`：技能库，每个技能一个目录。
- `golden_set.json`：评测黄金集。
- `workspace/`、`data/`：运行时生成，已被忽略。

## 安全边界

- 生成物只能读写自己的项目目录；破坏性命令会被拦截；所有命令留痕。
- 本机没有容器级沙箱，联网限制是软件层尽力而为，不是硬隔离；界面与文档均明示这一点。
- 密钥只存放在本地未跟踪的 `.env`，日志、事件与评测报告统一脱敏。
- 详情见 `INFO.md` 的安全章节与 `QUESTION.md`。

## 已知限制

- 暂停与取消在阶段边界生效，长节点不会被立即打断。
- 前端构建产物不纳入版本库，克隆后需要执行一次 `npm run build`。
- 本机 8000 端口可能被其他服务占用，默认使用 8010。
- 生成物限定 Python 技术栈；多语言与硬沙箱列入后续版本。
