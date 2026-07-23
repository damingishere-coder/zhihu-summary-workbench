# 第二阶段实施计划

更新时间：2026-07-24
开发分支：`feature/zhihu-summary-workbench`

## 阶段目标

在第一阶段可运行架构上打通核心内容生产链：

```text
知乎问题
→ 回答采集与清洗
→ 基础过滤与批量质量筛选
→ 回答观点提取
→ 本地 Embedding 与粗聚类
→ 聚类修正和观点地图
→ 总结文章与段落来源映射
→ 独立质量审核
→ 草稿人工审核
```

用户确认的产品调整：手动图片 Prompt 工作流进入草稿审核中间栏，随文章一起审核，不建立脱离草稿的独立操作路径。该工作流不调用任何图片 API。

## 复用与改造

- 复用 FastAPI、异步 SQLAlchemy、Redis 队列、Worker、SSE、任务日志和 Provider 抽象。
- 复用 `answers`、`claims`、`claim_embeddings`、`claim_clusters`、`article_drafts`、`article_versions`、`article_paragraph_sources`、`image_drafts` 和 `image_versions` 表。
- 扩展现有 `question_claim_extraction` Worker 为同一条可追踪的第二阶段流水线，不另建不可监控的后台任务。
- 复用既有 Product Design 方案 1、设计 Token、Ant Design 和三栏草稿页面。
- 不复制参考项目代码；采集、清洗、聚类和文章服务均在本仓库自行实现。

## 数据库迁移

新增 Alembic revision `20260724_0002`：

1. 为问题补充热榜、统计和最近抓取字段；
2. 为回答补充作者链接、外部时间、排序、媒体、采集批次字段；
3. 新增 `opinion_maps`，保存可编辑观点地图及版本；
4. 为文章草稿补充独立质量审核结果和审核时间；
5. 为图片版本补充工作流模式、复制状态、上传文件元数据和删除标记；
6. 为常用问题/回答查询建立索引。

迁移只新增表、列和索引，不删除或覆盖第一阶段数据。

## 后端文件

新增：

- `backend/app/collectors/zhihu.py`
- `backend/app/services/content_pipeline.py`
- `backend/app/ai/services/content.py`
- `backend/app/services/image_workflow.py`
- `backend/app/schemas/analysis.py`
- `backend/app/api/routes/answers.py`
- `backend/app/api/routes/analysis.py`
- `backend/app/api/routes/images.py`
- `backend/alembic/versions/20260724_0002_phase_two.py`

重点修改：

- AI 结构化 Schema、Mock Provider、本地 Embedding；
- 数据模型、任务状态机、Worker 流程；
- 问题、草稿、路由注册、配置与默认 Prompt；
- 后端单元、接口、迁移和来源映射测试。

## 前端文件

新增：

- `frontend/src/components/AnswerExplorer.tsx`
- `frontend/src/components/OpinionMapPanel.tsx`
- `frontend/src/components/ImagePromptWorkspace.tsx`
- 对应组件测试。

重点修改：

- `QuestionDetailPage.tsx`
- `DraftReviewPage.tsx`
- `types.ts`
- `api/client.ts`
- `StatusTag.tsx`
- `styles.css`
- 设计文档和 `frontend/AGENTS.md`

## 验证顺序

1. 执行迁移升级和回退/再升级测试；
2. 用固定 HTML 与模拟知乎响应验证采集、清洗、去重和平台阻断；
3. 用 Mock Provider 跑至少 20 条回答的完整流水线；
4. 验证观点簇、来源映射、文章版本、审核和模型用量记录；
5. 验证图片 Prompt 复制、纯 CSS 模式、上传、替换、删除和历史版本；
6. 运行后端、前端、类型、构建和 Sites 测试；
7. 启动真实服务，用浏览器验证 1440×900、1280×720、亮色和暗色；
8. 在用户本地已登录会话可用时测试真实知乎问题；登录或验证码阻断时安全暂停并记录。
