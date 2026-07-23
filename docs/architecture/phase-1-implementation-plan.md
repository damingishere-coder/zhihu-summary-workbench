# 第一阶段实施计划

## 交付目标

打通以下真实最小闭环：

```text
手动添加知乎问题
→ 写入关系型数据库
→ 创建 Redis 队列任务
→ 独立 Worker 获取任务
→ Mock 或 DeepSeek 执行结构化观点提取
→ 保存结构化结果、草稿、模型用量和日志
→ Redis Pub/Sub 发布进度
→ FastAPI SSE 转发进度
→ React 工作台实时展示结果
```

## 预计新增或修改文件

```text
CODEX_IMPLEMENTATION_SPEC.md
README.md
.env.example
.gitignore
docker-compose.yml
pyproject.toml
alembic.ini

backend/
  app/
    api/
    ai/providers/
    ai/services/
    core/
    db/
    models/
    repositories/
    schemas/
    services/
    worker/
    main.py
  tests/
  alembic/

frontend/
  src/
    api/
    components/
    layouts/
    pages/
    styles/
    test/
  package.json
  vite.config.ts

scripts/
  start-dev.ps1
  start-backend.ps1
  start-frontend.ps1
  start-worker.ps1
  run-tests.ps1

docs/
  architecture/
  design/
  progress/

artifacts/ui/
design-qa.md
```

实际文件清单以阶段验收报告中的 Git 变更为准。

## 后端工作项

1. 建立统一配置、日志和脱敏策略。
2. 建立 SQLAlchemy 模型、Alembic 初始迁移和默认数据。
3. 实现问题、任务、任务日志、设置、Prompt 版本、模型用量和草稿仓储。
4. 实现真实 Redis 队列、Pub/Sub 事件和独立 Worker。
5. 实现任务状态机、取消、失败、有限重试和状态变更审计。
6. 定义文本、结构化输出、Embedding、图片工作流 Provider 接口。
7. 实现 DeepSeek、Mock、本地 Embedding 和手动图片工作流 Provider。
8. 实现问题观点提取服务，输入为问题及可选示例回答。
9. 实现阶段一要求的全部 API、SSE、健康检查和仪表盘汇总。
10. 为接口、状态机、迁移、Mock Provider、JSON 校验和重试编写测试。

## 前端工作项

1. 以选定的方案 1 为视觉基准建立设计 Token 和应用壳。
2. 实现仪表盘、问题池、问题详情、任务中心、草稿审核、发布准备和设置页。
3. 页面数据全部来自后端；不使用静态假数据冒充业务结果。
4. 实现手动添加、批量导入、优先级、加入任务、忽略、删除、重试和取消。
5. 接入 SSE，实时刷新任务进度、Worker、队列、日志和分析结果。
6. 实现加载、空、错误、禁用、成功、危险确认和暗色模式。
7. 为路由、表单验证、状态组件和暗色模式编写测试。

## 第一阶段新增接口

规格要求：

```text
POST  /api/questions/manual
POST  /api/questions/import
GET   /api/questions
GET   /api/questions/{id}
PATCH /api/questions/{id}
POST  /api/questions/{id}/queue

GET   /api/tasks
GET   /api/tasks/{id}
POST  /api/tasks/{id}/retry
POST  /api/tasks/{id}/cancel
GET   /api/queues/status
GET   /api/queues/status/stream
GET   /api/workers

GET   /api/settings
PATCH /api/settings
POST  /api/settings/test-model
```

为支持完整页面和最小闭环，补充：

```text
GET    /api/health
GET    /api/dashboard/summary
DELETE /api/questions/{id}
POST   /api/questions/{id}/ignore
GET    /api/drafts
GET    /api/drafts/{id}
PATCH  /api/drafts/{id}
GET    /api/prompts
GET    /api/prompts/{id}/versions
```

## 第一阶段任务

- `question_claim_extraction`：结构化提取用户提供的示例回答观点。
- 任务状态：`queued → extracting_claims → waiting_review`。
- 异常状态：`failed`。
- 用户操作状态：`cancelled`。
- 重试会创建新的执行轮次并保留旧日志，不覆盖历史。

## 验证顺序

1. 安装依赖和执行数据库迁移。
2. 启动 Redis。
3. 启动后端、Worker 和前端。
4. 执行后端单元/接口测试和前端测试/构建。
5. 用真实浏览器执行添加问题、加入任务、查看 SSE 进度、打开分析结果、重试/取消保护和设置校验。
6. 在 1440×900 与 1280×720 检查布局、暗色模式和长标题。
7. 保存规格要求的 6 张截图。
8. 运行 Design QA，修复 P0/P1/P2，直到 `design-qa.md` 为 `final result: passed`。
9. 更新阶段进度文档、检查敏感文件、提交 Git。
