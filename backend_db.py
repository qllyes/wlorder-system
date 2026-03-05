"""
后端数据层 — 纯 async 函数集，禁止 import UI 框架。
所有函数返回 dict | list[dict] | None。
"""
from __future__ import annotations

import datetime
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator
import json

import aiosqlite

DB_PATH: str = str(Path(__file__).parent / "logistics.db")


@asynccontextmanager
async def get_conn() -> AsyncIterator[aiosqlite.Connection]:
    """获取异步数据库连接，设置 row_factory。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn


# ════════════════════════════════════════════════
#  订单模块
# ════════════════════════════════════════════════

async def fetch_all_orders() -> list[dict]:
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_order_by_id(order_id: str) -> dict | None:
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT * FROM orders WHERE order_id = ?", (order_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def create_order(
    order_id: str,
    customer_name: str,
    product_name: str,
    quantity: int,
    delivery_address: str,
) -> None:
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO orders
               (order_id, customer_name, product_name, quantity, delivery_address)
               VALUES (?, ?, ?, ?, ?)""",
            (order_id, customer_name, product_name, quantity, delivery_address),
        )
        await conn.commit()


# ════════════════════════════════════════════════
#  发货单模块
# ════════════════════════════════════════════════

async def fetch_all_shipments(
    status: str = '全部',
    customer_name: str = '',
    start_date: str = '',
    end_date: str = '',
    phone: str = '',
) -> list[dict]:
    query = "SELECT * FROM shipments WHERE 1=1"
    params = []
    
    if status and status != '全部':
        query += " AND status = ?"
        params.append(status)
        
    if customer_name:
        query += " AND customer_name LIKE ?"
        params.append(f"%{customer_name.strip()}%")

    if phone:
        query += " AND customer_phone LIKE ?"
        params.append(f"%{phone.strip()}%")
        
    if start_date:
        query += " AND date(created_at) >= ?"
        params.append(start_date)
        
    if end_date:
        query += " AND date(created_at) <= ?"
        params.append(end_date)
        
    query += " ORDER BY created_at DESC"
    
    async with get_conn() as conn:
        async with conn.execute(query, tuple(params)) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_shipment_by_id(shipment_id: str) -> dict | None:
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT * FROM shipments WHERE shipment_id = ?", (shipment_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


def _generate_id(prefix: str) -> str:
    """生成带随机后缀的业务 ID，避免高并发下时间戳冲突。"""
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return f"{prefix}-{ts}-{suffix}"


async def create_shipment(
    customer_name: str,
    product_name: str,
    quantity: int,
    delivery_address: str,
    ship_type: str,
    customer_phone: str = '',
    total_weight: float = 0.0,
    unit_price: float = 0.0,
    delivery_fee: float = 0.0,
    freight_fee: float = 0.0,
) -> str:
    """
    新建发货单（脱离 orders 表独立运行）。
    初始状态: 整车与零单均默认为 '未订车'。
    freight_fee = total_weight * unit_price + delivery_fee  (由 app 层计算后传入)
    """
    status = "未订车"
    token = uuid.uuid4().hex if ship_type == "整车" else None
    shipment_id = _generate_id("SHIP")
    order_id = _generate_id("ORD")

    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO shipments
               (shipment_id, order_id, ship_type, status,
                customer_name, delivery_address, product_name, quantity,
                driver_token, customer_phone,
                total_weight, unit_price, delivery_fee, freight_fee)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                shipment_id, order_id, ship_type, status,
                customer_name, delivery_address, product_name, quantity,
                token, customer_phone,
                total_weight, unit_price, delivery_fee, freight_fee
            ),
        )
        await conn.commit()
    return shipment_id


# ── 发货单基础操作 (修改与作废) ──

