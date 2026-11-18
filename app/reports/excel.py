from io import BytesIO
from datetime import datetime, timezone
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from app.core.jalali import gregorian_to_jalali, format_duration


def generate_excel_report(
    sessions: list[dict],
    summary: dict,
    filter_username: str | None = None,
    filter_hub: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    lang: str = "fa"
) -> bytes:
    """
    Generate professional multi-sheet Excel report with openpyxl.
    """
    wb = openpyxl.Workbook()

    # Styling definitions
    font_family = "Tahoma"
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")  # Slate 800
    sub_fill = PatternFill(start_color="334155", end_color="334155", fill_type="solid")     # Slate 700
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")   # Slate 50
    header_font = Font(name=font_family, size=11, bold=True, color="FFFFFF")
    title_font = Font(name=font_family, size=14, bold=True, color="FFFFFF")
    bold_font = Font(name=font_family, size=10, bold=True, color="0F172A")
    regular_font = Font(name=font_family, size=10, color="1E293B")
    
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    is_fa = (lang == "fa")

    # -------------------------------------------------------------
    # Sheet 1: Summary Sheet
    # -------------------------------------------------------------
    ws_summary = wb.active
    ws_summary.title = "خلاصه گزارش" if is_fa else "Report Summary"
    ws_summary.views.sheetView[0].rightToLeft = is_fa

    # Title Banner
    title_text = "گزارش اتصالات و نشست‌های SoftEther VPN" if is_fa else "SoftEther VPN Connection Report"
    ws_summary.merge_cells("A1:D2")
    title_cell = ws_summary["A1"]
    title_cell.value = title_text
    title_cell.font = title_font
    title_cell.fill = header_fill
    title_cell.alignment = Alignment(horizontal="center", vertical="center")

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    now_j = gregorian_to_jalali(now_utc)

    summary_rows = [
        ("فیلتر کاربر" if is_fa else "Username Filter", filter_username or ("همه کاربران" if is_fa else "All Users")),
        ("فیلتر هاب مجازی" if is_fa else "Virtual Hub Filter", filter_hub or ("همه هاب‌ها" if is_fa else "All Hubs")),
        ("از تاریخ" if is_fa else "Date From", f"{date_from or '-'} (شمسی: {gregorian_to_jalali(date_from) if date_from else '-'})"),
        ("تا تاریخ" if is_fa else "Date To", f"{date_to or '-'} (شمسی: {gregorian_to_jalali(date_to) if date_to else '-'})"),
        ("زمان تولید گزارش" if is_fa else "Generated At", f"{now_utc} (شمسی: {now_j})"),
        ("", ""),
        ("تعداد کل نشست‌ها" if is_fa else "Total Sessions", summary.get("total_sessions", 0)),
        ("تعداد نشست‌های تکمیل‌شده" if is_fa else "Completed Sessions", summary.get("completed_sessions", 0)),
        ("تعداد نشست‌های فعال" if is_fa else "Active Sessions", summary.get("active_sessions", 0)),
        ("تعداد نشست‌های ناقص" if is_fa else "Incomplete Sessions", summary.get("incomplete_sessions", 0)),
        ("مجموع مدت زمان اتصال تایید شده" if is_fa else "Total Confirmed Duration", format_duration(summary.get("total_duration_seconds", 0), lang=lang)),
        ("میانگین مدت اتصال" if is_fa else "Average Duration", format_duration(summary.get("avg_duration_seconds", 0), lang=lang)),
        ("طولانی‌ترین نشست" if is_fa else "Longest Session", format_duration(summary.get("max_duration_seconds", 0), lang=lang)),
        ("اولین ورود ثبت‌شده" if is_fa else "First Login", f"{summary.get('first_login') or '-'} (شمسی: {gregorian_to_jalali(summary.get('first_login')) if summary.get('first_login') else '-'})"),
        ("آخرین خروج ثبت‌شده" if is_fa else "Last Logout", f"{summary.get('last_logout') or '-'} (شمسی: {gregorian_to_jalali(summary.get('last_logout')) if summary.get('last_logout') else '-'})"),
    ]

    r = 4
    for label, val in summary_rows:
        if not label:
            r += 1
            continue
        c1 = ws_summary.cell(row=r, column=1, value=label)
        c2 = ws_summary.cell(row=r, column=2, value=str(val))
        c1.font = bold_font
        c2.font = regular_font
        c1.fill = zebra_fill
        c1.border = thin_border
        c2.border = thin_border
        c1.alignment = Alignment(horizontal="right" if is_fa else "left", vertical="center")
        c2.alignment = Alignment(horizontal="right" if is_fa else "left", vertical="center")
        r += 1

    ws_summary.column_dimensions['A'].width = 32
    ws_summary.column_dimensions['B'].width = 45

    # -------------------------------------------------------------
    # Sheet 2: Detailed Sessions Sheet
    # -------------------------------------------------------------
    ws_detail = wb.create_sheet(title="جزئیات نشست‌ها" if is_fa else "Session Details")
    ws_detail.views.sheetView[0].rightToLeft = is_fa

    headers = [
        "ردیف" if is_fa else "#",
        "نام کاربری" if is_fa else "Username",
        "هاب مجازی" if is_fa else "Virtual Hub",
        "شناسه نشست" if is_fa else "Session ID",
        "آی‌پی کلاینت" if is_fa else "Client IP",
        "زمان ورود (میلادی)" if is_fa else "Login (Gregorian)",
        "زمان ورود (شمسی)" if is_fa else "Login (Jalali)",
        "زمان خروج (میلادی)" if is_fa else "Logout (Gregorian)",
        "زمان خروج (شمسی)" if is_fa else "Logout (Jalali)",
        "مدت اتصال" if is_fa else "Duration",
        "وضعیت" if is_fa else "Status",
        "توضیحات / علت" if is_fa else "Status Reason"
    ]

    for col_idx, h_text in enumerate(headers, 1):
        cell = ws_detail.cell(row=1, column=col_idx, value=h_text)
        cell.font = header_font
        cell.fill = sub_fill
        cell.border = thin_border
        cell.alignment = Alignment(horizontal="center", vertical="center")

    ws_detail.row_dimensions[1].height = 26

    status_labels = {
        "COMPLETED": "تکمیل‌شده" if is_fa else "Completed",
        "ACTIVE": "در حال اتصال (فعال)" if is_fa else "Active",
        "INCOMPLETE": "ناقص / قطع ناگهانی" if is_fa else "Incomplete"
    }

    for idx, s in enumerate(sessions, 1):
        row_num = idx + 1
        st_val = s.get("status", "INCOMPLETE")
        status_disp = status_labels.get(st_val, st_val)

        row_data = [
            idx,
            s.get("username", ""),
            s.get("virtual_hub", ""),
            s.get("session_id", ""),
            s.get("client_ip", "-") or "-",
            s.get("login_time", "-") or "-",
            gregorian_to_jalali(s.get("login_time")) or "-",
            s.get("logout_time", "-") or "-",
            gregorian_to_jalali(s.get("logout_time")) or "-",
            format_duration(s.get("duration_seconds"), lang=lang),
            status_disp,
            s.get("status_reason", "") or ""
        ]

        is_even = (idx % 2 == 0)
        for c_idx, val in enumerate(row_data, 1):
            c = ws_detail.cell(row=row_num, column=c_idx, value=val)
            c.font = regular_font
            c.border = thin_border
            if is_even:
                c.fill = zebra_fill
            
            # Alignments: numbers and IDs LTR/center, text RTL
            if c_idx in [1, 3, 4, 5, 6, 8]:
                c.alignment = Alignment(horizontal="center", vertical="center")
            else:
                c.alignment = Alignment(horizontal="right" if is_fa else "left", vertical="center")

        ws_detail.row_dimensions[row_num].height = 20

    # Auto-adjust column widths
    for col in ws_detail.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws_detail.column_dimensions[col_letter].width = max(max_len + 4, 12)

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()
