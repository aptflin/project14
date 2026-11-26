"""F7：以回溯完整搜尋可行課表；所有評分均不修改 SystemData。"""
from bisect import insort
from dataclasses import asdict
from itertools import combinations
from math import isfinite

from .adapters import normalise_data
from .conflict import course_occupancy, find_time_conflicts, overlap_slots, student_occupancies
from .course_filter import filter_courses
from .models import (
    FilterCriteria, OptimizerReport, ScheduleOption, ScheduleScore,
    ScoreWeights, SystemData,
)
from .result import ErrorItem, NO_FEASIBLE_TIMETABLE, Result
from .timeslot import describe_slots, parse_slot


def _preferences(weights, preferred_courses, top_k):
    errors = []
    try:
        weights = ScoreWeights(**weights) if isinstance(weights, dict) else weights
        weights = ScoreWeights() if weights is None else weights
        if not isinstance(weights, ScoreWeights):
            raise ValueError("權重須為 ScoreWeights 或同欄位物件")
        for name, value in asdict(weights).items():
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1000000:
                errors.append(ErrorItem("INVALID_VALUE", f"權重 {name} 須為 0–1000000 的有限數值"))
    except (TypeError, ValueError, OverflowError) as exc:
        errors.append(ErrorItem("INVALID_VALUE", f"評分權重不合法：{exc}"))
    if top_k is not None and (type(top_k) is not int or top_k < 1):
        errors.append(ErrorItem("INVALID_VALUE", "輸出組數須為正整數或 None（全部）"))
    if preferred_courses is not None:
        if not isinstance(preferred_courses, list) or not all(
            isinstance(code, str) and code.strip() for code in preferred_courses
        ):
            errors.append(ErrorItem("INVALID_VALUE", "偏好課程須為非空代號組成的清單"))
        else:
            preferred_courses = sorted({code.strip().upper() for code in preferred_courses})
    return weights, preferred_courses, errors


def _baseline_errors(report, occupancies):
    errors = []
    forbidden = {parse_slot(slot) for slot in report.criteria.forbidden_slots}
    for item in occupancies:
        blocked = sorted(item.slots & forbidden) if item.source_type == "course" else []
        if blocked:
            errors.append(ErrorItem("FORBIDDEN_SLOT",
                                    f"已選課程 {item.source_id} 位於不可上課時段：{describe_slots(blocked)}",
                                    blocked, item.source_id))
    for a, b in combinations(occupancies, 2):
        errors.extend(find_time_conflicts(a, [b]))
    maximum = report.criteria.max_credits
    if report.current_credits > maximum:
        errors.append(ErrorItem("CREDIT_LIMIT_EXCEEDED",
                                f"已選 {report.current_credits} 學分超過最高學分 {maximum}"))
    return errors


def _score(occupancies, codes, preferred_courses, preferred_days, weights):
    by_day = {}
    for item in occupancies:
        for day, period in item.slots:
            by_day.setdefault(day, set()).add(period)
    days = len(by_day)
    span = sum(max(periods) - min(periods) + 1 for periods in by_day.values())
    occupied = sum(map(len, by_day.values()))
    gaps = span - occupied
    early = sum(0 in periods for periods in by_day.values())
    course_ratio = len(set(codes) & preferred_courses) / len(codes) if codes and preferred_courses else 0
    day_ratio = (sum(len(periods) for day, periods in by_day.items() if day in preferred_days)
                 / occupied if occupied and preferred_days else 0)
    total = (-weights.days * days - weights.gaps * gaps - weights.early * early
             - weights.span * span + weights.preferred_courses * course_ratio
             + weights.preferred_days * day_ratio)
    return ScheduleScore(days, gaps, early, span, course_ratio, day_ratio, round(total, 8))


def _rank(option):
    score = option.score
    return (-score.total, score.days, score.gaps, score.early, score.span,
            -option.total_credits, tuple(option.course_codes))


