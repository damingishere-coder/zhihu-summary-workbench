# 知乎问题聚合总结与信息图生成系统
## Codex 三阶段完整开发指令

> 文档用途：将本文件放入目标代码仓库根目录，并交给 Codex 作为完整开发规格。
>
> 推荐文件名：`CODEX_IMPLEMENTATION_SPEC.md`
>
> 核心原则：Codex 可以一次读取完整文档，但必须严格按“第一阶段 → 验收 → 第二阶段 → 验收 → 第三阶段 → 总验收”的顺序执行。不得为了展示进度同时铺开所有模块，不得只搭空页面、空接口或伪实现。

---

# 0. 给 Codex 的总执行命令

你现在需要在当前代码仓库内，设计并实现一套“知乎问题聚合总结与信息图生成系统”。

系统不是从全网搜索答案，而是针对一个知乎问题，读取该问题下已有的大量回答，对回答进行清洗、筛选、观点提取、语义去重、观点聚类、共识与分歧识别，再生成一篇新的结构化总结型回答，并生成一张放在回答开头的“一图看懂”信息图。

系统每天默认处理 10 个问题，来源包括：

1. 知乎热门问题；
2. 用户手动推荐的问题。

系统必须提供一个完整的前端管理后台，用于：

- 查看问题池；
- 手动添加问题；
- 查看采集回答；
- 查看观点聚类；
- 审核和修改总结文章；
- 审核和修改总结图；
- 管理每日任务；
- 管理发布排期；
- 查看执行日志、失败原因、模型调用和成本。

请先分析现有仓库，再开始编码。不要直接推翻已有架构，不要删除现有可用功能，不要把多个 GitHub 项目机械拼接。

---

# 1. 必须遵守的执行方式

## 1.1 首先分析仓库

开始编码前必须完成：

1. 扫描项目目录；
2. 判断当前前端、后端、数据库、队列、浏览器自动化和 AI 调用方式；
3. 找出可复用模块；
4. 找出重复或冲突模块；
5. 输出准备新增和修改的文件清单；
6. 输出数据库迁移方案；
7. 输出三阶段实施计划；
8. 创建独立 Git 分支；
9. 确认项目当前可以启动或记录现有启动问题；
10. 不得在未分析仓库的情况下直接重构。

建议分支名：

```text
feature/zhihu-summary-workbench
```

## 1.2 三阶段顺序

严格按以下顺序：

```text
第一阶段：基础架构、AI Provider 骨架、任务系统、前端工作台和最小闭环
    ↓
第一阶段构建、测试、截图和验收
    ↓
第二阶段：知乎采集、DeepSeek 文本分析、Embedding、聚类、文章生成
    ↓
第二阶段构建、测试、截图和验收
    ↓
第三阶段：GPT 生图、信息图模板、发布中心、成本控制和完整验收
```

只有上一阶段达到验收条件，才允许进入下一阶段。

## 1.3 不允许的交付方式

禁止：

- 只创建路由和空页面；
- 用静态假数据冒充真实功能；
- 用 TODO 代替核心逻辑；
- 把所有代码写进单个文件；
- 在业务代码里直接散落第三方 API 调用；
- 在代码里写死 API Key、Cookie、模型名和知乎账号密码；
- 未经测试就声称完成；
- 为了赶进度删除来源追踪、版本记录或错误处理；
- 自动绕过验证码、平台登录限制或风控。

---

# 2. 产品定位

系统名称：

**知乎问题总结工作台**

核心内容形式：

> 阅读一个知乎问题下的大量回答，将其中的共识、分歧、经验、争议、条件和建议整理成结构化总结，并生成一张“一图看懂”的信息图放在回答开头。

系统不是简单拼接高赞回答，也不是把前十条回答换一种说法。

系统的内容价值应当来自：

- 大量回答的结构化阅读；
- 重复观点合并；
- 主流共识识别；
- 主要分歧识别；
- 不同结论背后的适用前提；
- 少数派但有价值的观点；
- 个人经历与普遍结论的区分；
- 高风险事实提示；
- 可保存、可转发的信息图。

---

# 3. GitHub 参考项目和改造原则

本项目没有一个现成仓库可以直接覆盖全部需求。

采用：

> 一个主骨架参考 + 多个局部参考 + 核心业务自研

## 3.1 任务系统和前端监控主参考

### `rjalexa/fastapi-async`

参考：

- FastAPI；
- React；
- TypeScript；
- Vite；
- Redis 任务队列；
- Worker；
- 重试；
- 延迟任务；
- 死信队列；
- SSE 实时进度；
- 任务列表和任务详情；
- Worker 状态；
- 队列监控；
- Docker Compose。

改造原则：

- Redis 只负责队列、临时状态、实时进度和缓存；
- PostgreSQL、SQLite 或现有关系型数据库负责长期业务数据；
- 如果现有项目已经有成熟队列，不强行替换，只参考其任务状态和监控思路。

## 3.2 知乎热门问题采集参考

### `SnailDev/zhihu-hot-hub`

参考：

- 知乎热门问题获取；
- 热榜顺序；
- 标题、链接、回答数和热度解析；
- 请求重试；
- 数据归档。

接口和字段不得散落写死，必须集中封装。

需要实现接口模式和 Playwright 页面模式两种采集方式；接口模式失败时，可切换页面模式。

## 3.3 知乎正文清洗参考

### `chenluda/zhihu-download`

参考：

- 知乎 HTML 结构处理；
- HTML 转 Markdown；
- HTML 转纯文本；
- 图片、动图、公式、视频和链接卡片处理；
- Cookie 配置；
- 内容清洗；
- 请求重试。

该项目主要处理专栏，不等于问题回答采集器。以下内容必须自行开发：

