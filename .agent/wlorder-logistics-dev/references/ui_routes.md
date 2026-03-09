# 前端路由与 UI 规范

## 概述

- 框架：NiceGUI（内置 Vue3 + Quasar UI）
- 入口：`app.py`，`ui.run(port=8501, host='0.0.0.0')`
- 导航：**左侧固定侧边栏（Sidebar）**，内容区占满右侧剩余宽度

## 路由表
- **PC 控制台 (SPA)**: 所有主模块（订单、发货、看板、财务）合并在主路由 `/` 下，通过 `ui.tab_panels` 逻辑切换，点击侧边栏**不触发浏览器刷新**。

| 路由 | 模式 | 终端 | 描述 |
|---|---|---|---|
| `/` | SPA | PC | 总控制台：通过侧边栏点击切换 Content 面板 |
| `/driver_confirm` | 独立页面 | Mobile | 司机扫码确认页（二维码直达） |
| `/print` | 独立页面 | PC | 打印预览页（新窗口弹出，带打印样式） |

## 全局导航样式 (Sidebar & Header)

- **Header**: 位于顶部的白色工具栏，包含一个左侧的 `menu` 按钮，通过 `left_drawer.toggle()` 实现侧边栏折叠。
- **Sidebar**: 深色侧边栏，支持通过 Header 按钮或侧边栏底部的“收起菜单”按钮进行隐藏。

> **注意**：在 NiceGUI 中，侧边栏使用 `ui.left_drawer` 组件实现；页面函数需调用 `create_sidebar(active='当前页key')` 来激活当前菜单项。

### 二维码生成
```python
def generate_qr_base64(data: str) -> str:
    # 使用 python-qrcode 生成 PNG Base64 data URI
    # 嵌入完整 URL: {base_url}/driver_confirm?id={shipment_id}&token={driver_token}
```

### 本机 IP 获取
```python
def get_local_ip() -> str:
    # socket.gethostbyname(socket.gethostname())
    # 用于生成默认的司机端访问前缀
```

## 页面规范

### `/` 订单管理页

**布局结构**：
```
Sidebar (左侧, 240px)
└── 右侧内容区 (flex-grow)
    └── Column (max-w-6xl, 居中)
        ├── 页面顶部标题行
        │   ├── 左侧: 页面标题 "订单管理"
        │   └── 右侧: [+ 新建订单] 主操作按钮（点击弹出Dialog）
        ├── Card: 筛选器工具栏
        │   └── Row: [状态下拉多选] [日期区间选择] [货物名称关键词] [搜索按钮] [重置]
        └── Card: 历史订单列表
            └── Table (可刷新, 联动过滤器)
                ├── 列: 订单号 | 客户名 | 货物名称 | 数量 | 状态(Chip) | 创建时间 | 操作
                └── 操作: 待发货→点击跳转/shipments?order_id=X | 已派发→灰色禁用

Dialog: 新建订单（居中模态, min-w-[480px]）
    ├── 标题行: "📝 新建客户订单" + 关闭按钮 (X)
    ├── 内容区 (垂直排列字段):
    │   ├── 客户名称* (全宽 Input)
    │   ├── 货物品类* (全宽 Input)
    │   ├── 数量(#件)* (Number, min=1)
    │   ├── 收货地址* (全宽 Input)
    │   ├── 分割线 + 提示信息
    │   └── **发货模式选择*** (Radio: 整车 | 零单)
    └── 操作区 (Row, 右对齐):
        ├── 取消 (描边按钮)
        └── 确认并立即生单 (实心蓝色主按钮)
```

**筛选器规范**：
- **订单状态**：`q-select` 多选，选项：全部 / 待发货 / 已派发，默认空（显示全部）
- **创建日期范围**：开始日期 + 结束日期两个 `q-input type=date`
- **货物名称**：`q-input` 模糊搜索
- **默认排序**：`待发货` 优先，`created_at DESC`
- **前端过滤**：数据从后端全量拉取后，在前端用 Python filter 进行过滤，避免复杂 SQL 参数

