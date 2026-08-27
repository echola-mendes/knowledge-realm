# 知域 Web 页面风格（以调试页为准）

**依据页面：**  
- 调试 / 配置：`web/src/views/DebugView.vue`（`main.page.debug-page`）  
- **列表 + 筛选：** `web/src/views/DocumentsView.vue`（`main.page.docs-page`）  
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

侧栏（不要在内容页复刻）：底 `#f9fafb`，默认字 `#4b5563`，激活底 `#eff6ff`、字 `#2563eb`，品牌字 `#111827`。

---

## 2. 字体

- 全家：`"PingFang SC", "Hiragino Sans GB", "Noto Sans SC", "Microsoft YaHei", sans-serif`
- `body`：`14px` / `color: var(--text)`
- **业务页（debug 及同类）：在 `main` 上设 `font-size: 12.5px`**，按钮、pill、表格继承，不要再升到 16px
- 公式/代码：`ui-monospace, monospace`，约 `0.82rem`

### 字号阶梯（相对页面 12.5px）

| 角色 | 规则 | 约等于 |
|---|---|---|
| 页标题 `h1` | `1.05rem`，`margin: 0 0 0.25rem` | ~13px |
| 副标题 `.sub` | `0.75rem`，`color: var(--muted)`，`margin: 0` | ~9.5px |
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

全局默认 `.page`（窄内容页，如部分旧页）：`width: var(--page)` 即 `min(1120px, calc(100% - 2rem))`，`padding: 1.15rem 0 2rem`，`margin: 0 auto`。新工具页跟调试页：全宽 + `1rem 1.25rem 2rem`。

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
| 阶段数字框 | 高 `1.55rem`，`padding: 0.12rem 0.35rem`，圆角 `6px` | 密表单 |
| label 上下 | `margin: 0.3rem 0 0.15rem`（普通）；阶段 `0.2rem 0 0.08rem` | |

横向滚动优先于挤扁：阶段网格 `overflow-x: auto`，`minmax(8.5rem, 1fr)`。

---

## 4. 页头

结构：左标题 + 副文案，右操作。

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

### 按钮

| 类 | 外观 |
|---|---|
| `.btn` | 白底、`1px var(--line)`、圆角 **8px**（页内可改为 10px）、字 `0.78rem` 或 inherit |
| `.btn-primary` | 底/边 `--teal`，字白；disabled `opacity: 0.6` |
| `.btn-link` | 无边无底，字 `--teal` |
| `.btn-danger` | 无边无底，字 `--danger` |

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

### 输入

- 边 `1px var(--line)`，圆角 **8px**（密表单 6px）
- 宽 100%（卡片内）
- placeholder 不要当唯一 label；label 在字段上方

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
- 单元格左对齐，底边 `1px var(--line)`，`padding: 0.4rem 0.45rem`；默认 `white-space: nowrap`
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

1. `main` 使用 `page` + 页专类；工具页 `padding: 1rem 1.25rem 2rem`、`font-size: 12.5px`、全宽。
2. 页头：`h1` + `.sub`；主操作一个 `btn-primary`。
3. 内容进 `.card.pad`，边框+浅阴影，圆角 12px。
4. 颜色只走 §1 token；状态用 `--ok` / `--warn` / `--danger`。
5. 字号不大于 §2；label 用 muted 小字。
6. 表格密排 + 横滑；空状态写清下一步；列表页跟 **§12**。
7. 不要：大营销标题、渐变字、玻璃拟态、emoji 当图标、嵌套卡片、未要求的左边彩条。

图标：描边 SVG，`stroke-width` 约 1.7–1.8，与 `Icon.vue` / 调试页导出图标一致。

---

## 12. 列表页：筛选栏 + 数据表

**参考实现：** `DocumentsView.vue` → `main.page.docs-page`。知识库管理等带筛选表格的页面应复用同一 DOM 结构与样式数值，类名保持一致以便后续抽到全局 CSS。

### 12.1 页面壳（`.docs-page`）

列表页铺满主栏，纵向 flex，表格区吃掉剩余高度：

```css
.docs-page {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 1rem 1.25rem 1rem;
  font-size: 12.5px;
  background: transparent;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
```

- 页头 `.page-head`、筛选 `.toolbar`、错误 `.hint`：`flex-shrink: 0`
- 页内按钮：`padding: 0.5rem 0.85rem; border-radius: 10px; font-size: inherit`
- 页头 `h1`：`1.05rem`；页头下间距 `margin-bottom: 0.45rem`

### 12.2 筛选栏（`.toolbar`）

白卡片一行：左侧筛选字段，右侧操作按钮。

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
| `.toolbar` | `display: flex; flex-wrap: nowrap; gap: 0.35rem; align-items: center; margin-bottom: 0.4rem; padding: 0.45rem 0.55rem` |
| `.filters` | `width: 80%; display: flex; gap: 0.35rem; min-width: 0` |
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
| `.list-card .table-wrap` | `flex: 1; min-height: 0; overflow: auto` |
| `.pager` | `display: flex; justify-content: flex-end; align-items: center; gap: 0.45rem; margin-top: 0.55rem; color: var(--muted)` |
| `.pager .btn:disabled` | `opacity: 0.5; cursor: not-allowed` |

推荐列顺序（文档页）：**序号 → 文件名 → 概述 → 标签 → … → 操作**。

### 12.4 单元格辅助类

| 类 | 用途 | 要点 |
|---|---|---|
| `.seq` | 序号 | `color: var(--muted); width: 2.2rem` |
| `.file-cell` | 文件名链接 | `white-space: nowrap`；链接用全局 `a` 色 |
| `.overview` | 概述 | `max-width: 12rem`；正文超 **15 字** 显示「前 15 字…」 |
| `.overview .tip` | 概述悬浮全文 | hover 显示白底浮层：`border + shadow`，`font-size: 0.68rem`，`max-width: 22rem` |
| `.tags-cell` | 标签 | 每标签一个全局 `.pill`；**最多 3 个**，超出加 `…` pill；hover `title` 显示全部 |
| `.tags-cell .pill` | 表内标签 pill | `padding: 0.08rem 0.45rem; font-size: 0.62rem; margin-right: 0.2rem; cursor: default` |
| `.ops` | 操作列 | `display: flex; gap: 0.7rem`；`.btn-link` + `.btn-danger` |
| `.pick-count` | 对比模式计数 | 表头内 `0/2`，`font-size: 0.62rem`，块级副行 |

### 12.5 复制到新列表页的 HTML 骨架

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