- 问题页解析；
- 回答分页；
- 回答 ID；
- 回答统计数据；
- 回答作者；
- 回答增量更新；
- 回答去重；
- 回答来源关系。

## 3.4 语义聚类参考

参考：

- `simonw/llm-cluster`
- `google-marketing-solutions/ml_toast`

参考其：

- Embedding；
- 相似度计算；
- K-Means；
- HDBSCAN；
- UMAP；
- 聚类代表项；
- 聚类标签。

不要仅靠传统聚类直接生成最终结论。

正确流程：

```text
回答清洗
→ AI 提取观点
→ 观点级 Embedding
→ 相似观点粗聚类
→ DeepSeek 修正聚类
→ 共识、分歧和少数派识别
→ 观点地图
```

## 3.5 信息图渲染参考

参考：

- `microsoft/playwright`
- `bubkoo/html-to-image`

推荐分工：

- 后台稳定批量导出：Playwright；
- 前端即时预览和手动导出：html-to-image。

不让图片模型直接承担大量中文文字排版。

## 3.6 发布中心交互参考

参考：

- `gitroomhq/postiz-app`
- `trypost-it/trypost`

只借鉴：

- 内容准备；
- 排期日历；
- 发布状态；
- 执行记录；
- 失败重试；
- 内容预览。

不要把其完整后端直接并入本项目。

## 3.7 许可证要求

使用任何参考项目之前必须：

1. 核查许可证；
2. 记录项目名称、版本和许可证；
3. 无明确许可证时只能参考思路，自行重写；
4. 保留必要的版权声明；
5. 在 README 增加“开源参考与许可证”章节；
6. 不引入 Python 2 或长期无人维护的旧知乎 SDK。

---

# 4. 平台边界和安全要求

系统不得设计为绕过验证码、登录限制或平台风控的工具。

必须遵守：

1. 仅处理用户正常可见页面；
2. 使用用户本地已经登录的浏览器会话；
3. 不保存知乎账号密码；
4. 不破解验证码；
5. 不实现代理池、账号池、设备指纹伪造；
6. 出现验证码时暂停任务；
7. 登录失效时暂停任务；
8. 页面结构无法识别时安全失败；
9. 发布默认需要人工审核；
10. 全自动发布开关默认关闭；
11. 采集和发布设置合理间隔；
12. 每篇生成内容保留原回答来源；
13. 对医疗、法律、金融和投资等高风险内容强制人工审核；
14. 不隐藏 AI 辅助创作事实；
15. 所有平台适配器必须可替换。

---

# 5. 总体业务流程

```text
知乎热门问题采集 / 用户手动添加
                ↓
             问题池
                ↓
       每日计划选取待处理问题
                ↓
          获取问题基本信息
                ↓
          分页获取问题回答
                ↓
       HTML 清洗、去重、基础过滤
                ↓
          回答质量筛选与抽样
                ↓
           单条回答观点提取
                ↓
       观点 Embedding 和粗聚类
                ↓
      DeepSeek 聚类修正与观点命名
                ↓
       共识、分歧、条件、风险识别
                ↓
             观点地图
                ↓
           总结文章生成
                ↓
      段落与原始回答来源映射
                ↓
           文章独立质量审核
                ↓
          信息图结构化文案
                ↓
前端生成图片 Prompt，用户手动复制到 GPT 生成图片（第三阶段）
                ↓
       HTML/CSS 叠加准确中文
                ↓
        Playwright 导出 PNG
                ↓
       前端人工审核和版本管理
                ↓
            加入发布队列
                ↓
       手动发布或辅助定时发布
                ↓
            保存发布记录
```

---

# 6. AI 服务架构——从第一阶段开始建立

> 重要决策：本项目不接入 OpenAI 图片 API。用户不为图片 API 充值。程序只生成图片 Prompt，并由用户在 ChatGPT 中手动生成图片后上传回系统。


AI 架构不能等业务功能完成后再补。

第一阶段必须先铺好统一 Provider 和业务服务接口；第二阶段接入 DeepSeek 核心文本能力；第三阶段接入 手动图片 Prompt 能力和高级成本控制。

## 6.1 Provider 层

至少定义：

```text
TextGenerationProvider
StructuredOutputProvider
EmbeddingProvider
ImageGenerationProvider
```

实现或预留：

```text
DeepSeekProvider
LocalEmbeddingProvider
MockProvider
ManualImageWorkflowProvider
```

其中 `ManualImageWorkflowProvider` 不调用任何图片 API，只负责：

- 根据观点地图和信息图模板生成图片 Prompt；
- 生成中文 Prompt 和可选英文 Prompt；
- 在前端展示并支持一键复制；
- 保存 Prompt 历史版本；
- 接收用户手动上传的 GPT 生成图片；
- 将上传图片绑定到对应问题、草稿和图片版本。

所有第三方模型调用只能存在于 Provider 层。

路由、Worker、采集器、文章生成器、审核器和图片服务不得直接调用 DeepSeek 或 OpenAI SDK。

## 6.2 业务 AI 服务层

在 Provider 层上定义：

```text
QuestionEvaluator
AnswerQualityEvaluator
AnswerClaimExtractor
ClaimClusterRefiner
OpinionMapGenerator
ArticleGenerator
ArticleReviewer
InfographicContentGenerator
VisualAssetGenerator
```

业务服务只依赖接口，不依赖具体模型供应商。

## 6.3 模型角色

业务代码只使用模型角色，不直接写死模型名称：

```text
fast_text_model
reasoning_model
embedding_model
image_model
fallback_text_model
```

默认配置建议：

