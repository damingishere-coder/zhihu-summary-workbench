# 数据库迁移方案

## 原则

- SQLAlchemy 模型是运行时数据结构，Alembic 是唯一迁移入口。
- 默认开发数据库为 `data/workbench.db`；可通过 `DATABASE_URL` 切换 PostgreSQL。
- Redis 只保存队列、临时进度、Pub/Sub 事件和 Worker 心跳。
- 原始输入、AI 输出、版本、来源、日志和审计分表保存，不用覆盖历史。
- ID 使用 UUID 字符串，时间统一保存 UTC，API 输出 ISO 8601。

## 第一阶段初始迁移

第一阶段创建长期架构需要的基础表。未进入的阶段只创建可迁移的数据容器，不提前实现业务流程。

### 第一阶段直接使用

- `questions`
- `question_sources`
- `article_drafts`
- `article_versions`
- `daily_plans`
- `task_jobs`
- `task_logs`
- `system_settings`
- `model_usage_logs`
- `audit_logs`
- `open_source_references`
- `prompt_templates`
- `prompt_versions`

### 第二阶段预留

- `question_scores`
- `answers`
- `answer_versions`
- `answer_analysis`
- `claims`
- `claim_embeddings`
- `claim_clusters`
- `cluster_answer_links`
- `article_paragraph_sources`

### 第三阶段预留

- `image_templates`
- `image_drafts`
- `image_versions`
- `publish_schedules`
- `publish_records`
- `browser_sessions`

## 关键约束与索引

- `questions.url` 唯一；`questions.content_hash` 建索引。
- `task_jobs.status`、`task_jobs.question_id`、`task_jobs.created_at` 建索引。
- `task_logs.task_id + created_at` 建复合索引。
- `answers.answer_external_id` 唯一；`answers.content_hash` 建索引。
- `claims.answer_id`、`claim_clusters.question_id` 建索引。
- `article_versions.draft_id + version` 唯一。
- `image_versions.image_draft_id + version` 唯一。
- `prompt_versions.template_id + version` 唯一。
- `model_usage_logs.question_id`、`task_id`、`created_at` 建索引。
- 所有外键启用级联或限制策略；历史日志和版本默认限制删除。

## 默认数据

应用启动时以幂等方式写入：

- `provider_mode=mock`
- 每日问题数 10
- AI 并发 3
- 请求超时 60 秒
- 自动发布关闭
- 默认“回答观点提取”Prompt 模板及版本 1
- 第一阶段使用的开源依赖记录

## 执行与回滚

升级：

```powershell
python -m alembic upgrade head
```

查看当前版本：

```powershell
python -m alembic current
```

第一阶段开发环境回滚：

```powershell
python -m alembic downgrade base
```

生产数据回滚前必须备份；本项目脚本不会自动删除数据库文件。

## 第二阶段迁移

Revision：`20260724_0002`

- 为问题增加热榜、回答统计和最近抓取字段；
- 为回答增加作者链接、外部时间、排序、媒体和采集批次；
- 为回答分析增加信息密度、纳入判断和原因；
- 为观点簇增加来源数量、反对理由、适用条件、主流/少数派/争议和信息增量；
- 新增 `opinion_maps`；
- 为文章草稿增加独立质量审核结果；
- 为图片草稿和版本增加纯 CSS 模式、复制状态、上传文件元数据和删除标记。

迁移只新增结构。由于第一阶段初始迁移使用 `Base.metadata.create_all`，第二阶段迁移会先检查列和表是否存在，以同时支持“旧数据库升级”和“从空库直接安装”。