async def update_shipment_info(
    shipment_id: str,
    customer_name: str,
    product_name: str,
    quantity: int,
    delivery_address: str,
    ship_type: str,
    pickup_method: str = "送货上门",
    payment_method: str = "现付",
    customer_phone: str = '',
    total_weight: float = 0.0,
    unit_price: float = 0.0,
    delivery_fee: float = 0.0,
    freight_fee: float = 0.0,
) -> None:
    """编辑未发货的发货单基础信息，包含业务模式的切换及打单配置的更新"""
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT ship_type, driver_token FROM shipments WHERE shipment_id = ?",
            (shipment_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row: return
            
            old_ship_type = row["ship_type"]
            token = row["driver_token"]

        if ship_type == "整车" and old_ship_type != "整车":
            token = uuid.uuid4().hex
        elif ship_type == "零单":
            token = None
            
        set_status_snippet = "status='未订车', " if old_ship_type != ship_type else ""

        await conn.execute(
            f"""UPDATE shipments
               SET customer_name=?, product_name=?, quantity=?, delivery_address=?, 
                   ship_type=?, driver_token=?, {set_status_snippet}
                   pickup_method=?, payment_method=?, customer_phone=?,
                   total_weight=?, unit_price=?, delivery_fee=?, freight_fee=?,
                   driver_name=NULL, driver_id_card=NULL, driver_phone=NULL, truck_plate=NULL, truck_type=NULL,
                   third_party_company=NULL, third_party_tracking=NULL, batch_id=NULL
               WHERE shipment_id=? AND status IN ('未订车', '已订车')""",
            (customer_name, product_name, quantity, delivery_address, ship_type, token,
             pickup_method, payment_method, customer_phone,
             total_weight, unit_price, delivery_fee, freight_fee, shipment_id),
        )
        await conn.commit()

async def cancel_shipment(shipment_id: str) -> None:
    """确认作废未发货的发货单"""
    async with get_conn() as conn:
        await conn.execute(
            """UPDATE shipments
               SET status='已作废'
               WHERE shipment_id=? AND status IN ('未订车', '已订车')""",
            (shipment_id,),
        )
        await conn.commit()


async def batch_delete_shipments(shipment_ids: list[str]) -> int:
    """硬删除多条发货单记录（不限状态），同时清理商品明细子表。
    返回实际删除的行数。"""
    if not shipment_ids:
        return 0
    placeholders = ",".join("?" for _ in shipment_ids)
    async with get_conn() as conn:
        await conn.execute(
            f"DELETE FROM shipment_products WHERE shipment_id IN ({placeholders})",
            shipment_ids,
        )
        cur = await conn.execute(
            f"DELETE FROM shipments WHERE shipment_id IN ({placeholders})",
            shipment_ids,
        )
        deleted = cur.rowcount
        await conn.commit()
    return deleted

async def rollback_to_unbooked(shipment_id: str) -> None:
    """逆向业务：异常回退，撤销发货并清空所有的物流/司机绑定信息，重发货车码"""
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT ship_type FROM shipments WHERE shipment_id = ?",
            (shipment_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row: return
            ship_type = row["ship_type"]

        token = uuid.uuid4().hex if ship_type == '整车' else None
        
        await conn.execute(
            """UPDATE shipments
               SET status='未订车', driver_token=?,
                   driver_name=NULL, driver_id_card=NULL, driver_phone=NULL, truck_plate=NULL, truck_type=NULL,
                   third_party_company=NULL, third_party_tracking=NULL, batch_id=NULL
               WHERE shipment_id=? AND status='已发货'""",
            (token, shipment_id),
        )
        await conn.commit()

# ── 整车状态流转 ──

async def update_zhengche_to_yidingche(shipment_id: str) -> None:
    """调度员手工将整车从 '未订车' 变更为 '已订车'。"""
    async with get_conn() as conn:
        await conn.execute(
            """UPDATE shipments SET status='已订车'
               WHERE shipment_id=? AND ship_type='整车' AND status='未订车'""",
            (shipment_id,),
        )
        await conn.commit()


async def confirm_zhengche_driver(
    shipment_id: str,
    name: str,
    id_card: str,
    phone: str,
    plate: str,
    truck_type: str,
) -> None:
    """司机扫码确认发车，整车从 '已订车' → '已发货'。"""
    async with get_conn() as conn:
        await conn.execute(
            """UPDATE shipments
               SET driver_name=?, driver_id_card=?, driver_phone=?,
                   truck_plate=?, truck_type=?,
                   status='已发货',
                   shipped_at=datetime('now','localtime')
               WHERE shipment_id=?""",
            (name, id_card, phone, plate, truck_type, shipment_id),
        )
        await conn.commit()


# ── 零单状态流转 ──

async def update_lingdan_info(
    shipment_id: str,
    company: str,
    tracking: str,
) -> None:
    """文员填写第三方物流信息，零单 → '已发货'。"""
    async with get_conn() as conn:
        await conn.execute(
            """UPDATE shipments
               SET third_party_company=?, third_party_tracking=?,
                   status='已发货',
                   shipped_at=datetime('now','localtime')
               WHERE shipment_id=?""",
            (company, tracking, shipment_id),
        )
        await conn.commit()


# ── 零单合单 ──

async def batch_lingdan(shipment_ids: list[str]) -> str:
    """
    将多个零单关联到同一批次。
    返回生成的 batch_id。
    """
    batch_id = _generate_id("BATCH")
    async with get_conn() as conn:
        placeholders = ",".join("?" for _ in shipment_ids)
        await conn.execute(
            f"""UPDATE shipments SET batch_id=?
                WHERE shipment_id IN ({placeholders})
                  AND ship_type='零单'""",
            [batch_id, *shipment_ids],
        )
        await conn.commit()
    return batch_id


async def unbatch_lingdan(shipment_id: str) -> None:
    """将某个零单从合单批次中移除。"""
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE shipments SET batch_id=NULL WHERE shipment_id=?",
            (shipment_id,),
        )
        await conn.commit()


# ════════════════════════════════════════════════
#  费用核算
# ════════════════════════════════════════════════

async def update_shipment_fee(
    shipment_id: str,
    actual_unit_price: float,
    actual_delivery_fee: float,
) -> None:
    """
    根据实付单价和实付运送费计算 actual_cost （实付运输费），
    再用已存的 freight_fee （托运单运输费）减去 actual_cost 得出利润。
    actual_cost = total_weight * actual_unit_price + actual_delivery_fee
    """
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT total_weight, freight_fee FROM shipments WHERE shipment_id = ?",
            (shipment_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row: return
            tw = float(row["total_weight"] or 0)
            ff = float(row["freight_fee"] or 0)
        
        actual_cost = round(tw * actual_unit_price + actual_delivery_fee, 2)
        profit = round(ff - actual_cost, 2)
        
        await conn.execute(
            """UPDATE shipments
               SET actual_unit_price=?, actual_delivery_fee=?, actual_cost=?, profit=?
               WHERE shipment_id=?""",
            (actual_unit_price, actual_delivery_fee, actual_cost, profit, shipment_id),
        )
        await conn.commit()


# ════════════════════════════════════════════════
#  商品明细子表 CRUD
# ════════════════════════════════════════════════

async def save_shipment_products(
    shipment_id: str,
    products: list[dict],
) -> None:
    """先清后插：保存发货单的商品明细行。
    products 格式: [{'name': str, 'spec': str, 'qty': int, ...任意其他字典项...}, ...]
    """
    async with get_conn() as conn:
        await conn.execute(
            "DELETE FROM shipment_products WHERE shipment_id = ?",
            (shipment_id,),
        )
        for p in products:
            raw_json = json.dumps(p, ensure_ascii=False)
            await conn.execute(
                """INSERT INTO shipment_products
                   (shipment_id, product_name, spec, quantity, raw_data)
                   VALUES (?, ?, ?, ?, ?)""",
                (shipment_id, p.get('name', ''), p.get('spec', ''), int(p.get('qty', 0)), raw_json),
            )
        await conn.commit()


async def get_shipment_products(shipment_id: str) -> list[dict]:
    """获取某发货单的全部商品明细行，包含展开的原始全量字典数据。"""
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT product_name, spec, quantity, raw_data FROM shipment_products WHERE shipment_id = ? ORDER BY id",
            (shipment_id,),
        ) as cur:
            rows = await cur.fetchall()
            
    result = []
    for r in rows:
        item = dict(r)
        raw_str = item.pop("raw_data", "{}")
        try:
            raw_dict = json.loads(raw_str)
        except Exception:
            raw_dict = {}

        # ── 标准化核心字段（以 DB 列名为准，兼容旧数据）──
        merged: dict = {
            "product_name": item.get("product_name") or raw_dict.get("name") or "",
            "spec":         item.get("spec") or raw_dict.get("spec") or "",
            "quantity":     item.get("quantity") or raw_dict.get("qty") or 0,
        }

        # ── 展开 _raw（原始 Excel 行所有列）到顶层 ──
        raw_inner = raw_dict.get("_raw", {})
        if isinstance(raw_inner, dict) and raw_inner:
            for k, v in raw_inner.items():
                # _raw 的原始列优先覆盖，不覆盖已有的标准字段
                if k not in merged:
                    merged[k] = v

        result.append(merged)
    return result


# ════════════════════════════════════════════════
#  数据看板统计
# ════════════════════════════════════════════════

async def get_dashboard_stats() -> dict:
    """当日数据看板统计。"""
    today = datetime.date.today().isoformat()
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT COUNT(*) FROM orders WHERE date(created_at)=?", (today,)
        ) as cur:
            today_orders = (await cur.fetchone())[0]

        async with conn.execute(
            """SELECT COUNT(*) FROM shipments
               WHERE status IN ('未订车','已订车')"""
        ) as cur:
            pending_count = (await cur.fetchone())[0]

        async with conn.execute(
            "SELECT COUNT(*) FROM shipments WHERE status='已发货' AND date(shipped_at)=?",
            (today,),
        ) as cur:
            shipped_today = (await cur.fetchone())[0]

        async with conn.execute(
            """SELECT status, COUNT(*) as cnt FROM shipments
               GROUP BY status ORDER BY cnt DESC"""
        ) as cur:
            status_dist = [dict(r) for r in await cur.fetchall()]

        async with conn.execute(
            """SELECT * FROM shipments
               WHERE date(created_at)=? OR date(shipped_at)=?
               ORDER BY created_at DESC""",
            (today, today),
        ) as cur:
            today_shipments = [dict(r) for r in await cur.fetchall()]

    return {
        "today_orders": today_orders,
        "pending_count": pending_count,
        "shipped_today": shipped_today,
        "status_dist": status_dist,
        "today_shipments": today_shipments,
    }


