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

async def fetch_all_shipments() -> list[dict]:
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT * FROM shipments ORDER BY created_at DESC"
        ) as cur:
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


async def create_shipment(order_id: str, ship_type: str) -> str | None:
    """
    创建发货单。
    - 整车: 状态=未订车, 生成 driver_token
    - 零单: 状态=待填写
    同时将订单状态更新为 '已派发'。
    """
    order = await get_order_by_id(order_id)
    if not order:
        return None

    status = "未订车" if ship_type == "整车" else "待填写"
    token = uuid.uuid4().hex if ship_type == "整车" else None
    shipment_id = _generate_id("SHIP")

    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO shipments
               (shipment_id, order_id, ship_type, status,
                customer_name, delivery_address, product_name, quantity,
                driver_token)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                shipment_id, order_id, ship_type, status,
                order["customer_name"], order["delivery_address"],
                order["product_name"], order["quantity"],
                token,
            ),
        )
        await conn.execute(
            "UPDATE orders SET status='已派发' WHERE order_id=?",
            (order_id,),
        )
        await conn.commit()
    return shipment_id


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
    logistics_fee: float,
    actual_cost: float,
) -> None:
    """更新费用并自动计算利润。"""
    profit = round(logistics_fee - actual_cost, 2)
    async with get_conn() as conn:
        await conn.execute(
            """UPDATE shipments
               SET logistics_fee=?, actual_cost=?, profit=?
               WHERE shipment_id=?""",
            (logistics_fee, actual_cost, profit, shipment_id),
        )
        await conn.commit()


# ════════════════════════════════════════════════
#  数据看板统计
# ════════════════════════════════════════════════

async def get_dashboard_stats() -> dict:
    """当日数据看板统计。"""
    today = datetime.date.today().isoformat()
    async with get_conn() as conn:
        # 当日新增订单
        async with conn.execute(
            "SELECT COUNT(*) FROM orders WHERE date(created_at)=?", (today,)
        ) as cur:
            today_orders = (await cur.fetchone())[0]

        # 积压未发车
        async with conn.execute(
            """SELECT COUNT(*) FROM shipments
               WHERE status IN ('未订车','已订车','待填写')"""
        ) as cur:
            pending_count = (await cur.fetchone())[0]

        # 当日已发货
        async with conn.execute(
            "SELECT COUNT(*) FROM shipments WHERE status='已发货' AND date(shipped_at)=?",
            (today,),
        ) as cur:
            shipped_today = (await cur.fetchone())[0]

        # 各状态分布
        async with conn.execute(
            """SELECT status, COUNT(*) as cnt FROM shipments
               GROUP BY status ORDER BY cnt DESC"""
        ) as cur:
            status_dist = [dict(r) for r in await cur.fetchall()]

        # 当日发货明细
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
                 COALESCE(SUM(logistics_fee), 0) as total_fee,
                 COALESCE(SUM(actual_cost), 0) as total_cost,
                 COALESCE(SUM(profit), 0) as total_profit
               FROM shipments WHERE status='已发货'"""
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else {}
