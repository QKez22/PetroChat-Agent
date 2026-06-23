"""工具单元测试（纯逻辑，不依赖外部服务）。"""

from __future__ import annotations

import re

from petrochat.app.tools import convert_unit


def _num(s: str) -> float:
    """从结果字符串里抽第一个 = 之后的数字。"""
    m = re.search(r"=\s*([-\d.]+)", s)
    assert m, f"无法从结果中抽数字: {s}"
    return float(m.group(1))


def test_convert_pressure_mpa_to_psi() -> None:
    r = convert_unit.invoke({"value": 1.0, "from_unit": "MPa", "to_unit": "psi"})
    assert abs(_num(r) - 145.038) < 0.5


def test_convert_temperature_c_to_k() -> None:
    r = convert_unit.invoke({"value": 25, "from_unit": "celsius", "to_unit": "K"})
    assert abs(_num(r) - 298.15) < 0.01


def test_convert_temperature_f_to_c() -> None:
    r = convert_unit.invoke({"value": 100, "from_unit": "fahrenheit", "to_unit": "celsius"})
    assert abs(_num(r) - 37.78) < 0.1


def test_convert_length_inch_to_mm() -> None:
    r = convert_unit.invoke({"value": 1.0, "from_unit": "inch", "to_unit": "mm"})
    assert abs(_num(r) - 25.4) < 0.01


def test_convert_unsupported_unit() -> None:
    r = convert_unit.invoke({"value": 1, "from_unit": "MPa", "to_unit": "meter"})
    assert "无法换算" in r or "不被支持" in r


def test_convert_unit_case_insensitive() -> None:
    a = convert_unit.invoke({"value": 1.0, "from_unit": "mpa", "to_unit": "PSI"})
    b = convert_unit.invoke({"value": 1.0, "from_unit": "MPa", "to_unit": "psi"})
    assert abs(_num(a) - _num(b)) < 1e-6
