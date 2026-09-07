# 知乎问题总结工作台

针对一个知乎问题，管理回答聚合、观点提取、共识与分歧、总结草稿和信息图生产流程。

当前仓库已按 [`CODEX_IMPLEMENTATION_SPEC.md`](CODEX_IMPLEMENTATION_SPEC.md) 完成三阶段功能实现；现在进入“真实可用性优先”的系统推进期。代码能力不等于真实外部验收：知乎自动采集仍需通过稳定性门槛，真实提交仍保持人工确认。请以 [`docs/current-roadmap.md`](docs/current-roadmap.md) 作为当前状态和下一里程碑的唯一入口。

## 当前已经提供

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
- Windows PowerShell 启动和测试脚本；
- Manifest V3 Chrome 扩展通过用户正常知乎标签页同源采集；
- 问题池支持手动添加和批量导入；扩展 0.3.0 支持在正常页面同步热榜；
- HTML 清洗、Markdown/纯文本转换、媒体提取、内容哈希去重和基础过滤；
- 批量回答质量筛选和观点提取；
- 本地多语言字符 n-gram Embedding、向量缓存和余弦粗聚类；
- 聚类修正、观点地图、总结文章、段落来源和独立审核；
- 观点簇重命名、排序、写入策略、来源查看、拆分、合并、删除和局部重新分析；
- 问题详情“回答 / 观点地图 / 任务与费用”三栏工作区；
- 草稿审核“文章 / 图片 Prompt 与上传 / 来源与质量”三栏工作区；
- 草稿 Markdown/富文本编辑、选中文字或当前段落改写、撤销和历史版本恢复；
- 中英文图片 Prompt 复制、手动上传、替换、移除、纯 CSS 降级和历史版本；
- 有长度约束的信息图 JSON，以及“知识总结卡 / 观点对比表”两种模板；
- 草稿审核中的信息图完整编辑器：内容排序、删除、字号、模板、背景位置、品牌、页脚和版本恢复；
- Playwright 固定视口 PNG 渲染、字体/图片等待、文字溢出检测、重试、HTML 快照、日志、批量渲染和下载；
- 发布内容准备检查、冻结文章/图片版本、日历排期、拖动改期、每日上限、最小间隔和冲突提示；
- 输入“确认发布”后的人工发布包，以及登录、验证码、风控和浏览器不可用时的安全暂停记录；
- 每日计划只由用户手动执行或继续，启动服务不会触发生产或发布；
- 今日/问题/阶段模型调用与费用、预算暂停、结构化响应缓存、重试和备用模型统计；
- Prompt 列表、新版本、活动版本、测试、回滚和审计；
- 浏览器安全设置、开源组件与许可证页面。

今日计划使用已登录的 Codex CLI 内置生图，不要求单独的图片 API Key。工作台保存本次生图产物，用 HTML/CSS 排版中文并输出 PNG；仍支持人工替换背景。未知生图结果先核对已有产物，禁止自动重复提交。

## 本机使用方式（2026-09-07）

在 RunDock 中手动启动“知乎工作台”，打开 http://127.0.0.1:4173。后端监听 8002；停止整个项目后，下次由用户手动启动。点击首页“执行 / 继续今日计划”才开始生产。

Chrome 需要加载或重新加载 `frontend/dist/extension`（版本 0.3.0），在浏览器设置页完成配对。每题按最多 30 分钟读取可访问回答；不承诺能读到所有回答，文章和发布包会保存覆盖范围。

审核通过后，在发布中心下载 ZIP（Markdown、HTML、PNG、来源快照、版本及校验清单），最后在知乎人工发布。代码检查与真实业务验收分别记录于 [当前状态](docs/current-roadmap.md)。

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

### 日常本机开发：memory 模式（无需 Docker）

本机开发默认使用进程内 memory 队列：FastAPI 会在同一进程内启动共享 Broker 的 Worker，不需要 Redis、Docker 或独立 Worker。

完成后端 `.venv` 和 `frontend\node_modules` 安装后，在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

