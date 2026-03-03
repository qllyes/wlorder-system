"""
数据库初始化模块 — 幂等建表。
支持重复调用，仅在表不存在时创建。
"""
import sqlite3
from pathlib import Path

DB_PATH: str = str(Path(__file__).parent / "logistics.db")


def init_db() -> None:
    """初始化数据库，确保所有表结构存在（幂等操作）。"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ── 客户订单表 ──
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id         TEXT PRIMARY KEY,
        customer_name    TEXT NOT NULL,
        product_name     TEXT NOT NULL,
        quantity         INTEGER NOT NULL,
        delivery_address TEXT,
        status           TEXT NOT NULL DEFAULT '待发货',
        created_at       DATETIME DEFAULT (datetime('now','localtime'))
    )
    """)

    # ── 发货单表 ──
    cur.execute("""
    CREATE TABLE IF NOT EXISTS shipments (
        shipment_id          TEXT PRIMARY KEY,
        order_id             TEXT NOT NULL,
        ship_type            TEXT NOT NULL,
        status               TEXT NOT NULL,

        /* 订单快照（冗余存储，解耦 JOIN） */
        customer_name        TEXT,
        delivery_address     TEXT,
        product_name         TEXT,
        quantity             INTEGER,

        /* 整车司机信息（司机扫码填报） */
        driver_name          TEXT,
        driver_id_card       TEXT,
        driver_phone         TEXT,
        truck_plate          TEXT,
        truck_type           TEXT,
        driver_token         TEXT,

        /* 零单第三方物流信息 */
        third_party_company  TEXT,
        third_party_tracking TEXT,

        /* 零单合单批次 */
        batch_id             TEXT,

        /* 财务核算 */
        logistics_fee        REAL DEFAULT 0,
        actual_cost          REAL DEFAULT 0,
        profit               REAL DEFAULT 0,

        created_at           DATETIME DEFAULT (datetime('now','localtime')),
        shipped_at           DATETIME,
        remarks              TEXT
    )
    """)

    conn.commit()
    conn.close()
    print(f"[init_db] 数据库 '{DB_PATH}' 结构已就绪。")


if __name__ == "__main__":
    init_db()
