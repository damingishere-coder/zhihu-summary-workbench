# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

The durable visual decision for this project is Product Design ideation option 1, saved at `../docs/design/reference-dashboard.png`: a restrained light operations workbench with a compact left navigation, dense central task table, a narrow activity rail, quiet blue primary actions, and semantic status colors. Preserve this direction unless the user explicitly changes it.

The durable phase-two workflow decision is that the manual image Prompt workflow belongs inside the middle column of draft review, next to infographic copy and upload history. Do not move it into a detached image page or settings-only flow. The question detail page uses answers / opinion map / task-and-cost columns, while draft review uses article / image Prompt-and-upload / sources-and-quality columns.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.
