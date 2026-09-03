# 知域 Web 页面风格（以调试页为准）

**依据页面：**  
- 调试 / 配置：`web/src/views/DebugView.vue`（`main.page.debug-page`）  
- **列表 + 筛选：** `web/src/views/DocumentsView.vue`（`main.page.docs-page`）  
- **首页提问搜索框：** `web/src/views/HomeView.vue`（`.ask` + `.btn.btn-primary`）  
**全局 token：** `web/src/styles.css` 的 `:root` 与 `.page` / `.card` / `.btn` / `.pill`  
**用途：** 登录页以外的业务页（文档、检索、对话、知识库、设置、调试）生成 UI 时对照本文，不要另起一套密度或配色。

调试页是**工具型 Operate 界面**：浅底、白卡片、12.5px 密排、蓝主操作。新页面复用同一套，不要加大成营销站字号。

---

## 1. 颜色

只用 CSS 变量；组件里不要新造灰阶。调试页阶段色是**例外**（见 §7），仅用于检索流水线语义，普通列表页不要用左边框彩条。

| Token | 值 | 用途 |
|---|---|---|
| `--bg` | `#f8fafc` | 主栏背景（`.app-main`） |
| `--chrome` | `#eaeff3` | 次级灰底（chip 未选、少数填充） |
| `--card` | `#ffffff` | 卡片、按钮默认底 |
| `--text` | `#1e293b` | 标题、正文、默认按钮字 |
| `--muted` | `#64748b` | 副文案、label、hint、空状态、表空行 |
| `--line` | `#e2e8f0` | 卡片边、输入框边、表横线、Tab 底线 |
| `--teal` | `#2563eb` | 主色：主按钮、链接、Tab 选中、开关开 |
| `--teal-soft` | `#dbeafe` | 选中行、弱强调底 |
| `--teal-mid` | `#bfdbfe` | 少用 |
| `--danger` | `#dc2626` | 错误、删除文字按钮 |
| `--warn` | `#d97706` | 处理中 |
| `--ok` | `#059669` | 已完成 |
| `--radius` | `12px` | 卡片圆角 |
| `--shadow` | `0 4px 14px rgba(15, 23, 42, 0.06)` | 卡片阴影（有偏移+模糊，不要 0 偏移光晕） |

链接：`color: var(--teal)`，hover 下划线。  
选中表行：`background: var(--teal-soft)`。  
开关关：`#cbd5e1`；开：`#2563eb`。  
箭头/弱图标：`#94a3b8`。

### 背景分层（整页）

| 层级 | 色值 / Token | 用在 |
|---|---|---|
| 主工作区底 | `--bg` `#f8fafc` | `.app-main`、对话页 `.chat-page` 外层 gutter |
| 侧栏底 | `#f9fafb` | `.sidenav`（略暖于主栏，与内容区区隔） |
| 侧栏分隔线 | `#e5e7eb` | `.sidenav` 右边框 |
| 内容卡片 | `--card` `#ffffff` | `.card`、筛选栏、表格、对话列表/主区白底 |
| 列表页路由底 | `transparent` | `.docs-page` 等，透出 `--bg` |

**视觉：** 侧栏与主栏之间无额外 gap；主栏浅灰底上叠白卡片。列表页标题、筛选、表格左缘与 **`padding-left: 1.25rem`** 对齐，与菜单栏右缘留出统一 gutter（见 §3.1）。

侧栏（不要在内容页复刻）：底 `#f9fafb`，默认字 `#4b5563`，激活底 `#eff6ff`、字 `#2563eb`，品牌字 `#111827`。折叠宽 `--rail: 4.5rem`（小屏 `4.2rem`），**固定折叠、不随 hover 展开**。菜单区 `.sidenav .nav` 可纵向滚动：`overflow-y: auto; overscroll-behavior: contain`，**滚动条隐藏**（`scrollbar-width: none` + `::-webkit-scrollbar { display: none }`，仍可滚动手势/触控板操作）；品牌头部（`.sidenav-head`）与底部（`.sidenav-foot`）固定不滚动。

---

## 2. 字体

- 全家：`"PingFang SC", "Hiragino Sans GB", "Noto Sans SC", "Microsoft YaHei", sans-serif`
- `body`：`14px` / `color: var(--text)`
- **业务页（debug 及同类）：在 `main` 上设 `font-size: 12.5px`**，按钮、pill、表格继承，不要再升到 16px
- 公式/代码：`ui-monospace, monospace`，约 `0.82rem`

### 字号阶梯（相对页面 12.5px）

