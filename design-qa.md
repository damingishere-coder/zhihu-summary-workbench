# 第一阶段 Design QA

## 对比目标

- source visual truth path：`docs/design/reference-dashboard.png`
- implementation screenshot path：`artifacts/ui/dashboard-design-qa.png`
- 同屏全景证据：`artifacts/ui/design-qa-comparison.png`
- 顶部与指标聚焦证据：`artifacts/ui/design-qa-focus-header.png`
- 表格与日志聚焦证据：`artifacts/ui/design-qa-focus-table.png`
- 路由：`/dashboard`
- viewport：1487 × 1058 CSS px
- source pixels：1487 × 1058
- implementation pixels：1487 × 1058
- device density normalization：两张图均按 1:1 像素尺寸比较，没有缩放或设备外框
- state：桌面端、亮色主题、Redis/Worker/数据库在线。参考图是高数据量概念状态；实现图只展示本地数据库中真实完成的 1 条任务，未为了视觉密度加入静态假数据。

## Findings

- 没有遗留可执行的 P0、P1 或 P2 问题。
- [P3] 参考图的日期、自动刷新说明和操作按钮位于不同的顶部区域；实现把三个主要操作放在页面标题右侧，并以 15 秒查询刷新和 SSE 连接状态承担实时反馈。核心层级、操作可见性和扫描路径保持一致，本阶段无需阻断。
- [P3] 参考图用 10 行概念数据展示高密度表格；实现只显示通过真实浏览器创建并由真实 Worker 处理的任务。空余区域是“禁止静态假数据”的有意产品约束，不是布局缺失。

## 必查保真面

- 字体与排版：使用 Inter、Microsoft YaHei UI、Microsoft YaHei、PingFang SC 的稳定回退；标题、指标、表头、正文和辅助文本的字号/字重层级与参考图一致。长中文标题在表格中省略，在详情页完整换行。
- 间距与布局节奏：侧栏、标题区、双层指标区、任务表格和右侧日志保持参考图的主要区域关系。修正后日志栏从指标区顶部开始贯穿主工作区；1440 × 900 和 1280 × 720 均无页面级横向溢出。
- 颜色与视觉令牌：默认亮色主题映射参考图的白色表面、浅灰页面背景、知乎蓝主色以及绿色/橙色/红色状态色；另有可用的暗色主题。
- 图片质量与资产保真：从选定参考图提取并以 72 × 72 PNG 保存真实品牌图标，浏览器按 36 × 36 清晰显示；没有用手写 SVG、CSS 图形、Emoji 或占位图替代。其余图标来自统一的 Ant Design Icons 图标族。
- 文案与内容：页面文案独立可读，明确第一阶段、第二阶段和第三阶段边界；密钥、Cookie、账号信息不会在页面回显。
- 交互与状态：验证了添加问题、入队、Worker 消费、SSE 状态、任务详情、草稿审核、发布锁定、Mock 模型测试、重复入队禁用、亮暗主题、长标题、空状态和禁用状态。
- 无障碍：主要操作使用语义按钮/链接，表单有标签，状态区使用可访问名称，主题按钮有明确 aria-label；检查中未发现持久控件被遮挡。

## 全景与聚焦对比结论

- 全景：`design-qa-comparison.png` 在同一张图中按原始尺寸并排显示参考图与实现图，主要信息架构、侧栏比例、双层运行指标、表格工作区和日志栏保持一致。
- 顶部聚焦：`design-qa-focus-header.png` 可读地核对了真实品牌图标、导航选中态、标题、主要操作、指标字体、边界和状态颜色。
- 表格聚焦：`design-qa-focus-table.png` 可读地核对了工具栏、表头、状态标签、进度条、日志时间轴和工作区边界。数据行数量差异来自真实数据库状态，已单独分类为可接受约束。

## Comparison History

1. 初次真实浏览器检查发现 P2：路由切换保留上一页滚动位置，设置页标题可能离开首屏。修复：在路由层加入 pathname 变化后的滚动复位。复测证据：从草稿页 `scrollY=650` 切换发布页后 `scrollY=0`。
2. 初次控制台检查发现 P2：Ant Design 6 的 Alert、Timeline、Steps、Select、InputNumber、Space、Divider、Drawer 等弃用属性产生控制台错误级警告。修复：迁移到 `title`、`content`、`variant`、`suffix`、`separator`、`orientation`、`size` 等当前 API，并修正 Descriptions 跨列。复测：新浏览器页依次打开仪表盘、问题池、问题详情、任务抽屉、草稿、发布和设置，错误/警告数组为空。
3. 参考图与早期实现检查发现 P1：默认主题会跟随操作系统而进入暗色，与选定的亮色视觉目标不同。修复：首次访问固定使用亮色，仍保留用户主动选择并持久化暗色的能力。复测证据：同尺寸实现截图为 `theme=light`。
4. 参考图与早期实现检查发现 P2：操作日志只与表格并排，未从指标区顶部贯穿工作区。修复：将指标、基础设施和表格放入主列，日志作为完整右列。复测证据：最终 `design-qa-comparison.png`。
5. 聚焦检查发现 P2：早期品牌标记使用通用书本图标，不符合参考图。修复：直接从选定参考图提取源品牌 PNG，并通过真实 `<img>` 使用。复测证据：`design-qa-focus-header.png`，浏览器确认 `img[src="/brand-mark.png"]` 唯一存在。
6. 最终同屏全景和两个聚焦区域复查未发现新的 P0、P1 或 P2 问题。

## 浏览器验收证据

- browser-rendered implementation screenshot：`artifacts/ui/dashboard-design-qa.png`
- primary interactions tested：添加问题、保存、加入队列、Worker 处理、SSE 连接、详情导航、草稿打开、发布状态、Mock 模型测试、主题切换、任务抽屉、重复入队保护。
- responsive viewports：1440 × 900、1280 × 720；两者页面级 `horizontalOverflow=false`。
- console errors checked：最终检查 0 条 error / warning。

## Implementation Checklist

- [x] 默认亮色主题与参考图一致
- [x] 参考品牌图标使用真实图片资产
- [x] 主区域与日志栏比例复核
- [x] 1440 × 900 和 1280 × 720 响应式检查
- [x] 亮色/暗色主题检查
- [x] 控制台错误和弃用警告清零
- [x] 真实业务闭环与禁用态检查

## Follow-up Polish

- 第二阶段有真实数据规模后，可再验证 10 行以上表格的分页密度、批量选择和更多筛选器布局。

final result: passed
