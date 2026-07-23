# 知乎问题总结工作台

针对一个知乎问题，管理回答聚合、观点提取、共识与分歧、总结草稿和信息图生产流程。

当前仓库严格按 [`CODEX_IMPLEMENTATION_SPEC.md`](CODEX_IMPLEMENTATION_SPEC.md) 的三阶段顺序开发。当前分支只实现第一阶段：基础架构、AI Provider、任务队列、Worker、SSE、前端工作台和最小闭环。

## 第一阶段已经提供

- FastAPI REST API 和 OpenAPI 文档；
- SQLAlchemy 长期数据模型和 Alembic 初始迁移；
- Redis 真实任务队列、Pub/Sub 事件和独立 Worker；
- SSE 实时进度；
- DeepSeek Provider 基础请求、超时、重试和 Pydantic 结构校验；
- 不需要密钥的确定性 Mock Provider；
- 本地 Embedding 接口和手动图片工作流能力声明；
- Prompt 模板及版本；
- React、TypeScript、Vite、Ant Design 管理工作台；
- 仪表盘、问题池、问题详情、任务中心、草稿审核、发布准备和设置；
- 亮色/暗色模式、加载/空/错误/禁用/危险确认状态；
- Windows PowerShell 启动和测试脚本。

第一阶段不采集真实知乎回答，也不执行正式发布。真实采集、聚类和文章生成属于第二阶段；图片 Prompt、信息图和发布属于第三阶段。

## 系统结构

```text
React / TypeScript
├─ REST 查询和操作
└─ EventSource 实时进度
        ↓
FastAPI
├─ SQLite（默认）/ PostgreSQL（可切换）
├─ Redis List 任务队列
└─ Redis Pub/Sub SSE 事件
        ↓
独立 Worker
└─ Mock 或 DeepSeek Provider
```

## Windows 11 第一次启动

以下步骤均在项目根目录执行：

```text
C:\Users\你的用户名\Documents\zhihu-summary-workbench
```

### 1. 检查基础软件

需要：

- Python 3.12；
- Node.js 20 或更高；
- Docker Desktop。

在 PowerShell 中运行：

```powershell
python --version
node --version
docker --version
```

成功时会分别显示版本号。

### 2. 安装后端依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

第一条命令创建项目独立 Python 环境，第二条安装后端和测试依赖。成功时最后会显示 `Successfully installed`，且没有红色错误。

### 3. 安装前端依赖

```powershell
Set-Location .\frontend
npm install
Set-Location ..
```

成功时会显示安装的软件包数量。

### 4. 启动全部开发服务

先确认 Docker Desktop 已打开，再运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
```

脚本会：

1. 启动 Redis 容器；
2. 执行数据库迁移；
3. 在后台启动 FastAPI；
4. 在后台启动 Worker；
5. 在后台启动 Vite 前端。

成功后应看到：

```text
Redis 已就绪
数据库迁移完成
后端、Worker 和前端已启动
```

打开：

- 前端：[http://127.0.0.1:4173](http://127.0.0.1:4173)
- 后端接口文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 健康检查：[http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

运行日志在 `logs/` 目录。

### 5. 停止开发服务

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-dev.ps1
```

脚本只停止 `start-dev.ps1` 记录的本项目进程，并停止本项目 Redis 容器。

## 分别启动

都在项目根目录执行。

后端：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1
```

Worker：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-worker.ps1
```

前端：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1
```

## 运行测试

在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-tests.ps1
```

脚本依次运行：

- 后端单元、接口和迁移测试；
- 前端 TypeScript 检查；
- 前端组件测试；
- 前端生产构建；
- Sites 运行壳契约测试。

所有步骤成功后会显示 `第一阶段自动化测试全部通过`。

## DeepSeek 配置

默认 `Mock` 模式无需 API Key，可以验证完整前后端、Worker、数据库和 SSE。

如需测试真实 DeepSeek：

1. 在项目根目录把 `.env.example` 复制为 `.env`；
2. 只在本机 `.env` 中填写 `DEEPSEEK_API_KEY`；
3. 重启后端和 Worker；
4. 在“设置 → AI 与模型”中切换并测试。

不要把 `.env`、密钥、Cookie、Token、账号密码或浏览器缓存提交到 Git。设置 API 只返回“已配置/未配置”，不会返回密钥原文。

## 常见问题

### Redis 显示异常

原因通常是 Docker Desktop 未启动或 6379 端口被占用。

在项目根目录执行：

```powershell
docker compose ps
docker compose logs redis
```

正常状态应为 `healthy`。如果端口被占用，请先停止占用该端口的本地服务，不要修改为未知公网 Redis。

### 页面显示“数据加载失败”

先打开健康检查：

```text
http://127.0.0.1:8000/api/health
```

如果无法打开，查看 `logs/backend-error.log`。如果可以打开但 `redis` 为 `error`，检查 Docker Redis。

### Worker 一直未在线

查看：

```powershell
Get-Content .\logs\worker-error.log -Tail 100
```

正常 Worker 会每隔几秒写入心跳；前端会显示在线 Worker 数。

### 数据库迁移失败

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
```

成功时会显示当前 revision `20260723_0001`。不要直接删除有业务数据的数据库文件。

## 安全边界

- 不绕过知乎验证码、登录限制或风控；
- 不保存知乎账号密码；
- 登录失效或验证码出现时，后续浏览器任务必须暂停；
- 自动发布默认关闭；
- 高风险内容必须人工审核；
- 所有生成内容保留来源和版本；
- 本项目不接入 OpenAI 图片 API。

## 开源参考与许可证

第一阶段没有复制规格中参考仓库的代码，只参考了架构思想。直接使用的主要依赖：

| 项目 | 用途 | 许可证/授权 |
| --- | --- | --- |
| FastAPI | 后端 Web 框架 | MIT |
| React | 前端视图层 | MIT |
| Ant Design | UI 组件库 | MIT |
| SQLAlchemy | ORM | MIT |
| Alembic | 数据库迁移 | MIT |
| Redis 官方容器 | 队列和 Pub/Sub | 以所用 Redis 版本官方授权为准 |

完整依赖和精确版本以 `requirements*.txt`、`frontend/package-lock.json` 和已安装包许可证文件为准。后续阶段若借鉴规格列出的 GitHub 项目，必须先记录项目、版本和许可证；无明确许可证时只参考思路并自行重写。

## 设计与进度文档

- [仓库分析](docs/architecture/repository-analysis.md)
- [第一阶段实施计划](docs/architecture/phase-1-implementation-plan.md)
- [数据库迁移方案](docs/architecture/database-migration-plan.md)
- [产品设计简报](docs/design/product-design-brief.md)
- [第一阶段进度](docs/progress/phase-1.md)