| 角色 | 规则 | 约等于 |
|---|---|---|
| 页标题 `h1` | `1.05rem`，`font-weight: 700`，`color: var(--text)`，`margin: 0 0 0.25rem` | ~13px，深色标题 |
| 副标题 `.sub` | `0.75rem`，`font-weight: 400`，`color: var(--muted)`，`margin: 0`，行高继承 | ~9.5px，灰色说明 |
| 区块标题 `.block-title` | `0.8rem`，`margin: 0 0 0.45rem` | ~10px |
| 卡片 `h2` | `0.78rem`，`margin: 0 0 0.4rem` | ~10px |
| 流水线节点 `h3` | `0.72rem`，`font-weight: 650` | ~9px |
| 表 / Tab / 阶段输入 | `0.72rem` | ~9px |
| **表头 `th`** | **`0.85rem`**（全局 `.page table th`），`font-weight: 500`，`color: var(--muted)` | ~10.5px |
| 表单 label | `0.68rem`，`color: var(--muted)` | ~8.5px |
| 卡片内正文/节点 p | `0.68rem` | ~8.5px |
| hint / `.tiny` | `0.75rem`，`color: var(--muted)` | ~9.5px |
| 阶段卡片超小 label | `0.62rem` | 仅配置格 |
| 图例说明 | `0.58rem`，行高 `1.4` | 仅参数说明卡 |

不要 eyebrow（标题上方小标签）。标题自己够用。

---

## 3. 页面边距与节奏

### 3.1 与侧栏（菜单栏）的间距

应用壳：`aside.sidenav` + `.app-main` 横排，`gap: 0`（无中间缝）。内容区距菜单栏的边距由**路由页 `padding-left`** 控制，不要再用全局 `.page` 的 `margin: 0 auto` 居中窄栏。

| 页面类型 | 参考类 | padding（上 · 右 · 下 · 左） | 说明 |
|---|---|---|---|
| 列表 / 工具页 | `.docs-page`、`.debug-page` | `1rem 1.25rem 0.75rem`～`2rem` | **左 1.25rem（20px）** 为标准 gutter，与文档页截图一致 |
| 搜索 | `.search-page` | `1rem 1.25rem 2rem` | 全宽，左对齐，同列表页 gutter |
| 对话 | `.chat-page` | `0.75rem 0.75rem 0.75rem 1rem` | 外层 `--bg` gutter；内层 `.chat-list` / `.chat-main` 为白卡片 + `gap: 0.75rem` |

约定：

- **标准内容左距菜单栏：** `1.25rem`（`padding-left` on `main`）
- 页内白卡片（`.card`）贴齐该左缘，不再额外 `margin-left`
- 侧栏宽 `4.5rem`，内容从侧栏右缘 + padding 起算
- 小屏（`≤800px`）侧栏 `4.2rem`，内容 gutter 仍用 `1.25rem`（或对话页 `1rem`）

内容页**铺满主栏**（调试页覆盖全局 `.page` 的窄栏）：

```css
.debug-page {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 1rem 1.25rem 2rem; /* 上 16px · 左右 20px · 下 32px */
  font-size: 12.5px;
  background: transparent;
}
```

全局默认 `.page`（**旧窄栏，新页勿用**）：`width: var(--page)` 即 `min(1120px, calc(100% - 2rem))`，`padding: 1.15rem 0 2rem`，`margin: 0 auto`。新工具页跟调试 / 文档 / 搜索：**全宽 + 左 `1.25rem` gutter**。

| 间距 | 值 | 用在 |
|---|---|---|
| 页头下 | `1rem`（`.page-head` `margin-bottom`） | 标题区与正文 |
| 页头内部 | `gap: 1rem`，`flex-wrap` | 标题 vs 操作 |
| 区块之间 | `margin-bottom: 1rem` 或网格 `gap: 0.85rem`～`1rem` | 卡片组 |
| 三列顶栏网格 | `gap: 0.85rem`，`margin-bottom: 1rem` | `.top-grid` |
| 阶段网格 | `gap: 0.65rem`，`margin-bottom: 1rem` | `.stage-grid` |
| 双列底栏 | `gap: 1rem`，`margin: 1rem 0` | `.bottom-grid` |
| 操作簇 | `gap: 0.4rem` | `.head-actions`、`.chips` |
| 卡片内边距 `.pad` | `1rem 1.1rem` | 普通卡片 |
| 阶段卡内边距 | 标题 `0.4rem 0.55rem`；body `0.35rem 0.55rem 0.5rem` | 紧凑配置格 |
| 表单元格 | `0.4rem 0.45rem` | `th, td`；文档列表 tbody 另设 `min-height: 36px`、上下 `0.55rem` |
| 输入框 | `padding: 0.4rem 0.5rem`；圆角 `8px` | 普通表单 |
| **首页提问搜索框** | `padding: 0.45rem 0.7rem`；圆角 **10px**；行高约 **36px** | `HomeView` `.ask input`，见 §6 |
| 阶段数字框 | 高 `1.55rem`，`padding: 0.12rem 0.35rem`，圆角 `6px` | 密表单 |
| label 上下 | `margin: 0.3rem 0 0.15rem`（普通）；阶段 `0.2rem 0 0.08rem` | |

横向滚动优先于挤扁：阶段网格 `overflow-x: auto`，`minmax(8.5rem, 1fr)`。

