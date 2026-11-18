import pytest
from io import BytesIO
import openpyxl
from app.reports.excel import generate_excel_report
from app.reports.csv_export import generate_csv_report


@pytest.fixture
def sample_report_data():
    sessions = [
        {
            "username": "synth_alice",
            "virtual_hub": "DEFAULT",
            "session_id": "SID-SYNTH_ALICE-1",
            "client_ip": "198.51.100.10",
            "login_time": "2026-11-15 08:10:00",
            "logout_time": "2026-11-15 09:30:00",
            "duration_seconds": 4800,
            "status": "COMPLETED",
            "status_reason": None
        },
        {
            "username": "synth_bob",
            "virtual_hub": "DEFAULT",
            "session_id": "SID-SYNTH_BOB-1",
            "client_ip": "203.0.113.25",
            "login_time": "2026-11-15 10:00:00",
            "logout_time": None,
            "duration_seconds": None,
            "status": "ACTIVE",
            "status_reason": "In progress"
        }
    ]
    summary = {
        "total_sessions": 2,
        "completed_sessions": 1,
        "active_sessions": 1,
        "incomplete_sessions": 0,
        "total_duration_seconds": 4800,
        "avg_duration_seconds": 4800,
        "max_duration_seconds": 4800,
        "first_login": "2026-11-15 08:10:00",
        "last_logout": "2026-11-15 09:30:00"
    }
    return sessions, summary


def test_excel_export_generation(sample_report_data):
    sessions, summary = sample_report_data
    excel_bytes = generate_excel_report(
        sessions=sessions,
        summary=summary,
        filter_username="synth_alice",
        filter_hub="DEFAULT",
        lang="fa"
    )

    assert excel_bytes is not None
    assert len(excel_bytes) > 0

    # Load and verify with openpyxl
    wb = openpyxl.load_workbook(BytesIO(excel_bytes))
    assert len(wb.sheetnames) == 2
    assert "خلاصه گزارش" in wb.sheetnames
    assert "جزئیات نشست‌ها" in wb.sheetnames

    ws_detail = wb["جزئیات نشست‌ها"]
    assert ws_detail.max_row == 3  # Header + 2 data rows


def test_csv_export_generation(sample_report_data):
    sessions, _ = sample_report_data
    csv_bytes = generate_csv_report(sessions=sessions, lang="fa")

    assert csv_bytes is not None
    # Check UTF-8 BOM
    assert csv_bytes.startswith(b'\xef\xbb\xbf')
    
    text = csv_bytes.decode("utf-8")
    assert "synth_alice" in text
    assert "SID-SYNTH_ALICE-1" in text
