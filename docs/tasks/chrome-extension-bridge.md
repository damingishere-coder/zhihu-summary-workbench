# Chrome 扩展采集桥接执行任务

## 背景

当前正式数据库只有一个停在 `waiting_verification`、进度 10% 的知乎任务，且没有回答、草稿或真实模型调用记录。现有 Playwright 扫码方案同时存在浏览器组件版本漂移、缓存登录标记误报和知乎安全验证阻断，不能作为可靠的正式入口。

## 目标

用用户正常登录的 Chrome 扩展完成知乎问题和回答采集，通过本机安全桥接把结构化结果交给后端，恢复现有任务并让正式流水线继续到草稿审核。保留 JSON 导入兜底，不绕过知乎登录、验证码或风控。

## 允许修改范围

- `backend/`：桥接模型、迁移、协议、路由、任务状态机、导入与测试。
- `frontend/`：桥接设置页、任务恢复与导入交互、扩展源码/构建脚本及测试。
- `scripts/`、`requirements*.txt`、`docker-compose.yml`：启动预检、确定性浏览器依赖和扩展构建。
- `README.md`、`docs/`：安装、运行、真实验收、开源参考和限制说明。

## 禁止修改范围

- 不删除或重置现有 `data/`、任务日志、浏览器资料或用户数据库。
- 不读取、记录或提交 `.env`、Cookie、Token、密码、Codex 登录文件或浏览器数据。
- 不实现验证码破解、指纹伪造、代理池、请求签名逆向或其他风控绕过。
- 普通自动化测试不得访问知乎、Codex、DeepSeek 或其他真实外部服务。
- 不执行真实发布、生产部署、强制推送或历史重写。

## 已确定实现要求

1. Manifest V3 扩展只申请知乎、本机桥接和必要存储权限；同源请求使用当前 Chrome 登录态，但不导出 Cookie。
2. 使用一次性配对码和令牌哈希；WebSocket 协议版本化，并校验 job id、nonce、来源、大小和状态转换。
3. 新增持久化桥接客户端与采集任务，支持 `waiting_browser`、`waiting_login`、`waiting_verification`、成功回传和断线恢复。
4. 后端重新校验并清洗扩展数据；支持 `ImportBundleV1` JSON 导入。
5. 旧扫码操作接口返回 `410 Gone`，旧浏览器资料保留但不再证明登录有效。
6. Playwright 仅用于信息图渲染：本机优先系统 Chrome，Docker 使用匹配 Chromium，并提供启动预检。
7. 健康状态区分“已配置”和“最近真实验证”，并返回稳定的工作台 `app_id`。
8. 保留并恢复现有等待验证任务，不增加失败重试次数。

## 验收标准

- 后端、前端、扩展、Sites、Docker 配置和迁移测试全部通过，工作树无范围外产物。
- 模拟扩展集成测试能把任务从浏览器等待推进到 `waiting_review`。
- 真实验收仅在扩展在线、知乎实时登录成功后执行；使用当前 Codex，正式库出现真实回答、观点、观点簇、观点地图、草稿和真实 provider usage。
- 若知乎仍阻断，任务必须停在相应等待状态；导入兜底结果单独标记，不冒充实时采集。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=backend.app --cov-report=term-missing
Set-Location frontend
npm.cmd run typecheck
npm.cmd run test:run
npm.cmd run build:extension
npm.cmd run build
npm.cmd run test:sites
Set-Location ..
docker compose config --quiet
git status --short
git diff --check
```

## 返回格式

最终报告必须区分：自动化验证、扩展本地联通、真实知乎采集、真实 Codex 调用和真实发布；列出数据库备份路径、迁移版本、测试结果、提交哈希、分支、远端地址和推送结果。

## 2026-08-23 真实验收记录

- Chrome 扩展 `0.1.0` 已完成一次性配对；健康页确认扩展在线、知乎实时认证为 `authenticated`。
- 对问题 `58173613` 的同源 API 自动采集被知乎安全验证阻断，任务诚实进入 `waiting_verification`，未增加重试次数。
- 从用户当前正常可见的问题页提取 5 条回答并按 `ImportBundleV1` 人工兜底导入；该采集任务记录为 `source=import`，不计作自动采集成功。
- 修复 Codex 严格结构化输出 schema 和旧数据库 60 秒超时后，任务 `991b6bcd-2c1c-46ca-ba79-428b1d6f0f32` 到达 `waiting_review`、进度 100%、重试 0。
- 活动库形成 5 条回答分析、16 条观点、6 个观点簇、1 份观点地图、1 篇待审草稿和 7 条 `codex / gpt-5.6-sol` 成功 usage；未执行知乎发布。