---

## 4. 页头

结构：左标题 + 副文案，右操作。标题与说明始终成对出现；说明只用一行 `.sub`，不要 eyebrow。

```html
<div class="page-head">
  <div>
    <h1>页面名</h1>
    <p class="sub">一句说明当前范围或注意点。</p>
  </div>
  <div class="head-actions">
    <button class="btn">次操作</button>
    <button class="btn btn-primary">主操作</button>
  </div>
</div>
<p class="hint">一行状态/提示</p>
```

### 页头字体（文档页定稿）

| 元素 | 字号 | 字重 | 颜色 | 间距 |
|---|---|---|---|---|
| `h1` | `1.05rem`（相对页内 `12.5px`） | `700` | `var(--text)` `#1e293b` | `margin: 0 0 0.25rem` |
| `.sub` | `0.75rem` | `400`（常规） | `var(--muted)` `#64748b` | `margin: 0` |

列表页（`.docs-page`）页头下间距：`margin-bottom: 0.45rem`（略紧于全局 `.page-head` 的 `1rem`）。

### 主标题 + 说明块的上下左右边距

标题与说明包在 `.page-head` 左侧 `<div>` 里，**块自身不设任何 margin / padding**，四周距离全部来自外层容器与 `.page-head`：

| 方位 | 距离 | 来源 |
|---|---|---|
| 上 | `1rem`（16px） | 页面容器 `padding-top`（列表/工具/基础页均为 `1rem`；全局 `.page` 旧窄栏为 `1.15rem`） |
| 左 | `1.25rem`（20px） | 页面容器 `padding-left`（标准 gutter，见 §3.1）；块内元素不额外缩进 |
| 下 | `1rem`（16px） | `.page-head { margin-bottom: 1rem }` 与正文卡片隔开；列表页覆盖为 `0.45rem` |
| 右 | 随容器右缘 | `.page-head` 占满容器宽度，右侧操作块（`.head-actions`）贴容器右缘 |

块内节奏：

- `h1` 与 `.sub` 之间 `0.25rem`（`h1` 的 `margin-bottom`），`.sub` 自身 `margin: 0`
- `.page-head` 为 flex：`justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap`，窄屏时右块折行
- 块内文字一律左对齐，`h1`、`.sub` 均无左右 margin
- 自带 scoped 样式的页面（工具占位、监控、菜单管理等）照抄同一套值：容器 `padding: 1rem 1.25rem 2rem`、`h1` `font-size: 1.05rem; margin: 0 0 0.25rem`、`.sub` `0.75rem; margin: 0`、`page-head` `margin-bottom: 1rem`

- `.page-head`：`display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap`
- 次按钮白底描边；**一页一个** `.btn-primary`（蓝底白字）
- 调试页按钮额外：`padding: 0.5rem 0.85rem; border-radius: 10px; font-size: inherit`

---

## 5. 卡片

```css
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius); /* 12px */
  box-shadow: var(--shadow);
}
```

- 一块卡片一层：里面不要再套卡片。
- 普通内容加 `.pad`。
- 不要装饰性左边框（阶段卡除外）。

---

## 6. 控件

全局实现在 `web/src/styles.css`。首页提问条见本节「搜索框 + 提问按钮」。

### 按钮

定义在 `styles.css`，各页直接用 `.btn` / `.btn-primary`，不要再写一套蓝按钮。

```css
.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--text);
  border-radius: 8px;
  padding: 0.32rem 0.7rem;
  cursor: pointer;
  font-size: 0.78rem;
}
.btn-primary {
  background: var(--teal);      /* #2563eb */
  border-color: var(--teal);
  color: #fff;
}
.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
```

| 类 | 外观 |
|---|---|
| `.btn` | 白底、`1px var(--line)`、圆角 **8px**（页内可改为 10px）、字 `0.78rem` 或 inherit |
| `.btn-primary` | 底/边 `--teal`，字白；disabled `opacity: 0.6` |
| `.btn-link` | 无边无底，字 `--teal` |
| `.btn-danger` | 无边无底，字 `--danger` |

调试 / 列表页按钮可覆盖为 `padding: 0.5rem 0.85rem; border-radius: 10px; font-size: inherit`。首页提问按钮**不要**覆盖，跟全局 `.btn-primary`。

### 搜索框 + 提问按钮（首页 `.ask`）

**参考实现：** `HomeView.vue` → `section.hero-row` 内 `.card.hero > .ask`。  
新页需要「一行输入 + 主操作」时复用这一套，不要另起高度或圆角。

```html
<div class="ask">
  <input placeholder="例如：梳理文档的核心结论…" />
  <button class="btn btn-primary" type="button">提问 →</button>
</div>
```

```css
.ask {
  display: flex;
  gap: 0.6rem;
  margin-top: 1rem;
  flex-wrap: wrap;
}
.ask input {
  flex: 1;
  min-width: 12rem;
  border: 1px solid var(--line); /* #e2e8f0 */
  border-radius: 10px;
  padding: 0.45rem 0.7rem;
  background: #fff;
  color: var(--text);
  font: inherit; /* body 14px */
}
```

