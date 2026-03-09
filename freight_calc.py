"""
freight_calc.py — 运费计算独立模块

负责：
  1. 加载并缓存「2025年内表」运价表
  2. 根据省/市/区三级查询目的地单价（元/吨）
  3. 按车型和重量区间套用运费公式
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

# 单价表文件路径（与项目同目录）
_FREIGHT_TABLE_PATH = Path(__file__).parent / "单价表.xlsx"

# 默认包装规格单重（kg/件），可在系统设置中覆盖
DEFAULT_SPEC_WEIGHTS: dict[str, float] = {
    "305ml*12": 6.54,
    "650ml*6":  4.72,
    "650ml*12": 9.25,
    "1L*6":     7.14,
    "750ml*6":  10.0,
    "20L/桶":   21.0,
}


@lru_cache(maxsize=1)
def load_freight_table() -> pd.DataFrame:
    """加载内表到内存（仅首次加载，后续走缓存）。"""
    if not _FREIGHT_TABLE_PATH.exists():
        raise FileNotFoundError(f"未找到单价表文件: {_FREIGHT_TABLE_PATH}")

    df = pd.read_excel(_FREIGHT_TABLE_PATH, dtype=str)
    col_aliases = {
        '区.县': '区县',
        '区/县': '区县',
        '区or县': '区县',
        '运价（元/吨）': '运价',
        '运价(元/吨)': '运价',
        '运价': '运价',
    }
    df = df.rename(columns=col_aliases)
    required = {'省份', '地级市', '区县', '运价'}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"单价表缺少必要列，当前列: {list(df.columns)}")

    df = df[list(required)].copy()

    def _norm_region(v: str) -> str:
        t = str(v or '').strip().replace(' ', '')
        t = t.replace('自治区', '').replace('特别行政区', '').replace('省', '').replace('市', '')
        return t

    # 统一去除空格，防止匹配失败
    for col in ["省份", "地级市", "区县"]:
        df[col] = df[col].map(_norm_region)
    df["运价"] = pd.to_numeric(df["运价"], errors="coerce")
    return df


def lookup_unit_price(
    province: str,
    city: str,
    district: str = "",
) -> Optional[float]:
    """
    从内表中查询目的地运价（元/吨）。

    查询策略（逐级降级）：
      1. 全匹配：省 + 地级市 + 区县
      2. 省 + 地级市（忽略区县）
      3. 省（模糊兜底）
    返回 None 表示未查到，由调用方提示用户手动输入。
    """
    df = load_freight_table()

    def _first(mask: pd.Series) -> Optional[float]:
        rows = df[mask]["运价"].dropna()
        return float(rows.iloc[0]) if not rows.empty else None

    def _norm_region(v: str) -> str:
        return str(v or '').strip().replace(' ', '').replace('自治区', '').replace('特别行政区', '').replace('省', '').replace('市', '')

    province = _norm_region(province)
    city = _norm_region(city)
    district = _norm_region(district)

    # 1. 全匹配
    if district:
        result = _first(
            (df["省份"] == province.strip())
            & (df["地级市"] == city.strip())
            & (df["区县"] == district.strip())
        )
        if result is not None:
            return result

    # 2. 省 + 市
    result = _first(
        (df["省份"] == province.strip())
        & (df["地级市"] == city.strip())
    )
    if result is not None:
        return result

    # 3. 省级兜底
    return _first(df["省份"] == province.strip())


def calc_freight(
    weight_t: float,
    ship_type: str,
    unit_price: float = 0.0,
    delivery_fee: float = 0.0,
) -> float:
    """
    根据运输类型和重量套用计费公式。

    Args:
        weight_t:     货物总重量（吨）
        ship_type:    '整车' | '零单' | '拼车' | '专车'
        unit_price:   零单单价（元/吨），来自内表
        delivery_fee: 送货费（元），手动输入

    Returns:
        运费（元），整车/专车返回 0.0（需调用方手动输入）
    """
    ship_type = ship_type.strip()

    # 整车 / 专车：直接手动输入，不自动计算
    if ship_type in ("整车", "专车"):
        return 0.0

    # 零单 / 拼车：按重量区间套公式
    if ship_type in ("零单", "拼车"):
        if 5.0 <= weight_t < 8.0:
            # 无送货费
            return round(weight_t * unit_price, 2)
        elif 0.8 <= weight_t < 5.0:
            return round(weight_t * unit_price + delivery_fee, 2)
        elif 0.3 <= weight_t < 0.8:
            return round(weight_t * unit_price * 1.2 + delivery_fee, 2)
        else:
            # ≥8t 走专车逻辑，返回0由页面提示
            return 0.0

    return 0.0
