# Chrome DOM 优先采集与真实验收执行任务

## 背景

当前 Chrome 扩展仍以知乎同源 API 为主，真实验收中会被安全验证阻断；人工 `ImportBundleV1` 可以恢复任务并完成后续分析。系统推进路线要求先完成第 1 里程碑，达到真实采集门槛后才能进入质量评测和日计划后续阶段。

## 目标

在用户正常登录、可见的知乎问题标签页中优先采集已经渲染的回答，自动展开、滚动、去重并回传可解释的采集诊断。保留 API 显式增强和 `ImportBundleV1` 人工兜底；登录、验证码和风控必须安全暂停。

## 允许修改范围

- `frontend/extension/`：DOM 采集、标签页任务执行、桥接消息和测试。
- `backend/app/`、`backend/alembic/`、`backend/tests/`：采集包兼容、持久化诊断、任务输出、迁移和测试。
- `frontend/src/`：现有浏览器设置和问题详情中的采集来源、数量、诊断和恢复提示。
- `docs/`、`README.md`：当前状态、验收说明和操作边界。

## 禁止修改范围

- 不读取、导出、记录或提交 Cookie、密码、Token、`.env`、Codex 登录文件或浏览器资料。
- 不实现验证码破解、指纹伪造、代理池、隐身浏览器、请求签名逆向或后台隐藏采集。
- 不执行真实知乎发布、生产部署、数据库删除、Git 历史重写或强制推送。
- 在真实 5 题门槛通过前，不进入草稿质量评测、日计划语义重写和生产文件大拆分。

## 已确定实现要求

1. WebSocket 外层 `protocol_version` 保持 1，避免旧扩展在 hello 阶段失效。
2. 新增 `CollectionBundleV2`；后端同时接受 V1/V2，人工导入接口继续只接收 `ImportBundleV1`。
3. V2 记录 `capture_method`、页面 URL、可见/已采集回答数量和结构化诊断；问题和回答字段继续使用现有白名单模型。
4. `CollectionJob` 使用可空字段持久化采集版本、方式、页面、统计和诊断；旧数据不猜测可见数量。
5. 默认代表性模式采用 DOM 优先，最大 20 条；完整/API 模式只能显式触发。出现登录或验证状态后不得继续 API 请求。
6. DOM 采集复用当前可见问题页，自动展开回答并有限滚动；按回答 ID、URL和规范化内容去重。少于目标数量时返回实际数量和警告，不补假数据。
7. 页面结构不满足最低条件时返回 `page_changed` 诊断；登录和验证继续使用现有等待状态，重试次数不增加。
8. 任务结果和现有前端页面显示采集方式、页面、回答数量、警告及推荐恢复动作，不新增独立页面。

## 验收标准

- V1 人工导入、旧桥接消息和现有 REST/SSE 行为保持兼容。
- DOM fixture 覆盖正常、展开、滚动、匿名/删除、重复、少于上限、登录、验证和页面变化。
- 后端覆盖 V2 校验、持久化、重复完成、错误 nonce/client、断线后幂等恢复和历史迁移。
- 前端/扩展类型检查、测试、构建、后端测试、迁移和 Sites 测试全部通过；工作区无范围外产物。
- 真实门槛：5 个当前账号可正常浏览的问题中至少 4 个无需 JSON 导入进入 `waiting_review`；可见回答不少于 10 条时至少采集 10 条，否则准确报告实际数量。

## 测试命令

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_browser_bridge.py backend/tests/test_migration.py backend/tests/test_task_flow.py
Set-Location frontend
npm.cmd run typecheck
npm.cmd run typecheck:extension
npm.cmd run test:extension
npm.cmd run build:extension
npm.cmd run test:run
npm.cmd run build
npm.cmd run test:sites
Set-Location ..
powershell -ExecutionPolicy Bypass -File .\scripts\run-tests.ps1
git diff --check
git status --short
```

## 返回格式

最终报告必须区分自动化验证、扩展本地构建、真实知乎采集、后续流水线、真实发布；列出迁移版本、测试结果、未完成门槛、提交哈希、分支、远端和推送结果。