| 元素 | 规则 | 实测 |
|---|---|---|
| `.ask` | 横排 flex，`gap: 0.6rem`，默认同行 stretch（按钮跟输入框同高） | — |
| 搜索框 | 边 `1px var(--line)`，圆角 **10px**，`padding: 0.45rem 0.7rem`，`flex: 1`，`min-width: 12rem` | 高约 **36px** |
| 提问按钮 | 全局 `.btn.btn-primary`，文案「提问 →」；不另设 padding / 圆角 | 高约 **36px**（随输入框 stretch） |

约定：

- placeholder 用「例如：…」示例句，**不要**写「请输入」
- Enter 等同点击主按钮
- 输入框圆角 **10px**，比普通表单 8px 略大；按钮仍用全局 **8px**
- 不要给输入框加左边图标条或外层描边容器（那是检索页 `.bar-field`，见 `SearchView`）
- 字色 `--text`，placeholder 走浏览器默认（muted 感即可），边框 focus 不要换成粗彩边；需要强调时用 `outline: 2px solid var(--teal); outline-offset: 2px`（§10）

### Chip / Pill

- 未选：底 `#eef1f4`，字 `--muted`，全圆角
- 选中 `.on`：底 `--teal`，字白
- 调试页 pill：`padding: 0.28rem 0.7rem`

### Tab（下划线型，结果表上方）

- 容器底边 `1px var(--line)`
- 按钮无底无边，字 `--muted`，`0.72rem`，`padding: 0.35rem 0.7rem 0.45rem`
- `.on`：字 `--teal`、`font-weight: 600`、底边 `2px solid var(--teal)`

### 开关

- 轨道 `2.1rem × 1.15rem`，圆角全圆
- 关 `#cbd5e1`，开 `#2563eb`
- 圆钮白 `0.9rem`，过渡 `left 0.15s`（尊重 `prefers-reduced-motion`）
- 旁标 `0.72rem`、`--muted`

### 输入（普通表单）

- 边 `1px var(--line)`，圆角 **8px**（密表单 6px）
- 宽 100%（卡片内）
- placeholder 不要当唯一 label；label 在字段上方
- 首页 / 对话入口那种「一行提问」用上方 **搜索框 + 提问按钮**（圆角 10px、高约 36px），不要套本段 8px 表单输入

---

## 7. 检索阶段色（仅流水线）

用于「Vector / BM25 / RRF / Rerank」同一语义在配置卡与 Pipeline 节点上对齐。

| 阶段 | 强调色 | 标题/节点底 | 标题字 | 节点边 |
|---|---|---|---|---|
| Vector | `#3b82f6` | `#f0f7ff` | `#1d4ed8` | `#e0edff` |
| BM25 | `#22a06b` | `#f3fbf6` | `#166534` | `#e3f5ea` |
| RRF | `#7c5cbf` | `#f6f3ff` | `#5b21b6` | `#ece7ff` |
| Rerank | `#e67e22` | `#fff8f1` | `#c2410c` | `#ffedd5` |
| Final / Query | 同 Vector 浅底或白 | `#f0f7ff` 或 `#fff` | — | `#e0edff` |

阶段卡：`border-left: 3px solid` 对应强调色。  
参数说明卡：底 `#eff6ff`，边 `#dbeafe`，标题/加粗 `#2563eb`。

文档列表等非流水线页**不要**用这套彩条。

---

## 8. 表格

- `width: 100%; border-collapse: collapse; font-size: 0.72rem`
- **表头** `th`：`font-size: 0.85rem`（见 `styles.css` 的 `.page table th`），`position: sticky; top: 0`，底 `--card`
- 单元格：`vertical-align: middle`；**表头与数据行全部水平靠左**（列表页 `.list-card` 内，见 §12.3）
- 底边 `1px var(--line)`，`padding: 0.4rem 0.45rem`；默认 `white-space: nowrap`
- 外包 `.table-wrap { overflow: auto }`；列表页内 `.list-card .table-wrap` 可 `flex: 1; min-height: 0` 占满剩余高度
- 空数据：一行 `colspan`，类 `.empty`，文案说明下一步
- 可点行 / 选中行：`.on` → `background: var(--teal-soft)`
- 斑马行：奇数行 `var(--card)`，偶数行 `var(--bg)`

**列表页完整规范见 §12（文档页已实现）。**

---

## 9. 布局模板

复制调试页的网格，不要自创间距。

| 类 | 列 | 断点 |
|---|---|---|
| `.top-grid` | 3 列 `minmax(0, 1fr)` | `≤560px` 单列 |
| `.stage-grid` | 6 列 `minmax(8.5rem, 1fr)`，可横滑 | — |
| `.detail-grid` | 2 列 | `≤720px` 单列 |
| `.bottom-grid` | `1.35fr 1fr` | `≤720px` 单列 |
| 全局 `.grid-3` / `.grid-2` | 等分，`gap: 1rem` | `≤880px` 单列 |

