from datetime import datetime, date, time, timedelta
import re
import jdatetime


def gregorian_to_jalali(dt_or_str: datetime | str | None, fmt: str = "%Y/%m/%d %H:%M:%S") -> str:
    """Convert a Gregorian datetime object or ISO string to a Jalali formatted string."""
    if not dt_or_str:
        return ""
    
    if isinstance(dt_or_str, str):
        # Handle string like '2026-11-18 14:23:01.456' or '2026-11-18T14:23:01' or '2026-11-18'
        clean_str = dt_or_str.replace("T", " ")
        try:
            if "." in clean_str:
                clean_str = clean_str.split(".")[0]
            if len(clean_str) == 10:
                dt = datetime.strptime(clean_str, "%Y-%m-%d")
            else:
                dt = datetime.strptime(clean_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return dt_or_str
    else:
        dt = dt_or_str

    try:
        jdt = jdatetime.datetime.fromgregorian(datetime=dt)
        return jdt.strftime(fmt)
    except Exception:
        return str(dt_or_str)


def jalali_to_gregorian_dt(jalali_str: str, is_end_of_day: bool = False) -> datetime:
    """
    Parse a Jalali date string (e.g. 1403/08/28 or 1403-08-28) into a Gregorian datetime.
    If is_end_of_day is True, time is set to 23:59:59.
    """
    # Extract digits
    match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", jalali_str.strip())
    if not match:
        raise ValueError(f"Invalid Jalali date format: '{jalali_str}'. Expected YYYY/MM/DD")
    
    jy, jm, jd = int(match.group(1)), int(match.group(2)), int(match.group(3))
    
    t = time(23, 59, 59) if is_end_of_day else time(0, 0, 0)
    
    # Check for optional time component
    time_match = re.search(r"(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?", jalali_str.strip())
    if time_match:
        th = int(time_match.group(1))
        tm = int(time_match.group(2))
        ts = int(time_match.group(3) or 0)
        t = time(th, tm, ts)
    
    jdt = jdatetime.datetime(jy, jm, jd, t.hour, t.minute, t.second)
    return jdt.togregorian()


def parse_filter_date(date_input: str | None, is_end_of_day: bool = False) -> str | None:
    """
    Accepts either Jalali (1403/xx/xx) or Gregorian (2026-xx-xx) string,
    and returns a normalized Gregorian string in 'YYYY-MM-DD HH:MM:SS' format.
    """
    if not date_input or not date_input.strip():
        return None
    
    text = date_input.strip()
    
    # Check if it starts with Jalali year (e.g. 13xx or 14xx)
    first_part = re.split(r"[/\-T ]", text)[0]
    if first_part.isdigit() and 1300 <= int(first_part) <= 1500:
        gdt = jalali_to_gregorian_dt(text, is_end_of_day=is_end_of_day)
        return gdt.strftime("%Y-%m-%d %H:%M:%S")
    
    # Otherwise treat as Gregorian
    clean = text.replace("T", " ")
    time_part = " 23:59:59" if is_end_of_day else " 00:00:00"
    
    if len(clean) == 10:
        return f"{clean}{time_part}"
    
    try:
        # If it has milliseconds, truncate or parse
        if "." in clean:
            clean = clean.split(".")[0]
        dt = datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return f"{clean[:10]}{time_part}"


def format_duration(seconds: int | None, lang: str = "fa") -> str:
    """Format duration in seconds to human-readable string."""
    if seconds is None or seconds < 0:
        return "-" if lang == "en" else "نامشخص"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if lang == "fa":
        parts = []
        if hours > 0:
            parts.append(f"{hours} ساعت")
        if minutes > 0:
            parts.append(f"{minutes} دقیقه")
        if secs > 0 or not parts:
            parts.append(f"{secs} ثانیه")
        return " و ".join(parts)
    else:
        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")
        return " ".join(parts)


def format_bytes(num_bytes: int | None) -> str:
    """Format bytes to human readable string (KB, MB, GB)."""
    if num_bytes is None or num_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    val = float(num_bytes)
    idx = 0
    while val >= 1024.0 and idx < len(units) - 1:
        val /= 1024.0
        idx += 1
    return f"{val:.1f} {units[idx]}"