```yaml
ai:
  fast_text_model:
    provider: deepseek
    model: deepseek-v4-flash

  reasoning_model:
    provider: deepseek
    model: deepseek-v4-flash

  fallback_text_model:
    provider: deepseek
    model: deepseek-v4-flash

  embedding_model:
    provider: local
    model: configurable-multilingual-embedding

  image_prompt_model:
    provider: deepseek
    model: deepseek-v4-flash

  image_generation:
    provider: manual
    mode: copy_prompt_and_upload
```

模型名必须通过环境变量或设置页面修改。

启动时可以调用供应商的模型列表接口验证配置，避免模型名称过期后静默失败。

## 6.4 DeepSeek 分工

`deepseek-v4-flash` 默认负责全部 DeepSeek 文本任务：

- 问题分类；
- 问题价值评分；
- 回答质量筛选；
- 批量观点提取；
- 普通质量审核；
- 信息图文案压缩；
- 生图提示词生成；
- 复杂长回答提取；
- 聚类修正；
- 共识与分歧识别；
- 观点地图；
- 总结文章；
- 段落来源映射；
- 高风险内容审核。

## 6.5 Embedding

Embedding 不与 DeepSeek 文本模型强绑定。

优先支持：

- 本地多语言 Embedding；
- 后续可替换的独立 Embedding API；
- 向量结果缓存；
- 只对新增或变化观点重新计算。

## 6.6 手动 GPT 生图工作流

本项目不接入 手动图片 API，不保存 OpenAI API Key，也不产生图片 API 费用。

系统只负责生成适合复制到 ChatGPT / GPT 图片生成功能中的图片 Prompt。

Prompt 用于生成：

- 无文字主题插画；
- 低干扰背景；
- 装饰视觉元素；
- 风格统一的辅助素材；
- 指定比例和构图的背景图片。

最终信息图的核心中文文字仍由 HTML/CSS/SVG 渲染。

正确流程：

```text
DeepSeek 生成信息图 JSON
→ DeepSeek 生成图片 Prompt
→ 前端展示 Prompt
→ 用户一键复制 Prompt
→ 用户在 ChatGPT 中手动生成图片
→ 用户下载图片并上传回工作台
→ 系统绑定图片版本
→ HTML/CSS 叠加准确中文
→ Playwright 导出最终 PNG
```

前端必须同时提供：

- “复制中文 Prompt”；
- “复制英文 Prompt”；
- “标记已生成”；
- “上传 GPT 生成图片”；
- “不使用背景图，直接使用纯 CSS 模板”。

用户未上传背景图时，系统直接使用纯 CSS 信息图模板，不得阻塞整篇内容进入审核。

## 6.7 Provider 统一能力

统一处理：

- API Key；
- Base URL；
- 超时；
- 重试；
- 限流；
- 并发；
- JSON 结构验证；
- 异常转换；
- Prompt 版本；
- 输入输出日志；
- Token 使用量；
- 模型费用；
- 调用耗时；
- 问题 ID；
- 任务 ID；
- 批次 ID；
- 响应缓存；
- 降级模型；
- 数据脱敏；
- 图片 Prompt 版本；
- Prompt 复制状态；
- 用户上传图片状态；
- 上传图片与草稿版本绑定。

## 6.8 降级策略

必须支持：

1. 相同模型有限次数重试；
2. 主模型失败切换备用模型；
3. JSON 解析失败自动修复；
4. 大批次失败后拆小批次；
5. 用户不上传图片或手动生图未完成时使用纯 CSS 模板；
6. 超过次数后进入人工处理；
7. 单个回答失败不得拖垮整个问题任务；
8. 所有降级行为记录日志。

---

# 7. 前端必须调用 Design Skills

## 7.1 强制要求

在开始编写任何正式前端页面之前，必须调用当前 Codex 环境中已安装的前端设计类 Skill / Design Skill。

优先使用能够完成以下工作的技能：

- Front-end Design；
- Responsive UI Design；
- Design System；
- UI Mock；
- Visual QA；
- Browser-based UI validation。

如果环境中存在名为 `Design Skills`、`Front-end Design` 或含义相同的已安装技能，必须先调用该技能。

如果没有安装对应 Skill：

1. 先检查 Codex 的 Plugins / Skills；
2. 明确报告“当前环境未检测到可用 Design Skill”；
3. 不得假装已经调用；
4. 按下述同等设计流程执行；
5. 在最终交付中记录未使用 Skill 的原因。

## 7.2 Design Skill 必须先产出设计方案

正式写前端代码前，先输出并保存：

```text
docs/design/product-design-brief.md
docs/design/information-architecture.md
docs/design/page-inventory.md
docs/design/design-tokens.md
docs/design/component-inventory.md
docs/design/interaction-states.md
```

至少包含：

- 产品使用者；
- 核心操作路径；
- 页面信息架构；
- 页面层级；
- 主导航；
- 状态设计；
- 组件清单；
- 颜色、字号、间距、圆角和阴影；
- 表格密度；
- 表单布局；
- 空状态；
- 加载状态；
- 错误状态；
- 禁用状态；
- 危险操作；
- 响应式断点；
- 无障碍要求。

## 7.3 前端视觉方向

系统应呈现为：

> 专业、克制、清晰、可信的内容运营工作台。

不要做成：

- 普通套壳后台；
- 过度花哨的数据大屏；
- 大面积渐变和发光效果；
- 每个区域都是卡片；
- 大量无意义动画；
- 低信息密度移动端风格；
- 视觉优先于操作效率的页面。

建议：

- 桌面端优先；
- 适合 Windows 浏览器；
- 左侧主导航；
- 顶部页面标题和主要操作；
- 中间高密度任务区；
- 清晰的状态标签；
- 可折叠详情面板；
- 支持亮色和暗色；
- 统一设计 Token；
- 关键数字和错误状态高可读；
- 长任务有阶段进度；
- 关键操作二次确认。