Pipeline：横向 `flex` + 节点 `flex: 1`，`min-width: 7.2rem`，箭头 `→` 色 `#94a3b8`。

---

## 10. 焦点与动效

- 可聚焦控件：`outline: 2px solid var(--teal); outline-offset: 2px`（侧栏已如此）
- 过渡控制在 **150–250ms**；状态变化才动，不要入场编排
- `prefers-reduced-motion: reduce` 时关掉开关与侧栏缩放过渡

---

## 11. 新页面检查清单

1. `main` 使用页专类（如 `docs-page` / `search-page` / `chat-page`）；工具页 `font-size: 12.5px`、全宽；**左 gutter `1.25rem`**（对话页 `1rem`）。
2. 页头：`h1`（`1.05rem` / `700` / `--text`）+ `.sub`（`0.75rem` / `--muted`）；主操作一个 `btn-primary`。
3. 工作区背景 `--bg` `#f8fafc`；内容进 `.card.pad` 白底，边框+浅阴影，圆角 12px。
4. 颜色只走 §1 token；状态用 `--ok` / `--warn` / `--danger`。
5. 字号不大于 §2；label 用 muted 小字。
6. 表格密排 + 横滑；空状态写清下一步；列表页跟 **§12**。
7. 不要：大营销标题、渐变字、玻璃拟态、emoji 当图标、嵌套卡片、未要求的左边彩条。

图标：描边 SVG，`stroke-width` 约 1.7–1.8，与 `Icon.vue` / 调试页导出图标一致。

---

## 12. 列表页：筛选栏 + 数据表

**参考实现：** `DocumentsView.vue` → `main.page.docs-page`。知识库管理等带筛选表格的页面应复用同一 DOM 结构与样式数值，类名保持一致以便后续抽到全局 CSS。

### 12.1 页面壳（`.docs-page`）

列表页铺满主栏，纵向 flex，**页面本身不滚动**；表格区在 `.list-card .table-wrap` 内滚动。与全局 `.app-main` 配合：`app-main` `overflow: hidden`，首子路由页 `flex: 1; min-height: 0`，底栏 `.footer-note` `flex-shrink: 0`。

```css
.docs-page {
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 1rem 1.25rem 0.75rem;
  font-size: 12.5px;
  background: transparent;
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
```

- 页头 `.page-head`、筛选 `.toolbar`、错误 `.hint`、对比结果等非列表卡片：`flex-shrink: 0`
- 页内按钮：`padding: 0.5rem 0.85rem; border-radius: 10px; font-size: inherit`
- 页头 `h1`：`1.05rem`；页头下间距 `margin-bottom: 0.45rem`
- **不要**在页面底部出现整页横向滚动条；列过多时仅在 `.table-wrap` 内横滑

### 12.2 筛选栏（`.toolbar`）

白卡片一行：左侧筛选字段，右侧操作按钮；窄屏可换行。

```html
<section class="card pad toolbar">
  <div class="filters">
    <select class="filter" aria-label="…">…</select>
    <input type="search" placeholder="文件名" aria-label="文件名" />
    <select class="filter" aria-label="…">…</select>
  </div>
  <div class="toolbar-actions">
    <button class="btn btn-primary" type="button">查询</button>
    <button class="btn btn-primary" type="button">导入</button>
  </div>
</section>
```

| 类 / 元素 | 规则 |
|---|---|
| `.toolbar` | `display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center; margin-bottom: 0.4rem; padding: 0.45rem 0.55rem` |
| `.filters` | `flex: 1 1 16rem; display: flex; flex-wrap: wrap; gap: 0.35rem; min-width: 0` |
| `.filters select`, `.filters input` | `flex: 1 1 0; min-width: 0; padding: 0.28rem 0.4rem; margin: 0` |
| `.toolbar select`, `.toolbar input` | 同上 padding；边 `1px var(--line)`，圆角 `8px`，底 `#fff`（继承卡片内输入规则） |
| `.toolbar-actions` | `display: flex; gap: 0.35rem; margin-left: auto; flex-shrink: 0` |

约定：

- placeholder 作提示（如「文件名」「知识库」「状态」「标签」），**不要**写「请输入」「请选择」
- 下拉默认不选（`value=""` + `disabled hidden` 占位项）；空值表示不过滤该维度
- 未选时下拉字色 `var(--muted)`（类 `.hinting`）
- 筛选项**不要**「全部…」选项
- 查询按钮触发筛选；Enter 在搜索框内等同查询
- 对比等多选模式：**不要**额外一行 hint 文案；用表头「对比」列 + 按钮文案切换（「对比」→「开始对比」）
- 文档处理失败原因**只在表格「失败原因」列**展示（省略 + `title` 悬浮全文）；**不要**在页顶 `.hint.err` 重复展示 reindex 失败文案

