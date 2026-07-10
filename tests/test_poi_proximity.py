"""Tests for OB/FVG 0.3% proximity tolerance."""

from app.analysis.poi_proximity import near_zone
from app.analysis.pro.conditions import evaluate_fvg, evaluate_order_block


def test_near_zone_inside():
    assert near_zone(110.0, 109.0, 111.0) is True


def test_near_zone_below_boundary_within_tolerance():
    # 0.28% below 109.0
    assert near_zone(108.695, 109.0, 111.0) is True


def test_near_zone_above_boundary_within_tolerance():
    # 0.28% above 111.0
    assert near_zone(111.31, 109.0, 111.0) is True


def test_near_zone_outside_tolerance():
    assert near_zone(108.0, 109.0, 111.0) is False


def test_evaluate_fvg_proximity_message():
    fvg = {"type": "BEARISH", "top": 100.0, "bottom": 98.0}
    result = evaluate_fvg(fvg, 100.25, weight=12)
    assert result.aligned is True
    assert result.direction == "SHORT"