## 7.4 前端设计流程

每个重要页面都要经过：

```text
用户任务
→ 页面草图或结构说明
→ 组件拆分
→ 状态定义
→ 正式编码
→ 浏览器打开
→ 截图检查
→ 交互测试
→ 修复
```

## 7.5 前端视觉验证

至少使用真实浏览器验证以下尺寸：

```text
1440 × 900
1280 × 720
```

需要检查：

- 页面是否溢出；
- 表格是否可读；
- 固定栏是否遮挡；
- 弹窗是否超出视口；
- 空状态是否合理；
- 错误状态是否可见；
- 深色模式是否可用；
- 长标题是否截断合理；
- 中文字体和行高是否正常；
- 信息图编辑器是否准确预览。

必须保存关键页面截图作为验收证据：

```text
artifacts/ui/dashboard.png
artifacts/ui/question-pool.png
artifacts/ui/question-detail.png
artifacts/ui/draft-review.png
artifacts/ui/publish-center.png
artifacts/ui/settings.png
```

## 7.6 前端组件要求

优先使用现有设计系统。

如果当前仓库没有成熟组件库，可选：

- React；
- TypeScript；
- Vite；
- Ant Design；
- 或其他成熟、稳定的组件库。

不要为了视觉效果引入多个冲突的 UI 库。

---

# 8. 数据模型建议

至少包含：

```text
questions
question_sources
question_scores
answers
answer_versions
answer_analysis
claims
claim_embeddings
claim_clusters
cluster_answer_links
article_drafts
article_versions
article_paragraph_sources
image_templates
image_drafts
image_versions
daily_plans
task_jobs
task_logs
publish_schedules
publish_records
system_settings
model_usage_logs
browser_sessions
audit_logs
open_source_references
prompt_templates
prompt_versions
```

要求：

1. 原始回答和 AI 生成内容分开保存；
2. 回答、文章和图片支持版本；
3. AI 调用记录模型、Token、费用和耗时；
4. 失败任务保留错误日志；
5. 不用覆盖方式删除历史版本；
6. 关键字段建立索引；
7. 使用内容哈希去重；
8. 保存段落和来源回答关系；
9. 保存 Prompt 版本；
10. 保存开源项目和许可证信息。

---

# 9. 任务状态机

建议状态：

```text
candidate
queued
fetching_question
fetching_answers
cleaning_answers
evaluating_answers
extracting_claims
generating_embeddings
clustering_claims
refining_clusters
generating_opinion_map
generating_article
reviewing_article
generating_infographic_content
generating_visual_asset
rendering_image
waiting_review
review_rejected
review_approved
scheduled
publishing
published
failed
cancelled
```

所有状态变化记录：

- 原状态；
- 新状态；
- 操作人；
- 操作时间；
- 原因；
- 任务 ID；
- 问题 ID；
- 执行 Worker。

---

# 10. 第一阶段：基础架构、工作台和最小闭环

## 10.1 第一阶段目标

第一阶段不是完成全部智能能力，而是建立不会在后续大规模返工的主架构。

第一阶段必须完成：

- 仓库分析；
- 数据库基础结构；
- 任务队列；
- Worker；
- SSE 实时进度；
- AI Provider 骨架；
- DeepSeekProvider 基础能力；
- MockProvider；
- LocalEmbeddingProvider 接口；
- ManualImageWorkflowProvider 接口预留；
- Prompt 版本管理；
- 前端 Design Skill 流程；
- 前端主框架；
- 问题池；
- 手动添加问题；
- 问题详情基础页；
- 任务中心；
- 设置页；
- 最小文章草稿流程；
- 真实构建和测试。

## 10.2 第一阶段后端

至少实现：

```text
POST /api/questions/manual
POST /api/questions/import
GET  /api/questions
GET  /api/questions/{id}
PATCH /api/questions/{id}
POST /api/questions/{id}/queue

GET  /api/tasks
GET  /api/tasks/{id}
POST /api/tasks/{id}/retry
POST /api/tasks/{id}/cancel
GET  /api/queues/status
GET  /api/queues/status/stream
GET  /api/workers

GET   /api/settings
PATCH /api/settings
POST  /api/settings/test-model
```

## 10.3 第一阶段 AI 能力

完成：

- Provider 接口；
- DeepSeek API 基础请求；
- 结构化输出；
- JSON Schema 或 Pydantic 校验；
- 超时和重试；
- MockProvider；
- 模型调用日志；
- Token 统计；
- 模型角色配置；
- API Key 安全读取；
- 至少打通一个“回答观点提取”的真实任务；
- 没有 API Key 时可用 Mock 模式完成前后端测试。

## 10.4 第一阶段前端页面

必须完成：

### 仪表盘

展示：

- 今日计划数；
- 处理中；
- 待审核；
- 待发布；
- 发布成功；
- 失败任务；
- Worker；
- 队列状态；
- 模型状态。

### 问题池

标签：

- 热门问题；
- 手动推荐；
- 今日任务；
- 已处理；
- 已忽略。

支持：

- 手动添加；
- 批量导入；
- 设置优先级；
- 加入任务；
- 忽略；
- 删除；
- 查看详情。

### 问题详情基础页

展示：

- 问题标题；
- 链接；
- 描述；
- 状态；
- 数据来源；
- 原始回答占位区域；
- 任务进度；
- 日志；
- 重试。

### 任务中心

展示：

- 任务类型；
- 所属问题；
- 当前阶段；
- 进度；
- 开始时间；
- 耗时；
- Worker；
- 重试次数；
- 错误。

### 设置页

包含：

- DeepSeek API；
- 模型角色；
- Embedding；
- 手动图片 Prompt 工作流设置；
- 每日任务数；
- 并发；
- 超时；
- 浏览器目录。

