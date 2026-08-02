# 仓库分析

## 检查时间与结论

- 检查日期：2026-07-23。
- 远程仓库：`damingishere-coder/zhihu-summary-workbench`。
- 基线分支：`origin/main`，基线提交 `6ed2423c734246b05b1d084b7f7aca2fa2840f4a`。
- 当前开发分支：`feature/zhihu-summary-workbench`。
- 根目录没有额外 `AGENTS.md`，本项目遵循会话中提供的开发规范。
- 初始仓库只有 `README.md` 和完整规格文档，没有现成应用代码、数据库、测试或构建配置。
- 规格文档已按正文推荐名称改为根目录 `CODEX_IMPLEMENTATION_SPEC.md`，并作为长期目标规格。

## 现有技术栈

初始仓库不存在可识别的前端、后端、数据库、队列、浏览器自动化或 AI 调用技术栈。

本机运行条件：

| 能力 | 检查结果 | 第一阶段处理 |
| --- | --- | --- |
| Node.js | v24.15.0 | 用于 React/Vite 前端 |
| npm | v11.12.1 | 管理前端依赖 |
| Python | 3.12.10 | 用于 FastAPI 后端和 Worker |
| Docker | 28.0.4 | 用于 Redis，可选 PostgreSQL |
| Docker Compose | v2.34.0-desktop.1 | 统一启动基础服务 |
| 本机 Redis | 未安装 | 使用 Docker Compose 中的 Redis |
| uv | 未安装 | Windows 原生方案改用 `python -m venv` 和 pip |

## 可复用模块

仓库中没有应用模块可复用。可以复用的只有：

1. 完整目标规格及其中的阶段边界；
2. 远程仓库和 Git 历史；
3. 当前环境中的 Product Design、Image Gen、Browser 等技能；
4. 本机 Node.js、Python 和 Docker 运行时。

## 重复或冲突模块

- 没有重复实现或架构冲突。
- 唯一命名偏差是规格文件原名过长，与用户指定的 `CODEX_IMPLEMENTATION_SPEC.md` 不一致；已通过 Git 重命名修正，不改正文。
- Product Design 原型模板只用于建立前端基础，不替代本项目的 FastAPI、Redis、数据库和 Worker 架构。

## 第一阶段技术选型

| 层级 | 选型 | 原因 |
| --- | --- | --- |
| 前端 | React、TypeScript、Vite | 与规格建议一致，Windows 开发体验稳定 |
| 组件 | Ant Design、Ant Design Icons | 单一成熟组件库，适合高密度中文运营后台 |
| 数据请求 | TanStack Query | 统一加载、错误、缓存和轮询状态 |
| 后端 | FastAPI、Pydantic v2 | 明确的接口契约和结构化输出校验 |
| ORM/迁移 | SQLAlchemy 2、Alembic | 支持 SQLite 和 PostgreSQL，迁移可审计 |
| 开发数据库 | SQLite | 零配置启动；长期数据仍由关系型数据库保存 |
| 队列 | Redis List + Pub/Sub | 第一阶段实现真实独立 Worker、重试和 SSE |
| AI Provider | 自研接口层 + httpx | 第三方模型调用集中在 Provider 层 |
| 测试 | pytest、Vitest、Testing Library | 覆盖接口、状态机、Provider、组件和表单 |
| 浏览器验收 | Codex 内置 Browser | 使用真实浏览器完成交互与截图 |

## 边界与风险

- 第一阶段不采集真实知乎回答；问题详情中的“原始回答”区域按规格仅展示阶段说明。
- 第一阶段会用用户输入的“示例回答”打通观点提取闭环。没有 DeepSeek 密钥时使用确定性的 Mock Provider；有密钥时可以通过同一接口测试真实调用。
- Redis 是队列、进度和实时事件的真实基础设施，不承担长期业务数据。
- SQLite 作为默认开发数据库；`DATABASE_URL` 可切换 PostgreSQL。
- 不保存知乎密码、Cookie、DeepSeek 密钥或浏览器缓存；设置接口只返回密钥是否已配置。
- 不复制规格中参考仓库的代码。任何后续代码借鉴必须先记录版本和许可证。

## 三阶段实施顺序

1. 第一阶段：基础架构、Provider 骨架、队列/Worker/SSE、工作台和最小闭环。
2. 第一阶段通过构建、测试、浏览器截图和验收后停止。
3. 第二阶段：知乎采集、清洗、DeepSeek 文本分析、Embedding、聚类和文章生成。
4. 第二阶段通过独立验收后停止。
5. 第三阶段：图片 Prompt、手动上传背景、信息图、发布中心和成本控制。

本分支当前只实现第一阶段，不提前实现第二、三阶段业务。