### 12.3 数据表（`.list-card`）

```html
<section class="card pad list-card">
  <div class="table-wrap">
    <table>…</table>
  </div>
  <div class="pager">
    <button class="btn" type="button">上一页</button>
    <span>1 / 3</span>
    <button class="btn" type="button">下一页</button>
  </div>
</section>
```

| 类 | 规则 |
|---|---|
| `.list-card` | `flex: 1; min-height: 0; display: flex; flex-direction: column; margin-bottom: 0` |
| `.list-card .table-wrap` | `flex: 1; min-height: 0; min-width: 0; overflow: auto; max-width: 100%` |
| `.list-card th` | `text-align: left; vertical-align: middle` |
| `.list-card td` | `text-align: left; vertical-align: middle` |
| `.list-card tbody td` | `min-height: 36px; padding-top/bottom: 0.55rem; line-height: 1.45` |
| `.pager` | `display: flex; justify-content: flex-end; align-items: center; gap: 0.45rem; margin-top: 0.55rem; color: var(--muted); flex-shrink: 0` |
| `.pager .btn:disabled` | `opacity: 0.5; cursor: not-allowed` |

**文档页列顺序（`DocumentsView`，2026-08 定稿）：**

对比（可选）→ 序号 → 文件名 → 概述 → 标签 → 文件类型 → 文件大小 → 切片长度 → 重叠长度 → **状态** → **失败原因** → **创建人** → **创建时间** → **操作**

操作列顺序：**切片 → 向量化 → 删除**（间距 `gap: 0.35rem`，全部左对齐）

**切片列表列顺序（`DocumentChunksView`）：**

序号 → 编号 → 切片 → **字符数** → 状态 → 创建时间 → **操作**

- 切片列：超长省略，`title` 悬浮全文（与失败原因省略策略一致）
- 字符数：按 Unicode 码点计数（`[...content].length`）
- 页壳 / **表头与行数据全部靠左** / 状态 pill：同本节其它规则；面包屑为 `文档 › 文件名 › 切片`
- 操作列：**向量化 → 删除**（无「切片」入口）
  - 向量化：仅重新嵌入**当前行切片**（`POST .../chunks/{chunk_id}/reindex`），不是整篇文档
  - 删除：仍删除**本文档**（与文档列表同一套 API）
- 页头**不要**再放「查看文档 / 向量化 / 删除」
- 列表卡片：全局 `.card` + **必须** `.pad`（`padding: 1rem 1.1rem`）

### 12.4 单元格辅助类

| 类 | 用途 | 要点 |
|---|---|---|
| `.seq` | 序号 | `color: var(--muted); width: 2.2rem` |
| `.file-cell` | 文件名链接 | `white-space: nowrap`；链接用全局 `a` 色 |
| `.overview` | 概述 | `max-width: 12rem`；正文超 **15 字** 显示「前 15 字…」 |
| `.overview .tip` | 概述悬浮全文 | hover 显示白底浮层：`border + shadow`，`font-size: 0.68rem`，`max-width: 22rem` |
| `.tags-cell` | 标签 | 每标签一个全局 `.pill`；**最多 3 个**，超出加 `…` pill；hover `title` 显示全部 |
| `.tags-cell .pill` | 表内标签 pill | `padding: 0.08rem 0.45rem; font-size: 0.62rem; margin: 0 0.1rem; cursor: default` |
| `.status-cell` | 状态 | 表头 `th`、数据 `td` 均用此类；内嵌 `.pill.status-pill` |
| `.status-cell .status-pill` | 状态徽章 | `inline-flex; align-items: center; padding: 0.08rem 0.45rem; font-size: 0.62rem; line-height: 1.45` |
| `.fail-reason` | 失败原因 | `max-width: 10rem` |
| `.fail-text` | 失败原因正文 | `overflow: hidden; text-overflow: ellipsis; white-space: nowrap`；完整文案放 `title` |
| `.ops` | 操作列 | 见 §12.6 |
| `.pick-count` | 对比模式计数 | 表头内 `0/2`，`font-size: 0.62rem`，块级副行 |

### 12.5 状态徽章色（文档列表）

状态文案与 `documentStatusLabel` 一致；语义色**仅**用于列表 pill，不用流水线左边框。

| 类 | 背景 | 字色 | 对应状态 |
|---|---|---|---|
| `.pill.ok` | `#ecfdf5` | `#059669` | 已完成 `ready` |
| `.pill.busy` | `#fff7ed` | `#ea580c` | 解析中 / 向量化中 `parsing` `indexing` |
| `.pill.idle` | `#f3f4f6` | `#6b7280` | 待处理 / 待向量化等 `pending` `parsed` |
| `.pill.bad` | `#fef2f2` | `#dc2626` | 解析失败 / 向量化失败 |

状态机与文案定义见根目录 `PRD.md`（文档状态）与 `memory-bank/design-document.md` §4.1.1。

### 12.6 操作列（`.ops`）