## 10.5 第一阶段最小闭环

至少打通：

```text
手动添加知乎问题
→ 保存数据库
→ 创建任务
→ Worker 执行
→ Mock 或真实 DeepSeek 完成一次结构化分析
→ 保存结果
→ SSE 更新前端进度
→ 前端查看结果
```

## 10.6 第一阶段验收

必须满足：

1. 后端可启动；
2. 前端可构建；
3. 数据库迁移可执行；
4. Redis/队列可用；
5. Worker 可执行；
6. SSE 可更新；
7. 手动问题可新增；
8. 任务状态可追踪；
9. DeepSeek 测试接口可用；
10. Mock 模式可用；
11. 页面不是静态假数据；
12. 关键页面已做浏览器截图；
13. 运行单元测试和接口测试；
14. 输出第一阶段修改文件清单；
15. 提交 Git commit。

第一阶段完成后，先停止继续开发，输出：

- 完成内容；
- 未完成内容；
- 测试结果；
- 截图位置；
- 已知问题；
- 是否达到第二阶段条件。

---

# 11. 第二阶段：知乎采集与 DeepSeek 文本智能

## 11.1 第二阶段目标

打通真正的核心内容生产流程：

```text
问题
→ 回答采集
→ 回答清洗
→ 回答筛选
→ 观点提取
→ Embedding
→ 聚类
→ 观点地图
→ 总结文章
→ 来源映射
→ 内容审核
```

## 11.2 热门问题采集

保存：

- 问题 ID；
- 标题；
- 链接；
- 描述；
- 热榜位置；
- 热度；
- 回答数；
- 关注数；
- 抓取时间；
- 来源；
- 原始数据快照。

支持：

- 接口模式；
- Playwright 页面模式；
- 失败重试；
- 字段变化告警；
- 去重；
- 热门接口失败不影响手动问题。

## 11.3 回答采集

每条回答保存：

- 回答 ID；
- 问题 ID；
- 作者；
- 作者链接；
- 回答链接；
- HTML；
- Markdown；
- 纯文本；
- 发布时间；
- 更新时间；
- 点赞；
- 评论；
- 排序；
- 图片；
- 视频；
- 公式；
- 内容哈希；
- 采集批次；
- 原始快照；
- 是否进入 AI 分析；
- 过滤原因。

支持两种模式：

### 代表性模式

优先：

- 高赞；
- 高评论；
- 新回答；
- 不同立场；
- 数据和专业回答；
- 信息密度高的回答。

### 尽可能完整模式

直到：

- 达到设置上限；
- 没有更多；
- 用户停止；
- 出现平台限制。

默认上限 100 条，可配置。

## 11.4 基础过滤

程序规则先处理：

- 过短；
- 纯表情；
- 广告；
- 删除；
- 无法解析；
- 完全重复；
- 内容哈希重复；
- 明显无关。

原始数据不能删除，只标记。

## 11.5 AI 回答质量筛选

DeepSeek Flash 批量处理。

输出：

```json
{
  "answer_id": "",
  "relevance_score": 0,
  "quality_score": 0,
  "information_density": 0,
  "include": true,
  "reason": ""
}
```

不要每条回答单独调用一次；默认 5 至 10 条为一批，批次大小可配置。

## 11.6 单条回答观点提取

输出结构：

```json
{
  "answer_id": "",
  "summary": "",
  "core_claims": [],
  "supporting_reasons": [],
  "examples": [],
  "data_or_evidence": [],
  "position": "",
  "applicable_conditions": [],
  "risks_or_limitations": [],
  "unique_insights": [],
  "possible_factual_claims": [],
  "quality_score": 0,
  "relevance_score": 0
}
```

所有观点必须保留 `answer_id`。

## 11.7 Embedding 和粗聚类

流程：

```text
core_claims 拆为观点
→ 生成向量
→ 余弦相似度
→ K-Means 或 HDBSCAN
→ 初步观点簇
```

支持：

- 向量缓存；
- 增量计算；
- 相似度阈值；
- 聚类算法配置；
- 孤立观点；
- 代表观点；
- 聚类重跑。

## 11.8 DeepSeek 聚类修正

DeepSeek Pro 负责：

- 合并相似簇；
- 拆分错误簇；
- 观点簇命名；
- 主流共识；
- 主要分歧；
- 少数派价值；
- 适用前提；
- 支持与反对关系；
- 数据冲突；
- 过时信息风险。

每个观点簇保存：

- ID；
- 名称；
- 代表总结；
- 来源回答；
- 支持数量；
- 反对理由；
- 适用前提；
- 是否主流；
- 是否少数派；
- 是否争议；
- 可信度；
- 信息增量。

## 11.9 观点地图

输出：

```json
{
  "question_summary": "",
  "one_sentence_answer": "",
  "main_dimensions": [],
  "main_consensus": [],
  "main_disagreements": [],
  "minority_but_valuable_views": [],
  "common_misunderstandings": [],
  "applicable_conditions": [],
  "risks": [],
  "practical_suggestions": [],
  "source_answer_ids": []
}
```

前端支持：

- 删除观点；
- 合并；
- 拆分；
- 修改名称；
- 调整顺序；
- 强制写入；
- 禁止写入；
- 查看来源回答；
- 局部重新分析。

## 11.10 总结文章

默认结构：

```text
一句话结论

一、这个问题下，大多数回答的共识是什么

二、大家真正存在分歧的地方是什么

三、为什么看起来相互矛盾

四、哪些观点最值得参考

五、哪些前提容易被忽略

六、综合这些回答，我的总结与建议

AI 辅助整理说明
```

要求：

