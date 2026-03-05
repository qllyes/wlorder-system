---
name: wlorder-logistics-dev
description: 物流调度管理系统（wlorder-system）的全栈开发指南。使用 NiceGUI + SQLite + aiosqlite 技术栈，覆盖订单管理、整车/零单发货调度、司机扫码确认、费用核算和数据看板的完整 O2O 闭环。当需要开发、迭代或修复该物流系统的任何功能时触发此 Skill。
---

# 物流调度系统开发指南

## 开发约束（文档驱动开发 - Document-Driven Development）
**核心原则**：本项目采用文档驱动代码的模式。
- 当代码（业务逻辑、数据库结构、UI架构等）发生任何修改时，**必须同步将变更更新至相关文档**（包括本 SKILL 文档本身，以及对应的 PRD 或 readme 文件）。
- 代码实现必须始终以文档中的定义为准，确保文档与代码的绝对一致性。

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

新版流程：在“发货调度”或者订单录入阶段直接选择【整车/零单】，保存即完成派单分流，极大提升了调度效率。支持后置的**异常防呆管理**（如“重新编辑模式”、“撤回重发”、“彻底作废归档”），以应对现实业务突发情况。

整车/零单分流以及异常状态处理是系统核心，详见系统实际运行与相关注释。

## 开发工作流

按以下顺序开发或迭代，每步参考对应文档：

### 1. 数据库层

参考 [db_schema.md](references/db_schema.md)。

- 在 `init_db.py` 中使用 `CREATE TABLE IF NOT EXISTS`（幂等）
- orders 表 + shipments 表，shipments 冗余存储订单快照
- 核心状态机 (Shipments):
  - 顺向：`未订车`/`待填写` → `已订车`(仅整车) → `已发货`
  - 逆向流转操作：
    - `作废`：防呆机制，对多余或误操作的发货单进行**软隔离**，状态变更为 `已作废`，不再向下流转参与后续核算环节。
    - `撤销/回驳`：针对已发货但物流出现退换错等异常，清除该项原有全部下属司机、第三方物流、车辆信息，**使单据直接退回 `未订车` 初始池中重新流转**。

### 2. 后端 API 层

参考 [api_spec.md](references/api_spec.md)。

- 所有函数为 `async def`，使用 `asynccontextmanager` 管理连接
- 返回 `dict` 或 `list[dict]`
- `create_shipment` 是核心：根据 `ship_type` 决定初始状态和 Token 生成（如果需要的话）。
- 生命期操作：`update_shipment_info` 覆盖基本信息编辑，`cancel_shipment` 作废处理，`rollback_to_unbooked` 实现已发货单据的回驳重生。

### 3. PC 端导航 (SPA)

参考 [ui_routes.md](references/ui_routes.md)。

- 统一入口 `/`：通过 `ui.tab_panels` 切换不同模块面板
- 订单管理面板：仅作为客户信息的快速录入工具
- 发货调度面板 (核心调度台)：
  - **解耦统一的新建入口**：集成所有发货单分派逻辑，直接发起源头任务。
  - **台账与高级管控表格**：查询筛选、防呆作废、信息覆盖重写、回驳撤回、以及带条件选择器的“纯净定制 Excel (CSV)”一键导出。
  - 弹窗功能集合：零单合单、扫码驱动弹窗、信息覆盖修改弹窗。
  - **高保真托运单预览（下钻极简视口）**：支持点击订单行直接打开仿真托运单UI界面，并在该页面执行打印和Excel导出，实现WYSIWYG（所见即所得）。
- 数据看板面板：统计卡片 + 明细列表
- 费用核算面板：对外费 / 对内成本录入、利润自动计算、保密控制

### 4. 移动端路由

参考 [ui_routes.md](references/ui_routes.md) 的 `/driver_confirm` 章节。

- **无 Header**，Mobile-First 设计
- Token 鉴权 + 状态三态分支（错误/已完成/正常表单）
- 表单：姓名、身份证、电话、车牌、车型
- 提交后刷新进入成功页


## 关键设计决策

1. **Token 防伪**：整车发货单创建时自动生成 UUID hex Token，二维码 URL 携带 `id` + `token` 双参数校验
2. **冗余快照**：shipments 表冗余存储 `customer_name`/`product_name` 等，避免运行时 JOIN
3. **Quasar Slot 通信**：表格自定义操作按钮通过 `$parent.$emit` → `table.on()` 传递事件到 Python
4. **SPA 切换机制**：使用 `ui.tab_panels` 替代多路由跳转，通过 `nonlocal` 或状态变量在面板间共享行为（如从订单页跳转至发货页）。
5. **二维码显示修复**：使用 `ui.image.set_source()` 替代 `ui.html.content` 解决异步刷新不显示的问题。
6. **侧边栏折叠 (Toggle)**：在 `ui.header` 提供菜单按钮控制 `left_drawer.toggle()`，适配不同宽度的屏幕作业。
7. **访问前缀可配**：司机端二维码的 base_url 通过 Input 框动态配置，同时传递给打印预览页。
8. **生命周期异常控制**：引入了“撤销回流”机制 (`rollback_to_unbooked`)，通过清除物流属性让已错发单据实现初始化重生，避免了数据库脏数据的累积。
9. **面向用户的导出报表**：在 `app.py` 内部使用纯净字典重新编排内置字段名导出 CSV，有效屏蔽了底层数据库敏感字段（主键/Token等），提升产品化质感。
10. **生单流入口解耦合并**：彻底剔除之前单独依附于外源订单的局部触发面板，将`创建发货操作`提升集中统合为一个全新的新建调度表单框。
11. **所见即所得打印机制**：引入仿真纸质托运单的HTML模板，将操作聚焦于可视化的单据中，符合调度文员的操作直觉。

## 运行与部署

```bash
# 开发运行
uv run python app.py
# 访问: http://localhost:8501

# 内网穿透（司机外部访问）
cpolar http 8501
# 将穿透域名填入发货调度页的"访问前缀"输入框
```

## ⚠️ 强制收尾工作流 (Skill 自我进化纪律)

凡是在对话中涉及以下任一变动：
1. 修改了 `init_db.py` 里的数据库结构（增删改任一字段）
2. 修改了 `app.py` 或 `backend_db.py` 里的核心 API 形参、返回结构或业务逻辑

**作为 AI 工程师，在向用户报告“开发/修改完成”之前，你必须强制执行以下动作，少一步都不行：**
- 必须立刻静默调用文件读取和写入工具，将上述代码的最新改动，同步更新到本 Skill 的 `references/db_schema.md` 或 `references/api_spec.md` 中。
- 只有在确认 reference 里的文档已经和最新代码 100% 对齐后，才能向用户输出已完成的提示，并在最后加上一句暗号：“*(系统日志：相关 Skill 规范已随代码静默同步进化)*”。