脚本会执行数据库迁移，启动 `127.0.0.1:8002` 的 FastAPI 与 `127.0.0.1:4173` 的 Vite，并把 PID 和日志写入已忽略的 `logs/` 目录。停止本机服务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-local.ps1
```

### 完整集成/部署回退：Docker 一键启动

只需要安装并打开 Docker Desktop，不需要另外安装 Python、Node.js 或 Playwright。

1. 双击项目根目录的 `start-docker.bat`；
2. 第一次启动会下载并构建镜像，等待时间会比之后更长；
3. 启动成功后浏览器会自动打开 [http://127.0.0.1:4173](http://127.0.0.1:4173)；
4. 不使用时双击 `stop-docker.bat`，数据库和上传文件会继续保留。

Docker 会启动 Redis、FastAPI 后端、Worker 和 Nginx 前端。真实 API 密钥仍只保存在本机 `.env` 中，不会写入镜像。

以下步骤用于需要 Redis 与独立 Worker 的完整 Docker 集成模式；日常本机开发请优先使用上面的 `start-local.ps1`。

### 1. 检查基础软件

需要：

- Python 3.12；
- Node.js 20 或更高；
- Docker Desktop（仅运行完整集成模式时需要）。

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

### 4. 准备信息图渲染浏览器

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

Playwright 固定为 `1.61.0`，只负责信息图 PNG 渲染。本机优先探测系统 Chrome；Docker 镜像安装与 Python 包匹配的 Chromium。知乎采集不再使用 Playwright。

### 5. 构建并安装 Chrome 扩展

```powershell
Set-Location .\frontend
npm.cmd run build:extension
Set-Location ..
```

然后打开 `chrome://extensions`，开启“开发者模式”，点击“加载已解压的扩展程序”，选择 `frontend\dist\extension`。回到工作台“设置 → 浏览器与发布”，生成一次性配对码并粘贴到扩展弹窗。

