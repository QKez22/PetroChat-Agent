"""单位换算工具：石化领域常用。

为什么用查表式实现而不是 pint 库：
1. 学习目的明显（看得见每个转换关系）
2. 依赖更轻
3. 错误提示完全可控
4. 石化场景的单位有限（压力/温度/流量/长度/重量），手维护表完全够用

LLM 调用方式：
  convert_unit(value=1.0, from_unit="MPa", to_unit="psi")
"""

from __future__ import annotations

from langchain_core.tools import tool

# ============================================================
# 转换工厂：维度 → {单位: 到该维度"基准单位"的换算系数}
# 设计：以国际单位为基准（MPa, K, m, m3, kg, m3/h），通过 to_base/from_base 互换
# ============================================================

# 压力（基准：MPa）
_PRESSURE = {
    "Pa":   1e-6,
    "kPa":  1e-3,
    "MPa":  1.0,
    "bar":  0.1,
    "atm":  0.101325,
    "psi":  0.00689476,
    "mmHg": 0.000133322,
}

# 温度（特殊：不是线性比例，用回调）
def _temp_to_K(v: float, unit: str) -> float:
    u = unit.lower()
    if u in ("k", "kelvin"):
        return v
    if u in ("c", "celsius", "°c", "℃"):
        return v + 273.15
    if u in ("f", "fahrenheit", "°f", "℉"):
        return (v - 32) * 5 / 9 + 273.15
    raise ValueError(f"未知温度单位: {unit}")


def _temp_from_K(v: float, unit: str) -> float:
    u = unit.lower()
    if u in ("k", "kelvin"):
        return v
    if u in ("c", "celsius", "°c", "℃"):
        return v - 273.15
    if u in ("f", "fahrenheit", "°f", "℉"):
        return (v - 273.15) * 9 / 5 + 32
    raise ValueError(f"未知温度单位: {unit}")


# 流量（基准：m³/h）
_FLOW = {
    "m3/h":  1.0,
    "m³/h":  1.0,
    "L/s":   3.6,
    "L/min": 0.06,
    "L/h":   0.001,
    "kg/h":  0.001,  # 仅水近似（实际依赖密度，这里给警示性近似）
}

# 长度（基准：m）
_LENGTH = {
    "m":     1.0,
    "mm":    0.001,
    "cm":    0.01,
    "km":    1000.0,
    "inch":  0.0254,
    "in":    0.0254,
    "ft":    0.3048,
}

# 重量（基准：kg）
_MASS = {
    "kg":    1.0,
    "g":     0.001,
    "mg":    1e-6,
    "ton":   1000.0,
    "t":     1000.0,
    "lb":    0.453592,
    "oz":    0.0283495,
}

# 体积（基准：m³）
_VOLUME = {
    "m3":    1.0,
    "m³":    1.0,
    "L":     0.001,
    "mL":    1e-6,
    "gallon": 0.00378541,
    "gal":   0.00378541,
}


def _try_linear(value: float, from_u: str, to_u: str, table: dict[str, float]) -> float | None:
    """若两单位都在表里，按 (value × from_factor / to_factor) 换算。"""
    fk = next((k for k in table if k.lower() == from_u.lower()), None)
    tk = next((k for k in table if k.lower() == to_u.lower()), None)
    if fk and tk:
        return value * table[fk] / table[tk]
    return None


@tool
def convert_unit(value: float, from_unit: str, to_unit: str) -> str:
    """石化领域常用单位换算。

    支持的维度（输入单位需在同一维度内）：
      - 压力: Pa, kPa, MPa, bar, atm, psi, mmHg
      - 温度: K, celsius/°C, fahrenheit/°F
      - 流量: m3/h, L/s, L/min, L/h, kg/h(仅水近似)
      - 长度: m, mm, cm, km, inch, ft
      - 重量: kg, g, mg, ton/t, lb, oz
      - 体积: m3/m³, L, mL, gallon

    Args:
        value: 要换算的数值（如 1.0）
        from_unit: 源单位（如 "MPa"）
        to_unit:   目标单位（如 "psi"）

    Returns:
        换算结果的可读字符串，含原值和目标值。

    Examples:
        convert_unit(1.0, "MPa", "psi")   → "1.0 MPa = 145.04 psi"
        convert_unit(25, "celsius", "K")  → "25 celsius = 298.15 K"
    """
    # 温度走专用回调（非线性）
    if from_unit.lower() in ("k", "kelvin", "c", "celsius", "°c", "℃", "f", "fahrenheit", "°f", "℉"):
        try:
            kelvin = _temp_to_K(value, from_unit)
            result = _temp_from_K(kelvin, to_unit)
            return f"{value} {from_unit} = {result:.6g} {to_unit}"
        except ValueError as e:
            return f"温度换算失败: {e}"

    # 线性单位逐表试
    for table, name in [
        (_PRESSURE, "压力"),
        (_FLOW, "流量"),
        (_LENGTH, "长度"),
        (_MASS, "重量"),
        (_VOLUME, "体积"),
    ]:
        r = _try_linear(value, from_unit, to_unit, table)
        if r is not None:
            return f"{value} {from_unit} = {r:.6g} {to_unit}（{name}）"

    return (f"无法换算 '{from_unit}' → '{to_unit}'：单位不在同一维度内或不被支持。"
            f"支持的维度：压力/温度/流量/长度/重量/体积。")
