import pytest
from datetime import datetime
from app.core.jalali import (
    gregorian_to_jalali,
    jalali_to_gregorian_dt,
    parse_filter_date,
    format_duration,
    format_bytes
)


def test_gregorian_to_jalali():
    # 2026-11-18 is 1405-08-27 in Jalali calendar
    g_str = "2026-11-18 12:00:00"
    j_str = gregorian_to_jalali(g_str, fmt="%Y/%m/%d")
    assert j_str == "1405/08/27"


def test_jalali_to_gregorian():
    j_str = "1405/08/27"
    g_dt = jalali_to_gregorian_dt(j_str, is_end_of_day=False)
    assert g_dt.year == 2026
    assert g_dt.month == 11
    assert g_dt.day == 18
    assert g_dt.hour == 0 and g_dt.minute == 0 and g_dt.second == 0

    # End of day test
    g_dt_eod = jalali_to_gregorian_dt(j_str, is_end_of_day=True)
    assert g_dt_eod.hour == 23 and g_dt_eod.minute == 59 and g_dt_eod.second == 59


def test_parse_filter_date():
    # Jalali input start
    p1 = parse_filter_date("1405/08/27", is_end_of_day=False)
    assert p1 == "2026-11-18 00:00:00"

    # Jalali input end-of-day
    p2 = parse_filter_date("1405/08/27", is_end_of_day=True)
    assert p2 == "2026-11-18 23:59:59"

    # Gregorian input start
    p3 = parse_filter_date("2026-11-18", is_end_of_day=False)
    assert p3 == "2026-11-18 00:00:00"

    # Gregorian input end-of-day
    p4 = parse_filter_date("2026-11-18", is_end_of_day=True)
    assert p4 == "2026-11-18 23:59:59"


def test_format_duration():
    assert format_duration(3665, lang="fa") == "1 ساعت و 1 دقیقه و 5 ثانیه"
    assert format_duration(3665, lang="en") == "1h 1m 5s"
    assert format_duration(0, lang="fa") == "0 ثانیه"
    assert format_duration(None, lang="fa") == "نامشخص"


def test_format_bytes():
    assert format_bytes(500) == "500.0 B"
    assert format_bytes(1048576) == "1.0 MB"
    assert format_bytes(1073741824) == "1.0 GB"