### 6. 启动全部开发服务

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
- 后端接口文档：[http://127.0.0.1:8002/docs](http://127.0.0.1:8002/docs)
- 健康检查：[http://127.0.0.1:8002/api/health](http://127.0.0.1:8002/api/health)

运行日志在 `logs/` 目录。

### 7. 停止开发服务

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

所有步骤成功后会显示 `All automated tests passed`。

## DeepSeek 配置

默认 `Mock` 模式无需 API Key，可以验证回答筛选、观点提取、Embedding、聚类、观点地图、文章、来源映射、独立审核和图片 Prompt 的完整结构。

如需测试真实 DeepSeek：

1. 在项目根目录把 `.env.example` 复制为 `.env`；
2. 只在本机 `.env` 中填写 `DEEPSEEK_API_KEY`；
3. 重启后端和 Worker；
4. 在“设置 → AI 与模型”中切换并测试。

不要把 `.env`、密钥、Cookie、Token、账号密码或浏览器缓存提交到 Git。设置 API 只返回“已配置/未配置”，不会返回密钥原文。

模型价格会变化，项目不会把价格写死。需要费用估算时，只在本机 `.env` 配置：

```env
DEEPSEEK_INPUT_COST_PER_MILLION=
DEEPSEEK_OUTPUT_COST_PER_MILLION=
```

## 知乎采集与安全边界

知乎接口可能要求登录或返回访问限制。新主流程如下：

1. Chrome 扩展在用户正常登录、可见的知乎问题标签页中优先读取已经渲染的回答，并自动展开、有限滚动和去重；
2. 扩展只回传白名单化的问题/回答字段，不读取或上传 Cookie、密码和 Token；
3. `401`、登录页跳转、`403` 和验证页分别暂停为等待登录或等待人工验证，不消耗任务失败重试；
4. 代表性模式默认使用页面 DOM、最多采集 20 条；完整模式才显式使用知乎同源回答接口；
5. 知乎仍阻断时可导出/导入 `ImportBundleV1` JSON，但界面会明确标注人工来源，不冒充实时自动采集；
6. 不破解签名或验证码，不使用隐身浏览器、代理池、账号池或设备指纹伪造；
7. 旧 `data/browser` 资料原样保留，但不再作为登录有效的依据。

## 草稿中的手动图片 Prompt

打开“草稿审核”后，中间栏提供：

- 有长度限制的信息图结构化文案；
- “知识总结卡 / 观点对比表”模板；
- 标题、结论、共识、分歧、条件和建议编辑、删除与拖动排序；
- 字号、画布、品牌、页脚、背景位置和缩放；
- 生成和重新生成图片 Prompt；
- 复制中文或英文 Prompt；
- 推荐尺寸、比例和负面约束；
- 上传、替换或移除手动生成图片；
- 纯 CSS 背景开关；
- Prompt 和上传图片历史版本；
- Playwright PNG 渲染、溢出提示、HTML 快照、日志和下载。

上传图片保存在本机 `data/uploads/images/`，该目录已被 Git 忽略，不会提交到仓库。

## 发布中心与安全确认

“发布中心”分为“内容准备 / 发布日历 / 发布记录”：

1. 文章必须先通过人工草稿审核；
2. 信息图必须成功渲染；
3. 排期时冻结当前文章版本和图片版本；
4. 同一天不能超过发布上限，相邻排期必须满足最小间隔；
5. 真正执行前必须输入 `确认发布`；
6. 人工模式只准备发布包，不会替用户在知乎提交；
7. 浏览器辅助模式遇到目录缺失、未登录、验证码、风控或页面不可识别会立即暂停并记录。

“执行 / 继续今日计划”是唯一的日计划启动入口。Worker 不再做定时选题；服务重启后未完任务暂停，用户点击继续才恢复。每日目标默认 10 题，热榜与手动候选相互补齐，并展示真实完成数与缺口。

## Prompt、费用和缓存

- `/prompts` 管理所有文本 Prompt；保存只新增版本，不覆盖历史；
- 可以测试指定版本、切换活动版本和回滚；
- `/api/model-usage` 汇总今日调用数、Token、费用、缓存命中、备用模型和重试；
- `DAILY_MODEL_BUDGET` 大于 0 时可配合超预算暂停；
- 结构化响应缓存默认开启，缓存命中仍留下用量记录，但 Token 和费用为 0；
- DeepSeek 主模型失败后最多尝试三次，再按配置尝试一次备用文本模型。

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
http://127.0.0.1:8002/api/health
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

成功时会显示当前 revision `20260827_0006 (head)`。不要直接删除有业务数据的数据库文件。

## 安全边界

- 不绕过知乎验证码、登录限制或风控；
- 不保存知乎账号密码；
- 登录失效或验证码出现时，后续浏览器任务必须暂停；安全验证不会被误报成退出登录；
- 自动发布默认关闭；
- 高风险内容必须人工审核；
- 所有生成内容保留来源和版本；
- 本项目不接入 OpenAI 图片 API。

## 开源参考与许可证

本项目没有复制规格中参考仓库的代码，只参考架构思想。直接使用的主要依赖：

| 项目 | 用途 | 许可证/授权 |
| --- | --- | --- |
| FastAPI | 后端 Web 框架 | MIT |
| React | 前端视图层 | MIT |
| Ant Design | UI 组件库 | MIT |
| SQLAlchemy | ORM | MIT |
| Alembic | 数据库迁移 | MIT |
| Redis 官方容器 | 队列和 Pub/Sub | 以所用 Redis 版本官方授权为准 |
| Microsoft Playwright 1.61.0 | 仅用于信息图 PNG 渲染 | Apache-2.0 |
| Pillow | 本地生成上传背景缩略图 | MIT-CMU |
| OpenBiliClaw `f001c1f` | 借鉴扩展任务下发、同源请求、不导出 Cookie 和真实扩展 E2E 架构；自行实现 | MIT |
| RSSHub 知乎路由 `5151c32` | 仅参考分页、Cookie 有效性检查和接口封装行为；未复制代码 | AGPL-3.0 |
| zhihu-hot-hub `ec324e6` | 未来热榜种子/归档研究，不代替回答采集 | MIT |
| Zhihu++ `80a0971` | 仅研究内容模型和登录体验；未复制代码 | AGPL-3.0 |

以上参考版本记录于 2026-08-23。本仓库没有复制四个参考项目的代码；MIT 项目只借鉴架构，AGPL 项目仅观察公开行为。完整依赖和精确版本以 `requirements*.txt`、`frontend/package-lock.json` 和已安装包许可证文件为准。

## 设计与进度文档

- [仓库分析](docs/architecture/repository-analysis.md)
- [第一阶段实施计划](docs/architecture/phase-1-implementation-plan.md)
- [第二阶段实施计划](docs/architecture/phase-2-implementation-plan.md)
- [第三阶段实施计划](docs/architecture/phase-3-implementation-plan.md)
- [数据库迁移方案](docs/architecture/database-migration-plan.md)
- [产品设计简报](docs/design/product-design-brief.md)
- [第一阶段进度](docs/progress/phase-1.md)
- [第二阶段进度](docs/progress/phase-2.md)
- [第三阶段进度](docs/progress/phase-3.md)
- [第三阶段设计验收](design-qa.md)
