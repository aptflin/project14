"""規格 3.1–3.2：時段字串、索引與活動時間換算。"""
from datetime import time
import re

from .result import Slot

PERIODS = tuple("123456789abc")
DAYS = "一二三四五六日"


def parse_slot(text: str) -> Slot:
    """解析星期-節次；回傳 (星期, 0–11 索引)，非法時拋出 ValueError。"""
    if not isinstance(text, str) or not re.fullmatch(r"[1-7]-[1-9abc]", text.strip().lower()):
        raise ValueError(f"時段 {text!r} 不合法：須為星期 1–7 與節次 1–9、a、b、c")
    day, period = text.strip().lower().split("-")
    return int(day), PERIODS.index(period)


def format_slot(slot: Slot) -> str:
    """將合法內部 Slot 轉回字串；索引非法時拋出 ValueError。"""
    day, period = slot
    if type(day) is not int or type(period) is not int or not 1 <= day <= 7 or not 0 <= period < 12:
        raise ValueError(f"內部時段 {slot!r} 不合法")
    return f"{day}-{PERIODS[period]}"


def describe_slots(slots: list[Slot] | frozenset[Slot]) -> str:
    """依星期、節次排序並合併同一天的節次，回傳繁體中文文字。"""
    by_day = {}
    for day, period in sorted(set(slots)):
        format_slot((day, period))
        by_day.setdefault(day, []).append(PERIODS[period])
    return "；".join(f"星期{DAYS[day - 1]}第 {'、'.join(periods)} 節" for day, periods in by_day.items())


def time_range_to_slots(day: int, start: str, end: str) -> list[Slot]:
    """將活動時間換算為所有重疊節次；日期推得的星期由呼叫者傳入。"""
    if type(day) is not int or not 1 <= day <= 7:
        raise ValueError("星期須為 1–7")
    if not all(isinstance(value, str) and re.fullmatch(r"\d{2}:\d{2}", value) for value in (start, end)):
        raise ValueError("活動時間須為 HH:MM")
    begin, finish = time.fromisoformat(start), time.fromisoformat(end)
    if begin < time(8, 10) or finish > time(20) or finish <= begin:
        raise ValueError("活動時間須在 08:10–20:00 且結束晚於開始")
    slots = [(day, index) for index in range(12)
             if begin < time(9 + index) and time(8 + index, 10) < finish]
    if not slots:
        raise ValueError("活動只落在下課時間，沒有對應節次")
    return slots