- 直接回答；
- 不堆砌空泛背景；
- 不按答主 A、B、C 逐条复述；
- 不复制独特句式；
- 不捏造数据；
- 不虚构亲身经历；
- 区分经历和普遍结论；
- 明确共识和分歧；
- 写清适用条件；
- 默认 1200 至 2500 字；
- 字数可配置；
- 使用实际采集数量，不夸大“看了几百条”。

## 11.11 段落来源映射

文章输出需要同时返回：

```json
{
  "paragraph_id": "p001",
  "content": "",
  "cluster_ids": [],
  "source_answer_ids": []
}
```

前端点击段落时显示来源回答。

## 11.12 独立质量审核

生成和审核分开调用。

检查：

- 是否覆盖共识；
- 是否覆盖分歧；
- 是否遗漏重要观点；
- 是否过度依赖单一回答；
- 是否出现近似复制；
- 是否存在无来源观点；
- 是否将经历写成事实；
- 是否有矛盾数据；
- 是否有医疗、法律、金融风险；
- 是否模板化；
- 是否重复总结；
- 是否存在绝对表达。

## 11.13 第二阶段前端

完善：

### 问题详情

三栏：

- 左：原始回答；
- 中：观点地图；
- 右：任务、模型、Token、日志。

### 草稿审核

三栏：

- 左：文章编辑器；
- 中：信息图文案、图片 Prompt 和上传背景图区域；
- 右：来源和质量检查。

图片区域必须支持：

- 生成图片 Prompt；
- 查看 Prompt；
- 一键复制中文 Prompt；
- 一键复制英文 Prompt；
- 上传手动生成图片；
- 删除或替换图片；
- 切换纯 CSS 模式；
- 查看 Prompt 和上传图片历史版本。

支持：

- Markdown；
- 富文本；
- 段落重写；
- 选中文字重写；
- 版本；
- 撤销；
- 来源查看；
- 重新生成；
- 审核通过；
- 退回分析。

## 11.14 第二阶段验收

至少测试一个真实知乎问题：

1. 获取问题信息；
2. 获取至少 20 条有效回答；
3. 清洗和去重；
4. 回答质量筛选；
5. 观点提取；
6. Embedding；
7. 观点聚类；
8. 前端显示共识和分歧；
9. 生成文章；
10. 段落来源可追溯；
11. 质量审核完成；
12. 模型调用和费用有记录；
13. 失败任务可以重试；
14. 浏览器页面截图；
15. 前后端测试通过；
16. 提交 Git commit。

第二阶段结束后先停止，输出：

- 真实测试问题；
- 采集回答数；
- 有效回答数；
- 观点簇数；
- 文章字数；
- Token 和费用；
- 失败和重试；
- 截图位置；
- 已知限制；
- 是否达到第三阶段条件。

---

# 12. 第三阶段：图片 Prompt 工作流、信息图、发布中心和完整运营能力

## 12.1 第三阶段目标

完成：

```text
观点地图
→ 信息图文案
→ 图片 Prompt
→ 用户复制到 GPT 手动生图
→ 用户上传背景图
→ HTML/CSS 信息图
→ PNG
→ 人工审核
→ 排期
→ 辅助发布
→ 发布记录
```

## 12.2 信息图内容 JSON

DeepSeek Flash 输出：

```json
{
  "title": "",
  "one_line_conclusion": "",
  "consensus": [
    {
      "title": "",
      "description": ""
    }
  ],
  "disagreements": [],
  "conditions": [],
  "suggestions": [],
  "visual_keywords": [],
  "source_cluster_ids": []
}
```

需要做长度限制，防止文字溢出。

## 12.3 图片 Prompt 与人工生图能力

实现 `ManualImageWorkflowProvider` 和前端“图片 Prompt 工作区”。

本项目不接入 手动图片 API，不要求 OpenAI API Key，不自动调用 GPT 图片模型。

系统负责：

- 根据问题标题、观点地图和模板生成图片 Prompt；
- 根据用户选择的视觉风格调整 Prompt；
- 输出中文 Prompt；
- 输出可选英文 Prompt；
- 支持一键复制；
- 保存 Prompt 历史版本；
- 显示建议尺寸和画面比例；
- 显示负面约束；
- 显示“不要在图片内生成中文文字”等硬性要求；
- 接收用户手动上传的 GPT 生成图片；
- 保存原图；
- 生成缩略图；
- 将上传图片绑定到草稿和图片版本；
- 支持替换、删除和重新上传；
- 支持完全跳过背景图。

推荐 Prompt 结构：

```text
主题
使用场景
画面主体
构图
视觉风格
色彩
背景复杂度
预留文字区域
尺寸与比例
禁止出现的元素
不得生成中文文字
```

前端操作流程：

```text
生成图片 Prompt
→ 预览 Prompt
→ 一键复制
→ 用户前往 ChatGPT 手动生图
→ 用户下载图片
→ 回到工作台上传
→ 预览裁切
→ 保存为背景图版本
```

未上传图片时，使用纯 CSS 背景完成最终信息图。

## 12.4 信息图模板

至少实现：

### 模板 1：知识总结卡

适合一般问题。

### 模板 2：观点对比表

适合 A/B、支持/反对、是否值得。

预留：

- 决策树；
- 时间线。

默认尺寸：

```text
1080 × 1440
1242 × 1660
```

## 12.5 图片编辑器

前端支持：

- 修改标题；
- 修改一句话结论；
- 修改观点；
- 拖拽排序；
- 删除观点；
- 字体大小；
- 模板切换；
- 背景切换；
- 品牌名；
- 页脚；
- 重新渲染；
- 重新生成 Prompt；
- 复制中文 Prompt；
- 复制英文 Prompt；
- 上传手动生成图片；
- 替换上传图片；
- 删除背景图；
- 纯 CSS 模式；
- 下载 PNG；
- 历史版本；
- 文字溢出提示。

