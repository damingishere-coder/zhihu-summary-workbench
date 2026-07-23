# 设计 Token

## 颜色

### 亮色

| Token | 值 | 用途 |
| --- | --- | --- |
| `color-bg-layout` | `#F6F8FB` | 应用底色 |
| `color-bg-container` | `#FFFFFF` | 主工作面 |
| `color-bg-subtle` | `#F2F5F9` | 轻量分组 |
| `color-text` | `#172033` | 主文本 |
| `color-text-secondary` | `#667085` | 次文本 |
| `color-border` | `#DCE3EC` | 分隔线 |
| `color-primary` | `#1769E0` | 主操作、选中 |
| `color-info` | `#1769E0` | 信息状态 |
| `color-success` | `#15805D` | 正常、完成 |
| `color-warning` | `#C76B16` | 待审核、警告 |
| `color-error` | `#D92D20` | 失败、危险 |

### 暗色

| Token | 值 |
| --- | --- |
| `color-bg-layout` | `#0F1724` |
| `color-bg-container` | `#151F2E` |
| `color-bg-subtle` | `#1B2737` |
| `color-text` | `#F2F5F9` |
| `color-text-secondary` | `#A6B1C2` |
| `color-border` | `#2A394D` |
| `color-primary` | `#5B9CFF` |

语义色在暗色下提高亮度但保持含义，不使用发光效果。

## 字体

- 字体栈：`Inter, "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", sans-serif`。
- 正文：14px / 22px / 400。
- 辅助文字：12px / 20px / 400。
- 表格标题：13px / 20px / 600。
- 页面标题：22px / 30px / 650。
- 数字指标：28px / 36px / 600。
- 不使用超过两套字体，不用全大写英文制造层级。

## 间距

使用 4px 基础网格，主要节奏为 8px：

```text
2, 4, 8, 12, 16, 20, 24, 32, 40, 48
```

- 页面外边距：24px；1280px 视口为 20px。
- 表单行间距：20px。
- 表格单元格水平内边距：12px。
- 紧凑表格行高：48px。
- 区块间距：24px。

## 圆角与阴影

- 小控件：4px。
- 输入、按钮、标签：6px。
- 抽屉和模态框：8px。
- 不使用超大圆角。
- 主页面不使用阴影分区；浮层使用 `0 8px 24px rgba(16, 24, 40, 0.12)`。

## 表格密度

- 桌面默认 `middle`，目标行高 48px。
- 长标题最多两行，列表默认单行省略。
- 低优先级列在 1280px 下隐藏，不压缩正文到 12px 以下。
- 固定操作列宽度不超过 120px。

## 表单布局

- 标签置于字段上方，标签与输入间距 6px。
- 帮助文字紧随输入下方，错误文字替换帮助文字但不引发布局跳动。
- 宽表单最大内容宽度 760px。
- API Key 使用密码输入框，服务端不返回原值。

## 断点

```text
xs: 480
sm: 576
md: 768
lg: 960
xl: 1280
xxl: 1440
```

## 无障碍

- 正文与背景对比度至少 4.5:1。
- 主要控件焦点环为 2px，不能被 `outline: none` 移除。
- 点击目标至少 32×32px。
- 图标按钮必须有可访问名称和 Tooltip。
- 状态不能只用颜色；同时使用文字和图标。
- 动态 SSE 更新使用非打断式 `aria-live="polite"`。
- 支持 `prefers-reduced-motion`。