**关键交互**：
- 订单号自动生成：`ORDER-YYYYMMDDHHmmss`
- **`+ 新建订单` 按钮**：放在页面标题行右上角，点击弹出模态 Dialog 而非在页内展开内嵌表单
- 提交后：关闭 Dialog + 刷新列表（`@ui.refreshable`）
- 状态 Chip 颜色：待发货=orange, 已派发=green

### `/shipments` 发货调度页

**布局结构**：
```
Header
└── Column (max-w-6xl)
    ├── Card (条件): 携带 order_id 时显示派发面板
    │   ├── 订单信息摘要
    │   ├── Radio: 整车 | 零单
    │   └── Button: 生成发货单
    └── Card: 调度总台账
        ├── Row: [当前访问前缀 Input] [刷新按钮]
        ├── Dialog(QR): 二维码大图弹窗
        ├── Dialog(零单): 补录第三方物流表单弹窗
        └── Table (可刷新)
            ├── 列: 发货号 | 承运类型(Badge) | 状态(Chip) | 客户名 | 物品 | 时间 | 操作
            └── 操作按钮:
                ├── 整车+未订车 → "司机端扫码" (呼出QR弹窗)
                ├── 零单+待填写 → "补录快递单" (呼出零单弹窗)
                └── 已发货 → "发货全闭环" (灰色禁用)
```

**关键交互**：
- QR 弹窗：根据 `base_url_input` + `/driver_confirm?id=X&token=Y` 生成二维码
- 零单弹窗：提交后调用 `update_lingdan_info`，状态自动变更
- Quasar slot 自定义渲染：`body-cell-actions`, `body-cell-status`, `body-cell-ship_type`

### `/driver_confirm` 司机确认页 (Mobile-First)

**设计原则**：
- **无 Header 导航栏**（去除 PC 端元素）
- **max-w-md 居中**，适配手机屏幕
- **大字体 + 醒目按钮 + 渐变色**

**三态分支**：
```
1. 参数缺失(无id/token) → 红色错误卡片
2. Token 校验失败      → 红色鉴权失败卡片
3. 已发货(终态)        → 绿色成功页("祝师傅一路平安")
4. 正常流程           → 任务简报 + 信息采集表单
```

**信息采集表单**：
```
Card: 任务简报
├── 订单号、配送目的地、物品/数量、收货方

Card: 核实车辆人员资质
├── Input: 真实姓名*
├── Input: 身份证号码*
├── Input: 手机号码* (inputmode=tel)
├── Separator
├── Input: 车牌号码*
├── Select: 车型* (4.2米轻卡|6.8米中卡|9.6米重卡|13.5米挂车|17.5米平板|特种车辆|微型面包车)
└── Button: "我已确认装箱完毕，发车！" (渐变蓝, w-full, 大号)
```

**提交后**：调用 `confirm_zhengche_driver` → 刷新页面进入"已发货成功页"

## NiceGUI 开发要点

1. **异步模式**：所有数据库操作使用 `async/await`，页面函数标记 `async`
2. **`@ui.refreshable`**：列表使用可刷新装饰器，支持 `.refresh()` 局部更新
3. **Quasar Slot**：通过 `table.add_slot()` 注入 Vue 模板实现自定义渲染
4. **事件通信**：通过 `$parent.$emit('event', props.row)` + `table.on('event', handler)` 实现 Slot 到 Python 的事件传递
5. **Dialog 模式**：弹窗和表格需在同一层级定义，通过变量传递当前操作行数据


## 物流分配交互补充（2026-03）
- 在“编辑发货单”与“分配物流”弹窗中，物流字段统一为**单一物流选项控件**（可搜索、可选择、可输入新值）。
- 不再并列展示“选择配置物流 + 手工填写物流”两个字段，避免互斥冲突与优先级歧义。