def _enumerate_schedules(options, targets, current, minimum, maximum, report):
    """保留必要課，剪除衝堂或學分不可能達標的分支；不因 top_k 提早結束。"""
    suffix = [0] * (len(options) + 1)
    for i in range(len(options) - 1, -1, -1):
        suffix[i] = suffix[i + 1] + options[i].credits
    conflicts = {i: {j for j in range(i) if overlap_slots(targets[i], targets[j])}
                 for i in range(len(options))}

    def visit(index, selected, credits):
        report.visited_nodes += 1
        if credits > maximum or credits + suffix[index] < minimum:
            return
        if index == len(options):
            yield selected, credits
            return
        if not conflicts[index].intersection(selected):
            yield from visit(index + 1, selected + [index], credits + options[index].credits)
        if not options[index].required:
            yield from visit(index + 1, selected, credits)

    yield from visit(0, [], current)


def _search(data, report, baseline):
    filtered = report.filter_report
    options = filtered.candidates
    targets = [course_occupancy(data.courses[option.code]) for option in options]
    preferred, days = set(report.preferred_courses), set(filtered.criteria.preferred_days)
    ranked = []
    for selected, credits in _enumerate_schedules(
        options, targets, filtered.current_credits, filtered.criteria.min_credits,
        filtered.criteria.max_credits, report,
    ):
        added = sorted(options[i].code for i in selected)
        codes = sorted(filtered.already_enrolled + added)
        occupancies = baseline + [targets[i] for i in selected]
        score = _score(occupancies, codes, preferred, days, report.weights)
        option = ScheduleOption(codes, added, credits, score, occupancies)
        # 每個課程集合只產生一次；排序鍵含完整代號，故不需比較 option 物件。
        if report.top_k is None:
            ranked.append((_rank(option), option))
        else:
            insort(ranked, (_rank(option), option))
        if report.top_k is not None and len(ranked) > report.top_k:
            ranked.pop()
        report.feasible_count += 1
    report.schedules = [option for _, option in sorted(ranked)]


def search_best_timetables(data: SystemData, sid: str, criteria: FilterCriteria | dict,
                           *, weights: ScoreWeights | dict | None = None,
                           preferred_courses: list[str] | None = None,
                           top_k: int | None = 5) -> Result:
    """搜尋全部可行課表並評分，回傳 Result(data=OptimizerReport)，不讀寫檔案。

    data 為 SystemData；sid 不分大小寫；criteria 沿用 F5，學分含已選課程。
    已選課程及已報名活動固定保留。preferred_courses 預設為希望修習清單；
    top_k=None 回傳全部，正整數只限制顯示數量。權重欄位見 ScoreWeights。
    可能錯誤：F5 全部錯誤、INVALID_VALUE、FORBIDDEN_SLOT、
    STUDENT_TIME_CONFLICT、ACTIVITY_TIME_CONFLICT、CREDIT_LIMIT_EXCEEDED、
    NO_FEASIBLE_TIMETABLE。排除選修本身不代表無解，原因保留在 filter_report。
    """
    weights, preferred, errors = _preferences(weights, preferred_courses, top_k)
    filtered = filter_courses(data, sid, criteria)
    errors.extend(filtered.errors)
    if filtered.data is None:
        return Result(False, errors=errors)
    try:
        normalized = normalise_data(data)
        sid = filtered.data.student_id
        baseline = student_occupancies(normalized, sid)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return Result(False, errors=errors + [ErrorItem("INVALID_VALUE", f"資料無法檢查：{exc}")])
    report = OptimizerReport(sid, filtered.data.student_name, filtered.data, weights,
                             preferred if preferred is not None else filtered.data.criteria.desired_courses,
                             top_k)
    errors.extend(_baseline_errors(filtered.data, baseline))
    if errors:
        return Result(False, report, errors)
    _search(normalized, report, baseline)
    if not report.feasible_count:
        errors.append(ErrorItem(NO_FEASIBLE_TIMETABLE,
                                "候選課程無法同時滿足不衝堂、必修及學分範圍，找不到可行課表"))
    return Result(not errors, report, errors)
