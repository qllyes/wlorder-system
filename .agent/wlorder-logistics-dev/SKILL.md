---
name: wlorder-logistics-dev
description: 物流调度管理系统（wlorder-system）的全栈开发指南。使用 NiceGUI + SQLite + aiosqlite 技术栈，覆盖订单管理、整车/零单发货调度、司机扫码确认、费用核算和数据看板的完整 O2O 闭环。当需要开发、迭代或修复该物流系统的任何功能时触发此 Skill。
---

# 物流调度系统开发指南

## 技术栈

| 层 | 技术 | 备注 |
|---|---|---|
| 语言 | Python 3.10+ | 严格类型注解 |
| 前后端 | NiceGUI | 内置 Vue3 + Quasar，PC/Mobile 同构 |
| 数据库 | SQLite + aiosqlite | 无服务器，文件 `logistics.db` |
| 二维码 | python-qrcode | Base64 内嵌渲染 (修复：需 Pillow 依赖并使用 set_source 更新) |
| 导航模式 | SPA (单页应用) | 使用 `ui.tab_panels` 消除页面跳转刷新感 |
| 包管理 | uv | `uv run python app.py` 启动 |

## 架构分层

```
app.py          ← Interface Layer (NiceGUI 路由 + UI 渲染)
backend_db.py   ← Core Layer (纯 async 数据操作，无 UI 耦合)
init_db.py      ← Config Layer (DDL 建表，幂等)
logistics.db    ← SQLite 数据文件
```

**严格约束**：
- `backend_db.py` 禁止 import NiceGUI，禁止 print/UI 调用
- `app.py` 所有数据库调用必须 `await`，页面函数标记 `async`
- 金额字段中间计算保持高精度，仅最终展示时 `round()`

## 核心业务流

```
订单录入(选型) → 自动化调度分拣 → 整车(二维码→司机扫码) / 零单(文员补录) → 已发货 → 费用核算 → 看板
```

新版流程：在订单录入阶段直接选择【整车/零单】，保存即完成派单分流，极大提升了调度效率。

整车/零单分流是系统核心，详见 [prd.md](references/prd.md) 第3节。

## 开发工作流

按以下顺序开发或迭代，每步参考对应文档：

### 1. 数据库层

参考 [db_schema.md](references/db_schema.md)。

- 在 `init_db.py` 中使用 `CREATE TABLE IF NOT EXISTS`（幂等）
- orders 表 + shipments 表，shipments 冗余存储订单快照
- 状态机：Orders(`待发货`→`已派发`) / Shipments(`未订车`/`待填写`→`已发货`)

### 2. 后端 API 层

参考 [api_spec.md](references/api_spec.md)。

- 所有函数为 `async def`，使用 `asynccontextmanager` 管理连接
- 返回 `dict` 或 `list[dict]`
- `create_shipment` 是核心：根据 `ship_type` 决定初始状态和 Token 生成

### 3. PC 端导航 (SPA)

参考 [ui_routes.md](references/ui_routes.md)。

- 统一入口 `/`：通过 `ui.tab_panels` 切换不同模块面板
- 订单管理面板：快捷录入 + 列表（`@ui.refreshable`）
- 发货调度面板：二维码弹窗 + 零单补录弹窗 + 台账表格
- 数据看板面板：统计卡片 + 明细列表
- 费用核算面板：对外费 / 对内成本录入、利润自动计算、保密控制

### 4. 移动端路由

参考 [ui_routes.md](references/ui_routes.md) 的 `/driver_confirm` 章节。

- **无 Header**，Mobile-First 设计
- Token 鉴权 + 状态三态分支（错误/已完成/正常表单）
- 表单：姓名、身份证、电话、车牌、车型
- 提交后刷新进入成功页

### 5. 待开发模块

以下功能在 PRD 中定义但尚未实现：

| 模块 | 路由 | 核心功能 |
|---|---|---|
| 数据看板 | `/dashboard` | 当日统计卡片、积压数、已发货趋势 |
| 费用核算 | `/finance` | 对外物流费 / 对内成本录入、利润自动计算、保密控制 |
| 导航扩展 | Header | 增加看板和费用链接 |

## 关键设计决策

1. **Token 防伪**：整车发货单创建时自动生成 UUID hex Token，二维码 URL 携带 `id` + `token` 双参数校验
2. **冗余快照**：shipments 表冗余存储 `customer_name`/`product_name` 等，避免运行时 JOIN
3. **Quasar Slot 通信**：表格自定义操作按钮通过 `$parent.$emit` → `table.on()` 传递事件到 Python
4. **SPA 切换机制**：使用 `ui.tab_panels` 替代多路由跳转，通过 `nonlocal` 或状态变量在面板间共享行为（如从订单页跳转至发货页）。
5. **二维码显示修复**：使用 `ui.image.set_source()` 替代 `ui.html.content` 解决异步刷新不显示的问题。
6. **侧边栏折叠 (Toggle)**：在 `ui.header` 提供菜单按钮控制 `left_drawer.toggle()`，适配不同宽度的屏幕作业。
7. **访问前缀可配**：司机端二维码的 base_url 通过 Input 框动态配置，同时传递给打印预览页。
## 运行与部署

```bash
# 开发运行
uv run python app.py
# 访问: http://localhost:8501

# 内网穿透（司机外部访问）
cpolar http 8501
# 将穿透域名填入发货调度页的"访问前缀"输入框
```
