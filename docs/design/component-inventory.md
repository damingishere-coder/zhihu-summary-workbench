# 组件清单

## 应用框架

| 组件 | 责任 |
| --- | --- |
| `AppShell` | 侧边栏、顶栏、主内容和响应式布局 |
| `SidebarNavigation` | 品牌、路由、选中态、折叠和主题切换 |
| `PageHeader` | 标题、说明、面包屑和主操作 |
| `ThemeProvider` | 亮暗主题和 Ant Design Token |

## 数据展示

| 组件 | 责任 |
| --- | --- |
| `MetricStrip` | 紧凑展示今日计划、处理中、待审核和失败 |
| `InfrastructureHealth` | Redis、Worker、模型和存储状态 |
| `QuestionTable` | 问题高密度列表、筛选和行操作 |
| `TaskTable` | 任务阶段、进度、耗时、Worker、重试和错误 |
| `StatusTag` | 统一映射状态文字、颜色和图标 |
| `PriorityTag` | 高、中、低优先级 |
| `ProgressCell` | 百分比、进度条和阶段文字 |
| `ActivityTimeline` | 最近操作和任务日志 |
| `StructuredResult` | 结构化观点、摘要、风险和来源 |
| `AnswerExplorer` | 回答列表、质量分、纳入状态、展开正文和来源链接 |
| `OpinionMapPanel` | 共识、分歧、少数派、条件、风险、建议和来源抽屉 |
| `ImagePromptWorkspace` | 信息图文案、中文/英文 Prompt、复制、上传、纯 CSS 和历史版本 |
| `InfographicEditor` | 模板、画布、文案、排序、字体、品牌、页脚、背景裁切和版本保存 |
| `InfographicPreview` | 按最终比例预览知识总结卡和观点对比表 |
| `OverflowInspector` | 字段长度、DOM 溢出、渲染日志和定位提示 |
| `PublishReadinessTable` | 固定文章/图片版本、审核和风险状态 |
| `PublishCalendar` | 月历排期、拖拽改期、顺序和冲突 |
| `PublishRecordTable` | 执行状态、最终链接、失败原因、截图和重试 |
| `PromptWorkbench` | Prompt 版本、测试、启用、回滚和审计 |
| `CostOverview` | 今日、问题、阶段、预算、缓存和降级 |

## 输入与操作

| 组件 | 责任 |
| --- | --- |
| `AddQuestionModal` | 链接、标题、描述、示例回答、优先级校验 |
| `ImportQuestionsModal` | 一行一个链接的批量导入与结果汇总 |
| `QuestionFilters` | 标签、状态、来源、优先级和搜索 |
| `DangerConfirm` | 删除、取消等危险操作二次确认 |
| `RetryButton` | 只在可重试状态可用并解释禁用原因 |
| `SettingsForm` | 非敏感配置编辑 |
| `ModelTestPanel` | Provider 测试输入和结构化结果 |
| `ScheduleModal` | 日期、时间、顺序、间隔、方式和版本确认 |
| `PublishConfirmation` | 强制确认文本、发布范围和安全检查 |
| `BrowserSessionCheck` | 浏览器目录、登录、验证码和页面识别状态 |

## 状态反馈

| 组件 | 责任 |
| --- | --- |
| `LoadingBlock` | 首屏和局部加载骨架 |
| `EmptyState` | 说明为什么为空并提供唯一下一步 |
| `ErrorState` | 显示可理解错误、影响和重试 |
| `ConnectionBadge` | SSE 在线、重连、离线 |
| `SaveStatus` | 未保存、保存中、已保存、失败 |

## 图标策略

- 使用 `@ant-design/icons`，与 Ant Design 控件一致。
- 标准状态图标来自同一图标库。
- 不用 Emoji、文本符号、CSS 绘图或手写 SVG 代替图标。
- 第一阶段视觉稿没有需要生成的图片、插画或照片，因此不新增位图资产。
