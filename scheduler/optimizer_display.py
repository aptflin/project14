"""F7 中文課表與評分報告；僅產生字串，不執行輸入輸出。"""
from .models import ScheduleOption
from .result import Result
from .timeslot import DAYS, PERIODS, describe_slots


def _table(option: ScheduleOption) -> list[str]:
    cells = {}
    for item in option.occupancies:
        label = ("*" if item.source_type == "activity" else "") + item.source_id
        for slot in item.slots:
            cells.setdefault(slot, []).append(label)
    lines = ["節次 | " + " | ".join(f"星期{day}" for day in DAYS)]
    for index, period in enumerate(PERIODS):
        values = ["/".join(sorted(cells.get((day, index), []))) or "." for day in range(1, 8)]
        lines.append(f"{period:>4} | " + " | ".join(values))
    return lines


def format_optimizer_report(result: Result) -> str:
    """將 F7 Result 轉為含排除原因、排名、7×12 課表及評分明細的文字。"""
    if result.data is None:
        return "最佳課表搜尋失敗\n" + "\n".join(
            f"[{error.code}] {error.message}" for error in result.errors)
    report = result.data
    criteria = report.filter_report.criteria
    lines = [f"學生：{report.student_id} {report.student_name}",
             f"學分範圍：{criteria.min_credits}–{criteria.max_credits}（包含已選學分）",
             "搜尋結果：" + ("成功" if result.ok else "不可行"),
             f"可行課表共 {report.feasible_count} 組；顯示 {len(report.schedules)} 組",
             "搜尋只提供建議；選課與活動資料保持原樣。"]
    lines.extend(f"原因 {i} [{error.code}] {error.message}"
                 for i, error in enumerate(result.errors, 1))
    for option in report.filter_report.excluded:
        lines.append(f"排除 {option.code} {option.name}：")
        lines.extend(f"  [{error.code}] {error.message}" for error in option.reasons)
    for number, option in enumerate(report.schedules, 1):
        score = option.score
        lines.extend([f"\n第 {number} 名　總分 {score.total:.4f}　總學分 {option.total_credits}",
                      "課程：" + ("、".join(option.course_codes) or "無"),
                      "建議加選：" + ("、".join(option.added_courses) or "無"),
                      f"到校 {score.days} 天；空堂 {score.gaps} 節；早八 {score.early} 天；每日跨度合計 {score.span} 節",
                      f"偏好課程比例 {score.preferred_course_ratio:.1%}；偏好星期占用比例 {score.preferred_day_ratio:.1%}"])
        lines.extend(_table(option))
        for item in option.occupancies:
            suffix = f"（單次活動 {item.date}）" if item.date else ""
            lines.append(f"  {item.source_id} {item.name}　{describe_slots(item.slots)}{suffix}")
    return "\n".join(lines)
