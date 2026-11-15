"""將 F5 回傳值轉成繁體中文報告，不執行輸入輸出。"""
from .models import CourseOption
from .result import Result
from .timeslot import DAYS, describe_slots, parse_slot


def _option_line(option: CourseOption) -> str:
    label = "必修" if option.required else "選修"
    preference = "✓" if option.preferred else "✗"
    return (f"  [{label}] {option.code} {option.name}  {option.credits} 學分  "
            f"{describe_slots(option.slots)}  偏好 {preference}")


def format_filter_report(result: Result) -> str:
    """回傳可顯示的完整篩選結果；支援格式錯誤及不可行報告。"""
    if result.data is None:
        return "篩選失敗\n" + "\n".join(f"[{error.code}] {error.message}" for error in result.errors)
    report = result.data
    criteria = report.criteria
    blocked = describe_slots([parse_slot(slot) for slot in criteria.forbidden_slots]) or "無"
    preferred = "、".join(DAYS[day - 1] for day in criteria.preferred_days) or "不限"
    lines = [f"學生：{report.student_id} {report.student_name}  學分範圍 {criteria.min_credits}–{criteria.max_credits}",
             f"不可上課：{blocked}；偏好星期：{preferred}", "候選課程（可選）："]
    lines.extend([_option_line(item) for item in report.candidates] or ["  無"])
    lines.append("已排除：")
    for item in report.excluded:
        suffix = "（必修）" if item.required else ""
        lines.append(f"  {item.code} {item.name}{suffix}")
        lines.extend(f"    [{error.code}] {error.message}" for error in item.reasons)
    if not report.excluded:
        lines.append("  無")
    if report.already_enrolled:
        lines.append("已選課程（不重複計入候選）：" + "、".join(report.already_enrolled))
    lines.append(f"目前學分：{report.current_credits}；必修學分：{report.required_credits}；可選學分最多：{report.available_credits}")
    lines.append("可行性：可能可行（尚未搜尋課程組合）" if report.feasible else "可行性：不可行")
    lines.extend(f"  原因 {index} [{error.code}] {error.message}" for index, error in enumerate(result.errors, 1))
    return "\n".join(lines)
