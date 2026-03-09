# 数据库 Schema 参考

## 概述

- 引擎：SQLite（文件 `logistics.db`）
- 异步驱动：aiosqlite
- 同步初始化：sqlite3（`init_db.py` 幂等建表）
- 设计原则：发货单表冗余存储订单快照字段（`customer_name`, `product_name` 等），避免运行时 JOIN

## 表结构

### orders（客户订单表）

```sql
CREATE TABLE IF NOT EXISTS orders (
    order_id         TEXT PRIMARY KEY,        -- 格式: ORDER-YYYYMMDDHHmmss
    customer_name    TEXT NOT NULL,           -- 客户名称
    product_name     TEXT NOT NULL,           -- 货物名称/品类
    quantity         INTEGER NOT NULL,        -- 数量(件)
    delivery_address TEXT,                    -- 收货详细地址
    status           TEXT DEFAULT '待发货',    -- 状态: 待发货 | 已派发
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### shipments（发货单表）

```sql
CREATE TABLE IF NOT EXISTS shipments (
    shipment_id          TEXT PRIMARY KEY,    -- 格式: SHIP-YYYYMMDDHHmmss
    order_id             TEXT NOT NULL,       -- 关联订单号
    ship_type            TEXT NOT NULL,       -- 承运类型: 整车 | 零单
    status               TEXT NOT NULL,       -- 状态: 未订车 | 待填写 | 已发货

    -- 订单快照（冗余存储，解耦 JOIN）
    customer_name        TEXT,
    delivery_address     TEXT,
    product_name         TEXT,
    quantity             INTEGER,

    -- 整车司机信息（司机扫码填报）
    driver_name          TEXT,               -- 真实姓名
    driver_id_card       TEXT,               -- 身份证号
    driver_phone         TEXT,               -- 手机号
    truck_plate          TEXT,               -- 车牌号
    truck_type           TEXT,               -- 车型: 4.2米轻卡/6.8米中卡/...
    driver_token         TEXT,               -- UUID hex, 整车专属防伪 Token

    -- 零单第三方物流信息
    third_party_company  TEXT,               -- 第三方物流公司名
    third_party_tracking TEXT,               -- 运单号
    logistics_provider  TEXT DEFAULT '',      -- 后置分配的物流公司/承运方式（整车或第三方）

    -- 财务核算
    logistics_fee        REAL DEFAULT 0,     -- 对外物流费（客户结算价）
    actual_cost          REAL DEFAULT 0,     -- 对内实际成本（保密）
    profit               REAL DEFAULT 0,     -- 单票利润 = logistics_fee - actual_cost

    created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
    shipped_at           DATETIME,           -- 发货时间戳
    remarks              TEXT                -- 备注
);
```

## 状态机流转

```
Orders:   待发货 ──(创建发货单)──→ 已派发

Shipments(整车): 未订车 ──(司机扫码确认)──→ 已发货
Shipments(零单): 待填写 ──(文员补录物流)──→ 已发货
```

## ID 生成规则

| 实体 | 格式 | 示例 |
|---|---|---|
| order_id | `ORDER-YYYYMMDDHHmmss` | ORDER-20260303164500 |
| shipment_id | `SHIP-YYYYMMDDHHmmss` | SHIP-20260303164530 |
| driver_token | `uuid.uuid4().hex` (32位) | a1b2c3d4e5f6... |

> **注意**: 高并发下时间戳可能重复，生产环境应追加随机后缀或使用 UUID。


## 新增业务说明（后置分配物流）

- 新建发货单默认进入 `待分配物流` 状态；不再要求创建时手工选择整车/零单。
- 文员后置分配物流时自动推导业务模式：
  - 物流=`整车` → `ship_type=整车`，状态流转为 `已订车`
  - 物流=第三方公司 → `ship_type=零单`，填写运单号后流转为 `已发货`