**按钮顺序（文档页定稿）：** 切片 → 向量化 → 删除

```html
<td class="ops">
  <RouterLink class="btn-link" to="…">切片</RouterLink>
  <button class="btn-link reindex-btn" type="button">向量化</button>
  <button class="btn-danger" type="button">删除</button>
</td>
```

| 规则 | 值 |
|---|---|
| 容器 | `display: flex; gap: 0.35rem; align-items: center; justify-content: flex-start; white-space: nowrap` |
| 子项 | `flex-shrink: 0`（避免点击后文案变长挤压邻按钮） |
| `.reindex-btn` | `min-width: 3em; text-align: left` |
| 向量化文案 | 默认「向量化」；请求进行中「处理中」；卡在解析/向量化「重试向量化」 |
| 进行中 | `:disabled` + `opacity: 0.55`；**处理中**保持至文档终态（完成/失败）后再恢复 |
| `.ops .btn-link:disabled` | `cursor: not-allowed; text-decoration: none` |

### 12.7 复制到新列表页的 HTML 骨架

```html
<main class="page docs-page">
  <div class="page-head">
    <div>
      <h1>页面名</h1>
      <p class="sub">一句说明。</p>
    </div>
  </div>
  <p v-if="error" class="hint err">{{ error }}</p>

  <section class="card pad toolbar">
    <div class="filters">…</div>
    <div class="toolbar-actions">
      <button class="btn btn-primary" type="button">查询</button>
    </div>
  </section>

  <section class="card pad list-card">
    <div class="table-wrap">
      <table>
        <thead><tr><th>…</th></tr></thead>
        <tbody>
          <tr><td colspan="N" class="empty">没有符合条件的数据。</td></tr>
        </tbody>
      </table>
    </div>
    <div class="pager">…</div>
  </section>
</main>
```

样式当前在 `DocumentsView.vue` 的 `<style scoped>`；新页先复制同类名与数值，全局化时再迁入 `styles.css`。

---

## 13. 工具页二级菜单（`.tools-page`）

**参考实现：** `ToolsLayout.vue`（工具）、`BasicsLayout.vue`（基础，同一套壳类名）。侧栏折叠图标栏点「工具 / 基础」后，主栏左侧再出二级菜单；右侧 `RouterView` 为对应子页。

高度约定：二级菜单**铺满主栏剩余高度**，不要随内容收缩成矮卡片。`.tools-page` 本身不滚动；`.nav-card` 与 `.tools-main` 各自内部滚动。

### 13.1 页面壳

页头（「工具」+ 副文案）在卡片**外面**，不要放进 `.nav-card`。

```css
.tools-page {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 1rem 1.25rem 0.75rem;
  font-size: 12.5px;
  background: transparent;
  display: flex;
  gap: 1rem;
  align-items: stretch;
  box-sizing: border-box;
  flex: 1;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.tools-nav {
  width: 13.75rem; /* 220px */
  flex-shrink: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.nav-head {
  margin: 0 0.15rem 0.85rem;
  flex-shrink: 0;
}
.nav-title {
  margin: 0 0 0.25rem;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
}
.nav-sub {
  margin: 0;
  font-size: 0.75rem;
  color: var(--muted);
}
.tools-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.tools-main :deep(.placeholder-page) {
  padding: 0;
}
```

| 元素 | 规则 |
|---|---|
| `.nav-title` | 同 §4 `h1` |
| `.nav-sub` | 工具页文案「发现更多 AI 工具，提升效率」；基础页「系统基础配置与个性化设置。」 |
| 基础页 `.tools-nav` 宽 | `min(12.5rem, 28vw)`，其余壳样式与工具页相同 |

### 13.2 菜单卡片（铺满侧栏剩余高度）

白卡片一层，里面不要再套卡片。卡片 `flex: 1` 吃掉 `.nav-head` 以下全部高度；项多时只在卡片内纵滑。

```css
.nav-card {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius); /* 12px */
  box-shadow: var(--shadow);
  padding: 0.45rem 0.4rem;
}
.nav-group + .nav-group {
  margin-top: 0.2rem;
}
```

基础页 `.nav-card` padding 用 `0.75rem 0.55rem`（项更少，略松）。

分组顺序（图标见 `Icon.vue`）：

| 分组 | 图标 `name` | 子项 | 路由 |
|---|---|---|---|
| 旅程 | `plane` | 我的行程单、创建新行程 | `/tools/trips`、`/tools/trips/new` |
| AI资讯 | `headset` | 资讯中心、历史记录 | `/tools/consult`、`/tools/consult/history` |
| AI生图 | `image` | 生图台、我的作品 | `/tools/image`、`/tools/image/works` |
| 更多工具 | `apps` | 工具市场 | `/tools/market` |

### 13.3 父级行（`.nav-parent`）

