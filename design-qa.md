# 第三阶段 Design QA

## 对比目标

- source visual truth：`artifacts/ui/draft-review.png`
- implementation screenshot：`artifacts/ui/phase3-draft-review-match.png`
- 同屏全景证据：`artifacts/ui/phase3-design-qa-comparison.png`
- 草稿审核中栏聚焦证据：`artifacts/ui/phase3-design-qa-focus.png`
- 信息图编辑器证据：`artifacts/ui/phase3-infographic-editor-fixed-1440.png`
- Prompt 管理证据：`artifacts/ui/phase3-prompts-1440.png`
- 发布中心证据：`artifacts/ui/phase3-publish-1440.png`、`artifacts/ui/phase3-publish-900.png`
- 主要路由：`/drafts/:id/review`、`/publish`、`/prompts`
- source pixels：1472 × 1047
- implementation pixels：1457 × 1037
- device density normalization：浏览器截图均为 DPR 1。仅在全景对比图中把实现截图按横向 `1.0103`、纵向 `1.0096` 等比例接近到 1472 × 1047，目的是抵消滚动条占位造成的截图边界差异；界面本身没有缩放或加设备外框。
- state：桌面端亮色主题；草稿审核已生成信息图内容和 Prompt，编辑抽屉可打开；发布中心使用真实本地数据与真实禁用态。

## Findings

- 最终没有遗留可执行的 P0、P1 或 P2 视觉问题。
- [P3] 信息图预览在窄屏下保持固定卡片比例，因此编辑器需要纵向滚动；这是为了让导出比例与实际 1080 × 1440 PNG 一致，不影响关键操作。
- [P3] 发布中心的内容准备表在 900 px 视口下采用可滚动表格，页面本身没有横向溢出；这是高密度运营表格的预期行为。

## 必查保真面

- 字体与排版：沿用现有 Inter、Microsoft YaHei UI、Microsoft YaHei、PingFang SC 字体栈和标题、表头、正文层级，没有为第三阶段另造视觉体系。
- 间距与布局节奏：保留草稿审核的左文章、中信息图、右来源与质量三栏；用户指定的手动图片 Prompt 工作流放在中栏信息图编辑抽屉内。
- 颜色与视觉令牌：继续使用既有浅灰背景、白色表面、知乎蓝主色和绿色/橙色/红色状态语义；没有大面积渐变、发光或装饰动画。
- 信息密度：中栏首屏显示信息图真实预览、版本、模板和状态，完整编辑功能进入抽屉；发布中心按内容准备、发布日历、执行记录分层。
- 图片与图标：工作台图标继续使用 Ant Design Icons；信息图预览和 PNG 均由真实 HTML/CSS 渲染，不使用占位图或手绘图标。
- 文案：明确“不调用图片 API”“在 ChatGPT 手动生图”“上传后叠加准确中文”和“输入确认发布”的安全边界。
- 交互：验证了内容编辑、删除、拖拽排序、模板切换、字体缩放、背景上传/删除、纯 CSS、Prompt 中英文复制、历史恢复、PNG 渲染/下载、日历拖动和强制确认状态。
- 无障碍：主要控件使用语义按钮、标签页、文本框、表格和对话框；按钮具备可读名称，禁用态和错误态可被识别。

## Comparison History

1. 初次对比发现 P1：信息图“共识说明”文本框被外层网格压缩成很窄的单列，长文案难以编辑。修复：为共识字段增加独立布局容器，并为共识列表补上真实拖拽排序。复测证据：`phase3-infographic-editor-fixed-1440.png`。
2. 初次控制台检查发现 P2：Ant Design Drawer 的 `width` 属性产生弃用警告。修复：迁移到 `size` 属性。最终重新打开草稿审核、信息图抽屉和手动图片 Prompt 标签后，最新控制台 error 为 0。
3. 全景对比确认：草稿审核原有三栏结构、导航宽度、页面标题、文章编辑区和右侧质量栏均保持；第三阶段只重构中栏为真实信息图预览和完整编辑入口。
4. 聚焦对比确认：手动图片 Prompt 没有移到独立页面，仍在草稿审核的信息图编辑上下文中；Prompt 管理页只管理生产文本 Prompt 版本。
5. 1440 和 900 两个发布中心视口复查均未发现页面级横向溢出、遮挡或不可达主要操作。
6. 最终全景、聚焦、编辑器、Prompt 管理和发布中心复查未发现新的 P0、P1 或 P2 问题。

## 浏览器验收证据

- browser-rendered screenshots：`artifacts/ui/phase3-*.png`
- primary interactions tested：打开信息图编辑器、切换手动图片 Prompt、检查中英文 Prompt、检查内容编辑字段和拖拽入口、发布中心三页签、Prompt 管理、浏览器安全设置。
- responsive viewports：1440 × 900、900 × 900；发布中心页面级 `horizontalOverflow=false`。
- console errors checked：修复后的最终访问时间段内 0 条 error。

## Implementation Checklist

- [x] 手动图片 Prompt 工作流位于草稿审核
- [x] 草稿三栏信息架构保持
- [x] 信息图编辑器核心控件真实可用
- [x] 1080 × 1440 预览与导出比例一致
- [x] 发布中心桌面和窄屏检查
- [x] Prompt 管理和设置入口检查
- [x] 控制台弃用警告清零
- [x] 同屏全景和聚焦对比完成

## Follow-up Polish

- 真实运营数据达到数十条排期后，可再补一次周历密集状态、记录分页和批量操作的视觉压测。

final result: passed
