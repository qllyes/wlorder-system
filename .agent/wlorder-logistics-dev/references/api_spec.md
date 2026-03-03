# 后端数据层 API 接口规范

## 概述

- 文件：`backend_db.py`
- 模式：纯 async 函数集（非 class），通过 `asynccontextmanager` 管理连接
- 返回值：统一返回 `dict` 或 `list[dict]`（通过 `aiosqlite.Row` + `dict()` 转换）

## 连接管理

```python
from contextlib import asynccontextmanager
import aiosqlite

DB_PATH = "logistics.db"

@asynccontextmanager
async def get_conn():
    """获取异步数据库连接，自动设置 row_factory 为 Row。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn
```

## 订单模块接口

### `fetch_all_orders() -> list[dict]`
查询全部订单，按创建时间降序。

### `get_order_by_id(order_id: str) -> dict | None`
按 order_id 查询单条订单。

### `create_order(order_id, customer_name, product_name, quantity, delivery_address) -> None`
插入一条新订单记录。

## 发货单模块接口

### `fetch_all_shipments() -> list[dict]`
查询全部发货单，按创建时间降序。

### `get_shipment_by_id(shipment_id: str) -> dict | None`
按 shipment_id 查询单条发货单。

### `create_shipment(order_id: str, ship_type: str) -> str | None`
- 根据 `ship_type` 决定初始状态：`整车` → `未订车`，`零单` → `待填写`
- 冗余复制订单快照字段到发货单
- 整车类型自动生成 `driver_token`（UUID hex）
- 同时更新关联订单状态为 `已派发`
- 返回新建的 `shipment_id`

### `update_lingdan_info(shipment_id: str, company: str, tracking: str) -> None`
- 更新零单的第三方物流信息
- 自动设置 `status='已发货'`, `shipped_at=datetime('now','localtime')`

### `confirm_zhengche_driver(shipment_id, name, id_card, phone, plate, truck_type) -> None`
- 更新整车的司机与车辆信息
- 自动设置 `status='已发货'`, `shipped_at=datetime('now','localtime')`

## 待扩展接口（规划中）

### 费用核算
```python
async def update_shipment_fee(
    shipment_id: str,
    logistics_fee: float,  # 对外物流费
    actual_cost: float     # 对内实际成本
) -> None:
    """更新费用并自动计算利润。"""
    profit = logistics_fee - actual_cost
    # UPDATE shipments SET logistics_fee=?, actual_cost=?, profit=? WHERE shipment_id=?
```

### 看板统计
```python
async def get_dashboard_stats(date: str | None = None) -> dict:
    """返回指定日期（默认今天）的汇总统计。"""
    # 返回: { today_orders, pending_count, shipped_count, shipments_detail }
```
