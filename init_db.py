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

    # ── 动态添加扩展字段 ──
    _add_columns = [
        ("pickup_method",       "TEXT DEFAULT '送货上门'"),
        ("payment_method",      "TEXT DEFAULT '现付'"),
        ("freight_fee",         "REAL DEFAULT 0"),
        ("delivery_fee",        "REAL DEFAULT 0"),
        ("total_weight",        "REAL DEFAULT 0"),
        ("unit_price",          "REAL DEFAULT 0"),
        ("actual_unit_price",   "REAL DEFAULT 0"),
        ("actual_delivery_fee", "REAL DEFAULT 0"),
        ("customer_phone",      "TEXT DEFAULT ''"),   # 收货人电话
        ("logistics_provider",  "TEXT DEFAULT ''"),   # 后置分配物流公司/承运方式
        ("receiver_province",   "TEXT DEFAULT ''"),
        ("receiver_city",       "TEXT DEFAULT ''"),
        ("receiver_district",   "TEXT DEFAULT ''"),
    ]
    for col_name, col_def in _add_columns:
        try:
            cur.execute(f"ALTER TABLE shipments ADD COLUMN {col_name} {col_def}")
        except sqlite3.OperationalError:
            pass  # 字段已存在

    # ── 商品明细子表 ──
    cur.execute("""
    CREATE TABLE IF NOT EXISTS shipment_products (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        shipment_id  TEXT NOT NULL,
        product_name TEXT,
        spec         TEXT,
        quantity     INTEGER DEFAULT 0,
        parsed_spec  TEXT DEFAULT '',
        unit_weight_kg REAL DEFAULT 0,
        line_weight_kg REAL DEFAULT 0,
        weight_source TEXT DEFAULT 'manual_input',
        weight_locked INTEGER DEFAULT 0,
        raw_data     TEXT DEFAULT '{}',
        FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id)
    )
    """)
    # ── 动态补列（兼容旧数据库缺少 raw_data 的情况）──
    try:
        cur.execute("ALTER TABLE shipment_products ADD COLUMN raw_data TEXT DEFAULT '{}'")
    except sqlite3.OperationalError:
        pass  # 列已存在，忽略
    for col_name, col_def in [
        ("parsed_spec", "TEXT DEFAULT ''"),
        ("unit_weight_kg", "REAL DEFAULT 0"),
        ("line_weight_kg", "REAL DEFAULT 0"),
        ("weight_source", "TEXT DEFAULT 'manual_input'"),
        ("weight_locked", "INTEGER DEFAULT 0"),
    ]:
        try:
            cur.execute(f"ALTER TABLE shipment_products ADD COLUMN {col_name} {col_def}")
        except sqlite3.OperationalError:
            pass

    # ── 商品明细重量修改留痕 ──
    cur.execute("""
    CREATE TABLE IF NOT EXISTS shipment_weight_logs (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        shipment_id       TEXT NOT NULL,
        product_row_id    INTEGER,
        old_unit_weight_kg REAL DEFAULT 0,
        new_unit_weight_kg REAL DEFAULT 0,
        old_line_weight_kg REAL DEFAULT 0,
        new_line_weight_kg REAL DEFAULT 0,
        operator          TEXT DEFAULT 'system',
        note              TEXT DEFAULT '',
        created_at        DATETIME DEFAULT (datetime('now','localtime'))
    )
    """)

    # ── 系统配置表（键值存储） ──
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key         TEXT PRIMARY KEY,
        value       TEXT,
        updated_at  DATETIME DEFAULT (datetime('now','localtime'))
    )
    """)

    # ── 规格单重配置表 ──
    cur.execute("""
    CREATE TABLE IF NOT EXISTS spec_weights (
        spec        TEXT PRIMARY KEY,
        weight_kg   REAL NOT NULL,
        updated_at  DATETIME DEFAULT (datetime('now','localtime'))
    )
    """)
    # 预插入默认规格（忽略已存在的记录）
    default_specs = [
        ("305ml*12", 6.54),
        ("650ml*6",  4.72),
        ("650ml*12", 9.25),
        ("1L*6",     7.14),
        ("750ml*6",  10.0),
        ("20L/桶",   21.0),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO spec_weights (spec, weight_kg) VALUES (?, ?)",
        default_specs,
    )

    # ── 回填：把没有子表记录的历史发货单的 product_name/quantity 写入子表 ──
    cur.execute("""
        SELECT s.shipment_id, s.product_name, s.quantity
        FROM shipments s
        WHERE s.product_name IS NOT NULL AND s.product_name != ''
          AND NOT EXISTS (
              SELECT 1 FROM shipment_products sp WHERE sp.shipment_id = s.shipment_id
          )
    """)
    backfill_rows = cur.fetchall()
    if backfill_rows:
        cur.executemany(
            "INSERT INTO shipment_products (shipment_id, product_name, spec, quantity, raw_data) VALUES (?, ?, '', ?, '{}')",
            [(r[0], r[1], r[2] or 0) for r in backfill_rows],
        )
        print(f"[init_db] 回填了 {len(backfill_rows)} 条历史发货单的商品明细。")

    conn.commit()
    conn.close()
    print(f"[init_db] 数据库 '{DB_PATH}' 结构已就绪。")


if __name__ == "__main__":
    init_db()
