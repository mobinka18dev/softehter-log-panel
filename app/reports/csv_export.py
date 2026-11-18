import csv
from io import StringIO
import codecs
from app.core.jalali import gregorian_to_jalali, format_duration


def generate_csv_report(sessions: list[dict], lang: str = "fa") -> bytes:
    """
    Generate Excel-compatible CSV report with UTF-8 BOM.
    """
    is_fa = (lang == "fa")

    fieldnames = [
        "Row",
        "Username",
        "VirtualHub",
        "SessionID",
        "ClientIP",
        "LoginTime_Gregorian",
        "LoginTime_Jalali",
        "LogoutTime_Gregorian",
        "LogoutTime_Jalali",
        "Duration_Seconds",
        "Duration_Human",
        "Status",
        "StatusReason"
    ]

    if is_fa:
        headers = [
            "ردیف",
            "نام کاربری",
            "هاب مجازی",
            "شناسه نشست",
            "آی‌پی کلاینت",
            "زمان ورود (میلادی)",
            "زمان ورود (شمسی)",
            "زمان خروج (میلادی)",
            "زمان خروج (شمسی)",
            "مدت (ثانیه)",
            "مدت اتصال",
            "وضعیت",
            "علت / توضیحات"
        ]
    else:
        headers = fieldnames

    status_labels = {
        "COMPLETED": "تکمیل‌شده" if is_fa else "Completed",
        "ACTIVE": "در حال اتصال" if is_fa else "Active",
        "INCOMPLETE": "ناقص" if is_fa else "Incomplete"
    }

    buffer = StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)

    for idx, s in enumerate(sessions, 1):
        st_val = s.get("status", "INCOMPLETE")
        status_disp = status_labels.get(st_val, st_val)

        writer.writerow([
            idx,
            s.get("username", ""),
            s.get("virtual_hub", ""),
            s.get("session_id", ""),
            s.get("client_ip", "") or "",
            s.get("login_time", "") or "",
            gregorian_to_jalali(s.get("login_time")) or "",
            s.get("logout_time", "") or "",
            gregorian_to_jalali(s.get("logout_time")) or "",
            s.get("duration_seconds", "") if s.get("duration_seconds") is not None else "",
            format_duration(s.get("duration_seconds"), lang=lang),
            status_disp,
            s.get("status_reason", "") or ""
        ])

    csv_data = buffer.getvalue().encode("utf-8")
    # Prepend UTF-8 BOM so Microsoft Excel automatically recognizes UTF-8 encoding
    return codecs.BOM_UTF8 + csv_data