## 12.6 Playwright 渲染

必须：

- 固定视口；
- 等待字体加载；
- 等待图片加载；
- 检查文字溢出；
- 截图失败重试；
- 保存 HTML 快照；
- 记录渲染日志；
- 支持批量；
- 支持 Windows；
- 不依赖用户正在浏览的页面。

## 12.7 发布中心

分为：

### 内容准备

- 已审核；
- 未排期；
- 文章版本；
- 图片版本；
- 风险状态。

### 排期计划

- 日期；
- 时间；
- 发布顺序；
- 间隔；
- 手动或辅助发布；
- 日历；
- 拖拽；
- 每日数量；
- 冲突提醒。

### 执行记录

- 时间；
- 问题；
- 方式；
- 状态；
- 最终链接；
- 失败原因；
- 截图；
- 重试；
- 最终文章版本；
- 最终图片版本。

## 12.8 浏览器发布适配器

统一封装：

```text
ZhihuBrowserClient
BrowserSessionManager
DraftPublisher
```

发布遇到以下情况立即停止：

- 未登录；
- 验证码；
- 页面无法识别；
- 图片上传失败；
- 正文不完整；
- 发布按钮不可用；
- 用户要求强制确认。

默认只实现人工审核后的辅助发布。

不得绕过平台限制。

## 12.9 每日计划

默认每天 10 个问题，可配置：

- 热门配额；
- 手动推荐配额；
- 执行时间；
- 最大并发；
- 最大回答数；
- 每日发布上限；
- 发布时间间隔；
- 自动生产；
- 自动发布开关默认关闭。

立即执行和定时执行必须共用同一个调度器和任务流程。

## 12.10 成本控制

设置页展示：

- 今日调用数；
- 今日输入 Token；
- 今日输出 Token；
- DeepSeek 费用；
- 手动图片生成次数记录；
- 每个问题成本；
- 每个阶段成本；
- 每日预算；
- 超预算暂停；
- 模型切换；
- 缓存命中；
- 降级次数。

## 12.11 Prompt 管理

支持：

- Prompt 列表；
- 版本；
- 启用版本；
- 测试输入；
- 测试输出；
- 模型；
- 参数；
- 回滚；
- 变更记录。

不要允许普通页面无意中覆盖生产 Prompt。

## 12.12 第三阶段验收

至少满足：

1. 信息图 JSON 生成；
2. 图片 Prompt 生成；
3. 中文和英文 Prompt 可复制；
4. 用户可上传手动生成图片；
5. 未上传图片时纯 CSS 降级；
6. 两种模板；
7. 中文无明显错误；
8. 无明显文字溢出；
9. 导出 1080×1440 PNG；
10. 图片版本可查看；
11. 草稿可审核；
12. 加入发布队列；
13. 日历可排期；
14. 发布前强制确认；
15. 登录失效暂停；
16. 验证码暂停；
17. 执行记录保存；
18. 文本模型成本展示；
19. 浏览器真实截图；
20. 前后端测试通过；
21. README 完整；
22. 提交 Git commit。

---

# 13. 前端页面总清单

最终至少包含：

```text
/dashboard
/questions
/questions/:id
/tasks
/drafts
/drafts/:id/review
/publish
/prompts
/settings
/settings/ai
/settings/browser
/settings/open-source
```

---

# 14. 推荐后端接口

## 问题

```text
GET    /api/questions
POST   /api/questions/manual
POST   /api/questions/import
GET    /api/questions/{id}
PATCH  /api/questions/{id}
DELETE /api/questions/{id}
POST   /api/questions/{id}/queue
POST   /api/questions/{id}/retry
POST   /api/questions/{id}/ignore
```

## 回答

```text
GET    /api/questions/{id}/answers
POST   /api/questions/{id}/fetch-answers
GET    /api/answers/{id}
POST   /api/answers/{id}/include
POST   /api/answers/{id}/exclude
```

## 分析

```text
POST   /api/questions/{id}/evaluate
POST   /api/questions/{id}/extract-claims
POST   /api/questions/{id}/generate-embeddings
POST   /api/questions/{id}/cluster
POST   /api/questions/{id}/generate-opinion-map
GET    /api/questions/{id}/clusters
PATCH  /api/clusters/{id}
POST   /api/clusters/merge
POST   /api/clusters/{id}/split
DELETE /api/clusters/{id}
```

## 草稿

```text
POST   /api/questions/{id}/generate-draft
GET    /api/drafts/{id}
PATCH  /api/drafts/{id}
POST   /api/drafts/{id}/regenerate
POST   /api/drafts/{id}/review
POST   /api/drafts/{id}/approve
POST   /api/drafts/{id}/reject
GET    /api/drafts/{id}/versions
```

## 图片

```text
POST   /api/drafts/{id}/generate-infographic-content
POST   /api/drafts/{id}/generate-image-prompt
POST   /api/drafts/{id}/upload-visual-asset
POST   /api/drafts/{id}/generate-image
GET    /api/images/{id}
PATCH  /api/images/{id}
POST   /api/images/{id}/render
POST   /api/images/{id}/regenerate-prompt
POST   /api/images/{id}/upload-background
DELETE /api/images/{id}/background
GET    /api/images/{id}/download
GET    /api/images/{id}/versions
```

## 任务

```text
GET    /api/tasks
GET    /api/tasks/{id}
POST   /api/tasks/{id}/pause
POST   /api/tasks/{id}/resume
POST   /api/tasks/{id}/cancel
POST   /api/tasks/{id}/retry
GET    /api/queues/status
GET    /api/queues/status/stream
GET    /api/workers
```

## 发布

