# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

2026-09-07 UI redesign decision supersedes the old dense dashboard and three-column layout: use a clean, light personal creation tool with the main navigation 今天 / 选题 / 作品 and settings at the bottom. Today prioritizes the manual daily plan and actionable work; logs and infrastructure details stay secondary. Question details use 概览 / 回答 / 观点地图 tabs and a task-details drawer. Draft review uses same-page 文章 / 配图 / 审核与导出 steps, with readable article preview first and sources on demand. Keep image Prompt, upload history, manual replacement, and the full infographic editor inside the work, with the full editor opening in a drawer. Preserve dark mode, old URLs, explicit saving, unsaved-edit guards, and backend review/export readiness checks. Desktop and narrow windows are the primary targets. Publishing retains content readiness / calendar / records, typed confirmation for schedule execution, and manual publishing packages by default; browser-assisted flows must pause at login or captcha requirements. No cloud deployment for this redesign.

2026-09-07 user decision supersedes the manual-only image and scheduled-production assumptions: RunDock owns the two local services, the user manually starts them, then manually executes or resumes a daily plan. Startup must not collect or call models. The daily pipeline uses Codex CLI native image generation plus HTML/CSS PNG rendering; keep manual image replacement inside the work’s image step. Final Zhihu publication is manual. Keep daily counts and partial-collection coverage visible.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.
