"""Direction-aware hard-rule tests — SHORT eligibility, leverage cap, geometry."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from guardian.validators.hard_rules import (
    check_leverage_cap,
    check_short_eligibility,
    check_sl_tp_geometry,
)


SHORTABLE_PAIRS = {
    "XXBTZUSD": {
        "altname": "XBTUSD",
        "wsname": "XBT/USD",
        "leverage_buy": [2, 3, 4, 5],
        "leverage_sell": [2, 3, 4, 5],
    },
    "XETHZUSD": {
        "altname": "ETHUSD",
        "wsname": "ETH/USD",
        "leverage_buy": [2, 3, 4, 5],
        "leverage_sell": [2, 3],
    },
    "ADAUSD": {
        "altname": "ADAUSD",
        "wsname": "ADA/USD",
        "leverage_buy": [2, 3],
        "leverage_sell": [],   # NOT shortable
    },
}


# --- SHORT eligibility ---

def test_short_eligibility_passes_for_shortable():
    sig = {"direction": "SHORT", "pair": "XBT/USD"}
    res = check_short_eligibility(sig, SHORTABLE_PAIRS)
    assert res.passed is True


def test_short_eligibility_rejects_non_shortable():
    sig = {"direction": "SHORT", "pair": "ADA/USD"}
    res = check_short_eligibility(sig, SHORTABLE_PAIRS)
    assert res.passed is False
    assert "not margin-eligible" in res.reason or "not shortable" in res.reason or "leverage_sell" in res.reason


def test_short_eligibility_rejects_unknown_pair():
    sig = {"direction": "SHORT", "pair": "UNKNOWN/USD"}
    res = check_short_eligibility(sig, SHORTABLE_PAIRS)
    assert res.passed is False
    assert "AssetPairs" in res.reason


def test_short_eligibility_skipped_for_long():
    sig = {"direction": "LONG", "pair": "ADA/USD"}
    res = check_short_eligibility(sig, SHORTABLE_PAIRS)
    assert res.passed is True


# --- leverage cap ---

def test_leverage_cap_within_limits():
    settings = SimpleNamespace(max_leverage=5)
    sig = {"direction": "LONG", "pair": "XBT/USD", "leverage": 3}
    res = check_leverage_cap(sig, settings, SHORTABLE_PAIRS["XXBTZUSD"])
    assert res.passed is True


def test_leverage_cap_exceeds_max_setting():
    settings = SimpleNamespace(max_leverage=3)
    sig = {"direction": "LONG", "pair": "XBT/USD", "leverage": 5}
    res = check_leverage_cap(sig, settings, SHORTABLE_PAIRS["XXBTZUSD"])
    assert res.passed is False
    assert "exceeds cap" in res.reason


def test_leverage_cap_exceeds_pair_max():
    """ETH leverage_sell tops out at 3 — request 5 must be rejected."""
    settings = SimpleNamespace(max_leverage=5)
    sig = {"direction": "SHORT", "pair": "ETH/USD", "leverage": 5}
    res = check_leverage_cap(sig, settings, SHORTABLE_PAIRS["XETHZUSD"])
    assert res.passed is False


def test_leverage_cap_short_on_non_shortable_pair():
    """Even before SHORT eligibility check — pair has empty leverage_sell."""
    settings = SimpleNamespace(max_leverage=5)
    sig = {"direction": "SHORT", "pair": "ADA/USD", "leverage": 2}
    res = check_leverage_cap(sig, settings, SHORTABLE_PAIRS["ADAUSD"])
    assert res.passed is False


def test_leverage_cap_zero_or_negative_rejected():
    settings = SimpleNamespace(max_leverage=5)
    sig = {"direction": "LONG", "pair": "XBT/USD", "leverage": 0}
    res = check_leverage_cap(sig, settings, SHORTABLE_PAIRS["XXBTZUSD"])
    assert res.passed is False


def test_leverage_cap_no_leverage_field_passes():
    settings = SimpleNamespace(max_leverage=5)
    sig = {"direction": "LONG", "pair": "XBT/USD"}
    res = check_leverage_cap(sig, settings, SHORTABLE_PAIRS["XXBTZUSD"])
    assert res.passed is True


# --- SL/TP geometry ---

def test_geometry_long_correct():
    sig = {"direction": "LONG", "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 110.0}
    res = check_sl_tp_geometry(sig)
    assert res.passed is True


def test_geometry_long_inverted_stop_above_entry():
    sig = {"direction": "LONG", "entry_price": 100.0, "stop_loss": 105.0, "take_profit": 110.0}
    res = check_sl_tp_geometry(sig)
    assert res.passed is False


def test_geometry_long_tp_below_entry():
    sig = {"direction": "LONG", "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 90.0}
    res = check_sl_tp_geometry(sig)
    assert res.passed is False


def test_geometry_short_correct():
    sig = {"direction": "SHORT", "entry_price": 100.0, "stop_loss": 105.0, "take_profit": 90.0}
    res = check_sl_tp_geometry(sig)
    assert res.passed is True


def test_geometry_short_inverted():
    """SHORT with LONG-style geometry must fail."""
    sig = {"direction": "SHORT", "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 110.0}
    res = check_sl_tp_geometry(sig)
    assert res.passed is False


def test_geometry_missing_fields_skipped():
    sig = {"direction": "LONG", "entry_price": 100.0}
    res = check_sl_tp_geometry(sig)
    assert res.passed is True
    assert "missing" in res.reason or "skipped" in res.reason


def test_geometry_unknown_direction():
    sig = {"direction": "WAT", "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 110.0}
    res = check_sl_tp_geometry(sig)
    assert res.passed is False