```text
POST   /api/publish/schedules
GET    /api/publish/schedules
PATCH  /api/publish/schedules/{id}
DELETE /api/publish/schedules/{id}
POST   /api/publish/{id}/execute
GET    /api/publish/records
```

## 设置和 Prompt

```text
GET    /api/settings
PATCH  /api/settings
POST   /api/settings/test-model
POST   /api/settings/test-browser
GET    /api/prompts
POST   /api/prompts
PATCH  /api/prompts/{id}
POST   /api/prompts/{id}/activate
GET    /api/model-usage
GET    /api/open-source-references
```

---

# 15. 日志和错误处理

所有长任务记录：

- 任务 ID；
- 问题 ID；
- 阶段；
- 开始和结束；
- 耗时；
- 输入数量；
- 输出数量；
- 模型；
- Token；
- 费用；
- Worker；
- 队列；
- 错误；
- 重试；
- 截图。

单独处理：

- 页面加载失败；
- 登录失效；
- 验证码；
- 回答无法获取；
- 页面结构变化；
- 热榜接口变化；
- AI 超时；
- AI JSON 错误；
- Embedding 失败；
- 聚类为空；
- 文章失败；
- 图片失败；
- 文字溢出；
- Redis 失败；
- 数据库失败；
- Worker 掉线；
- 发布失败。

---

# 16. 测试要求

至少包含：

## 后端

- 单元测试；
- 接口测试；
- 数据库迁移测试；
- 任务重试测试；
- JSON 校验测试；
- Provider Mock 测试；
- 来源映射测试；
- 状态机测试。

## 前端

- 构建；
- TypeScript；
- 关键组件测试；
- 页面路由；
- 空状态；
- 错误状态；
- 深色模式；
- 表单校验。

## 端到端

- 手动添加问题；
- 创建任务；
- 回答采集；
- 文章生成；
- 图片 Prompt 生成；
- 手动上传背景图；
- 信息图；
- 审核；
- 排期；
- 失败重试。

---

# 17. 环境变量示例

提供 `.env.example`，至少包含：

```env
APP_ENV=development
DATABASE_URL=
REDIS_URL=

DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_FAST_MODEL=deepseek-v4-flash
DEEPSEEK_REASONING_MODEL=deepseek-v4-flash

IMAGE_GENERATION_MODE=manual
IMAGE_PROMPT_MODEL_ROLE=fast_text_model
ALLOW_MANUAL_IMAGE_UPLOAD=true

EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=

ZHIHU_BROWSER_USER_DATA_DIR=
PLAYWRIGHT_HEADLESS=false

DAILY_QUESTION_LIMIT=10
HOT_QUESTION_QUOTA=6
MANUAL_QUESTION_QUOTA=4
MAX_ANSWERS_PER_QUESTION=100
MAX_AI_CONCURRENCY=3
```

不要提交真实密钥。

---

# 18. Windows 11 运行要求

用户主要使用 Windows 11。

必须提供：

- 原生 Windows 启动方案；
- PowerShell 命令；
- 可选 Docker Compose；
- Playwright 浏览器安装命令；
- Redis 和数据库启动说明；
- 前后端一键启动脚本；
- Worker 启动脚本；
- 日志目录；
- 常见错误排查。

建议提供：

```text
scripts/start-dev.ps1
scripts/start-backend.ps1
scripts/start-frontend.ps1
scripts/start-worker.ps1
scripts/run-tests.ps1
```

---

# 19. 最终交付格式

每个阶段结束必须输出：

1. 本阶段实现摘要；
2. 修改文件清单；
3. 数据库迁移；
4. 新增接口；
5. 新增页面；
6. 新增任务；
7. 使用的 Design Skill；
8. UI 截图；
9. 测试命令；
10. 测试结果；
11. 模型调用测试；
12. 已知限制；
13. 下一阶段是否可以开始；
14. Git commit SHA。

第三阶段完成后额外输出：

- 完整启动方式；
- README；
- `.env.example`；
- 开源参考和许可证；
- 实际测试问题；
- 实际采集回答数；
- 文章字数；
- 信息图文件；
- 总文本模型成本；
- 发布流程验证；
- 尚未完成事项。

---

# 20. Codex 在目标模式下的行为要求

将本文件作为长期目标规格。

执行规则：

1. 先读取本文件和仓库；
2. 创建实施计划；
3. 先完成第一阶段；
4. 第一阶段验收不通过不得进入第二阶段；
5. 第二阶段验收不通过不得进入第三阶段；
6. 遇到小型歧义采用合理默认值并记录；
7. 不要频繁要求用户确认非关键细节；
8. 遇到平台登录、验证码、API Key 和不可逆操作时必须暂停；
9. 需要用户提供密钥时，先完成 Mock 和结构开发；
10. 不得在没有实际测试的情况下标记完成；
11. 长任务应持续更新进度文件；
12. 每完成一个阶段提交 Git；
13. 不在主分支直接进行大规模开发；
14. 发现现有项目架构冲突时优先适配，不擅自推翻；
15. 如果工作量超过单次执行能力，保持当前分支和进度文件完整，并从最近验收点继续。

建议维护：

```text
docs/progress/phase-1.md
docs/progress/phase-2.md
docs/progress/phase-3.md
```

---

# 21. 立即开始执行

现在开始：

1. 读取仓库；
2. 检查 Git 状态；
3. 创建开发分支；
4. 识别现有技术栈；
5. 检查已安装的 Plugins / Skills；
6. 调用可用的前端 Design Skill；
7. 输出仓库分析；
8. 输出设计文档；
9. 输出第一阶段文件修改计划；
10. 只开始第一阶段开发；
11. 完成第一阶段后执行测试、截图和验收；
12. 在进入第二阶段前明确报告第一阶段结果。

不要只回复方案，请实际修改代码、运行项目和测试。