# ════════════════════════════════════════════════
#  费用核算列表
# ════════════════════════════════════════════════

async def fetch_shipped_shipments() -> list[dict]:
    """获取所有已发货的发货单（用于费用核算）。"""
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT * FROM shipments WHERE status='已发货' ORDER BY shipped_at DESC"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_finance_summary() -> dict:
    """费用汇总统计。"""
    async with get_conn() as conn:
        async with conn.execute(
            """SELECT
                 COUNT(*) as total,
                  COALESCE(SUM(freight_fee), 0) as total_fee,
                 COALESCE(SUM(actual_cost), 0) as total_cost,
                 COALESCE(SUM(profit), 0) as total_profit
               FROM shipments WHERE status='已发货'"""
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else {}


# ════════════════════════════════════════════════
#  规格单重配置
# ════════════════════════════════════════════════

async def get_all_spec_weights() -> list[dict]:
    """获取所有规格单重配置。"""
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT spec, weight_kg FROM spec_weights ORDER BY spec"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def save_spec_weight(spec: str, weight_kg: float) -> None:
    """新增或更新一条规格单重（UPSERT）。"""
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO spec_weights (spec, weight_kg, updated_at)
               VALUES (?, ?, datetime('now','localtime'))
               ON CONFLICT(spec) DO UPDATE SET
                   weight_kg  = excluded.weight_kg,
                   updated_at = excluded.updated_at""",
            (spec.strip(), float(weight_kg)),
        )
        await conn.commit()


async def delete_spec_weight(spec: str) -> None:
    """删除一条规格单重配置。"""
    async with get_conn() as conn:
        await conn.execute(
            "DELETE FROM spec_weights WHERE spec = ?", (spec.strip(),)
        )
        await conn.commit()