```css
.nav-parent {
  width: 100%;
  display: grid;
  grid-template-columns: 1.05rem 1fr 0.75rem;
  align-items: center;
  gap: 0.45rem;
  padding: 0.5rem 0.5rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}
.nav-parent:hover {
  background: #f8fafc;
}
.nav-parent.on {
  background: #eff6ff; /* 与侧栏激活底相同，比 --teal-soft 更浅 */
  color: var(--teal);
}
.nav-parent :deep(.ico) {
  width: 1rem;
  height: 1rem;
}
.nav-parent .chev {
  opacity: 0.55;
  color: #94a3b8;
  justify-self: end;
}
.nav-parent .chev :deep(svg) {
  transform: rotate(-90deg);
}
.nav-parent[aria-expanded="true"] .chev :deep(svg) {
  transform: rotate(0deg);
}
```

| 状态 | 底 | 字/图标 |
|---|---|---|
| 默认 | 透明 | `--text` `#1e293b`，`0.82rem` / `600` |
| hover | `#f8fafc` | 不变 |
| 组内有选中 `.on` | `#eff6ff` | `var(--teal)` |

chevron 收起 `-90deg`，展开 `0deg`（朝下）。基础页无折叠子项时用 `grid-template-columns: 1rem 1fr`，字 `0.78rem`，默认色 `#4b5563`，选中底 `var(--teal-soft)`。

### 13.4 子项（`.nav-child`）

子项相对父级标题文字对齐（给图标留位）：容器 `padding-left: 1.5rem`。

```css
.nav-children {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  padding: 0.12rem 0 0.28rem 1.5rem;
}
.nav-child {
  display: block;
  padding: 0.42rem 0.5rem;
  border-radius: 8px;
  color: #4b5563;
  text-decoration: none;
  font-size: 0.78rem;
  font-weight: 400;
}
.nav-child:hover {
  background: #f8fafc;
  text-decoration: none;
}
.nav-child.on {
  background: var(--teal-soft);
  color: var(--teal);
  font-weight: 600;
}
```

约定：

- 只高亮**精确子路由**（「我的行程单」不要在「创建新行程」时也亮）
- 父级 `.on` 表示该组下任一子路由命中
- 进入某组路由时自动展开该组；不要默认全部收起
- 描边 SVG 图标，`stroke-width` 跟 `Icon.vue`；不要用 emoji
- **不要**给 `.tools-nav` 设 `align-self: flex-start`，否则卡片不会拉高

样式当前在 `ToolsLayout.vue` / `BasicsLayout.vue` 的 `<style scoped>`。

---

## 14. 我的行程单（`.trips-page`）

**参考实现：** `MyTripsView.vue`。无行程状态；用 **行程类型** 筛选与展示。

### 14.1 顶栏

左面包屑 `工具 › 旅程 › 我的行程单`（`0.75rem` / `--muted`，当前项 `--text`）。右：搜索框 + 一个 `.btn-primary`「+ 新建行程」。

| 元素 | 规则 |
|---|---|
| 搜索 | 边 `1px var(--line)`，圆角 **8px**，`padding: 0.4rem 0.5rem`，placeholder「搜索行程目的地、关键词…」 |
| 新建 | 链到 `/tools/trips/new`，仍走对话规划占位，不要在本页造第二套创建表单 |

### 14.2 说明卡（`.hero`）

本页例外：浅蓝渐变横幅（token `#eff6ff` → `--teal-soft` `#dbeafe`），圆角仍 `--radius`，边 `var(--line)`。不要照片图、不要行程状态徽章。

| 区域 | 规则 |
|---|---|
| 左上 | 地图+定位针小插画 + `h1`（同 §4）+ `.sub` |
| 右上 | 白底 `.guide-btn`「使用指南」（书图标，同 `.btn` 密度） |
| 右下 | 山形/航线 SVG 装饰 + 灰色引言「“让每一次出发，都更从容”」（`#94a3b8`，弱图标色） |
| 左下三项 | 白底小图标 + 标题 `0.75rem` / `--text` + 说明 `0.68rem` / `--muted`：AI 智能规划（快速生成个性化行程）、多方案对比（灵活选择最佳方案）、一键导出分享（支持 PDF / 链接分享） |

### 14.3 类型 Tab + 日期

类型 pill（同 §6 Chip）：未选底 `#eef1f4`、字 `--muted`；选中 `.on` 底 `--teal`、字白。文案带真实条数：`全部` / `商务出行` / `旅游度假` / `学习交流` / `其他`。

右侧：开始日期 → 结束日期（按 **出发日期** 过滤）+「重置」。**不要**状态下拉。

### 14.4 表

列：行程名称、出发日期、创建时间、方案页、对话。不要状态列、不要复选框（无批量操作则不加）。

行程名称：左侧 2rem 浅底缩略图标 + 标题；第二行 muted `行程类型` + 可选 `N天M晚`（`nights` 为晚数，展示为 `{nights+1}天{nights}晚`）。

出发日期：`YYYY-MM-DD 周X`。底栏：`共 N 条记录` + `10 条/页` + 上一页/下一页。
