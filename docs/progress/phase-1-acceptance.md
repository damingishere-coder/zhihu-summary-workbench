# 第一阶段验收报告

验收日期：2026-07-23  
开发分支：`feature/zhihu-summary-workbench`  
长期规格：`CODEX_IMPLEMENTATION_SPEC.md`  
阶段范围：只完成第一阶段；第二阶段、第三阶段未开始

## 1. 结论

第一阶段通过验收。

项目已从仅有规格文档的仓库建立为可运行的前后端工作台，并完成以下真实闭环：

```text
浏览器添加知乎问题
→ FastAPI 校验并写入数据库
→ Redis 队列
→ 独立 Worker
→ Mock / DeepSeek Provider 接口
→ Pydantic 结构化校验
→ 保存任务日志、观点结果和最小草稿
→ Redis Pub/Sub 与 SSE
→ 前端展示详情、进度和草稿
```

验收没有使用静态业务假数据。浏览器截图中的问题、任务、日志和草稿均来自本地数据库中的真实操作结果。

## 2. 第一阶段交付

- FastAPI 应用、OpenAPI、健康检查和分层路由。
- SQLite 默认运行、PostgreSQL 可切换的异步 SQLAlchemy 数据层。
- 长期数据表模型与 Alembic 初始迁移。
- Redis List 队列、Pub/Sub 事件、队列状态和 SSE 心跳。
- 独立 Worker、心跳、状态机、重试、取消和审计日志。
- TextGeneration、StructuredOutput、Embedding、ImageGeneration Provider 抽象。
- DeepSeek OpenAI-compatible 请求基础、超时、重试、JSON/Pydantic 校验和用量记录。
- 无密钥可运行的确定性 Mock Provider。
- 本地 Embedding 接口和手动图片 Prompt / 上传能力声明。
- Prompt 模板、版本和读取 API。
- React 19、TypeScript、Vite、Ant Design 管理工作台。
- 仪表盘、问题池、问题详情、任务中心、草稿列表、草稿审核、发布准备、系统设置和模型测试。
- 亮色默认主题、暗色主题、加载/空/错误/禁用/危险确认状态。
- Windows 启动、停止和一键测试脚本。
- Product Design 参考图、设计文档、真实品牌图片资产和 Design QA。

## 3. 自动化测试

运行命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-tests.ps1
```

结果：

| 项目 | 结果 |
| --- | --- |
| 后端单元 / API / 迁移测试 | 12 passed |
| 后端覆盖率 | 73% |
| TypeScript | passed |
| 前端组件测试 | 4 files / 8 tests passed |
| Vite 生产构建 | passed |
| Sites 运行壳 | 4 passed |

生产构建仍提示主 JavaScript chunk 约 1.25 MB；这不影响第一阶段运行和验收，后续可通过路由级动态导入优化。

## 4. 运行态验收

| 检查项 | 结果 |
| --- | --- |
| FastAPI 健康检查 | `status=ok` |
| 数据库 | `ok` |
| Redis | `ok` |
| 队列后端 | `redis` |
| Redis 容器 | `healthy` |
| 队列积压 | 0 |
| Worker | 1 个在线，`idle`，非 stale |
| Alembic | `20260723_0001 (head)` |
| SSE | 收到 `snapshot` 与 `heartbeat` |
| 前端 | `http://127.0.0.1:4173` 可访问 |

## 5. 真实浏览器闭环

浏览器创建的问题：

- URL：`https://www.zhihu.com/question/99920260723`
- 标题：`为什么很多人制定了学习计划，却很难长期坚持？有哪些真正可执行的改进方法？`
- 优先级：高

验收观察：

1. 表单校验并保存到问题池。
2. 问题详情页显示真实数据库记录。
3. 点击“加入任务”后 Redis 队列被 Worker 消费。
4. Worker 使用 Mock Provider 提取结构化观点。
5. 结构化输出通过 Pydantic 校验。
6. 任务进入“待审核”，进度 100%。
7. 页面显示 Worker、模型、重试次数和 5 条任务日志。
8. 生成最小草稿 v1，并能进入草稿审核页。
9. SSE 连接状态显示“实时更新”。
10. 已完成问题的“加入任务”按钮被禁用，防止重复入队。
11. Mock 模型测试显示 Token、耗时和估算费用。
12. 最终浏览器控制台 0 条 error / warning。

## 6. 响应式与视觉验收

- 1440 × 900：六个要求页面均检查并截图。
- 1280 × 720：仪表盘、各主要路由无页面级横向溢出。
- 亮色主题：默认使用，与选定参考图一致。
- 暗色主题：切换和持久化正常。
- 长中文标题：表格省略、详情完整换行。
- 页面切换：从滚动 650px 的草稿页切换后回到顶部 0px。
- Design QA：参考图与实现图按 1487 × 1058 原始尺寸放入同一对比图，最终无 P0/P1/P2。

Design QA 报告：`design-qa.md`

## 7. 截图清单

- `artifacts/ui/dashboard.png`
- `artifacts/ui/question-pool.png`
- `artifacts/ui/question-detail.png`
- `artifacts/ui/draft-review.png`
- `artifacts/ui/publish-center.png`
- `artifacts/ui/settings.png`
- `artifacts/ui/phase-1-contact-sheet.png`
- `artifacts/ui/dashboard-1280x720.png`
- `artifacts/ui/dashboard-dark-1280x720.png`
- `artifacts/ui/design-qa-comparison.png`

## 8. 安全与阶段边界

- 未提交 `.env`、API Key、Cookie、Token、账号密码或浏览器缓存。
- 页面和设置 API 不回显 DeepSeek 密钥。
- 默认 Mock 模式不需要密钥。
- DeepSeek 真实网络调用没有执行，因为本机未提供密钥；真实调用入口、重试、超时和结构化校验基础已实现。
- 不采集真实知乎回答，不绕过验证码或风控。
- 自动发布保持关闭。
- 第二阶段和第三阶段没有开始。

## 9. 已知非阻断项

- 前端主 chunk 可在后续阶段做按路由拆包。
- DeepSeek 需要用户在本机 `.env` 自行配置密钥后才能做真实计费调用测试。
- 参考图是高数据量概念状态；实现截图只展示真实本地任务，因此表格行数较少。
