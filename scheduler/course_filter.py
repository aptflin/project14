"""F5 FR-5.1–5.6：多條件篩選與必要條件可行性檢查；不搜尋課程組合。"""
from copy import deepcopy
from dataclasses import asdict
from itertools import combinations

from .adapters import normalise_data
from .conflict import course_occupancy, find_time_conflicts, overlap_slots, student_occupancies
from .models import CourseOption, FilterCriteria, FilterReport, SystemData
from .result import ErrorItem, Result
from .timeslot import describe_slots, parse_slot


def _criteria(value: FilterCriteria | dict) -> tuple[FilterCriteria | None, list[ErrorItem]]:
    errors = []
    try:
        raw = asdict(value) if isinstance(value, FilterCriteria) else dict(value)
        criteria = FilterCriteria(**deepcopy(raw))
    except (TypeError, ValueError):
        return None, [ErrorItem("INVALID_VALUE", "篩選條件欄位或資料格式不合法")]
    for name in ("desired_courses", "required_courses"):
        items = getattr(criteria, name)
        if not isinstance(items, list) or not all(isinstance(item, str) and item.strip() for item in items):
            errors.append(ErrorItem("INVALID_VALUE", f"{name} 須為非空代號組成的清單"))
        else:
            setattr(criteria, name, sorted({item.strip().upper() for item in items}))
    for name in ("min_credits", "max_credits"):
        if type(getattr(criteria, name)) is not int or getattr(criteria, name) < 0:
            errors.append(ErrorItem("INVALID_VALUE", f"{name} 須為非負整數，不接受布林值"))
    days = criteria.preferred_days
    if not isinstance(days, list) or any(type(day) is not int or not 1 <= day <= 7 for day in days):
        errors.append(ErrorItem("INVALID_VALUE", "偏好星期須為 1–7 的整數清單"))
    else:
        criteria.preferred_days = sorted(set(days))
    if not isinstance(criteria.forbidden_slots, list):
        errors.append(ErrorItem("INVALID_SLOT", "不可上課時段須為字串清單"))
    else:
        for slot in criteria.forbidden_slots:
            try:
                parse_slot(slot)
            except ValueError as exc:
                errors.append(ErrorItem("INVALID_SLOT", str(exc)))
    return criteria, errors


def _course_option(data: SystemData, code: str, required: set, forbidden: set,
                   preferred: set, occupancies: list) -> CourseOption:
    option = CourseOption(code, code, required=code in required)
    course = data.courses.get(code)
    if course is None:
        option.reasons.append(ErrorItem("NOT_FOUND", f"課程 {code} 不存在", related_id=code))
        return option
    option.name, option.credits = course.name, course.credits
    if course.status == "cancelled":
        option.reasons.append(ErrorItem("COURSE_CANCELLED", "課程已取消", related_id=code))
    count = sum(code in student.enrolled_courses for student in data.students.values())
    if count >= course.capacity:
        option.reasons.append(ErrorItem("COURSE_FULL", f"課程已額滿（{count}/{course.capacity}）", related_id=code))
    try:
        target = course_occupancy(course)
        option.slots = sorted(target.slots)
        option.preferred = not preferred or all(day in preferred for day, _ in option.slots)
        blocked = sorted(target.slots & forbidden)
        if blocked:
            option.reasons.append(ErrorItem("FORBIDDEN_SLOT", f"時段 {describe_slots(blocked)} 落在不可上課時段", blocked, code))
        option.reasons.extend(find_time_conflicts(target, occupancies))
    except (ValueError, TypeError) as exc:
        option.reasons.append(ErrorItem("INVALID_SLOT", f"{code}：{exc}", related_id=code))
    return option


def _required_errors(data: SystemData, required: set, report: FilterReport) -> list[ErrorItem]:
    errors = [ErrorItem("REQUIRED_EXCLUDED", f"必修課 {item.code} 被排除", related_id=item.code)
              for item in report.excluded if item.required]
    courses = [data.courses[code] for code in sorted(required) if code in data.courses]
    for a, b in combinations(courses, 2):
        try:
            slots = overlap_slots(course_occupancy(a), course_occupancy(b))
        except (ValueError, TypeError):
            continue  # 格式錯誤已在課程排除原因或已選資料檢查回報。
        if slots:
            errors.append(ErrorItem("REQUIRED_CONFLICT", f"必修課 {a.code} 與 {b.code} 於 {describe_slots(slots)} 衝堂", slots, b.code))
    report.required_credits = sum(course.credits for course in courses)
    new_required = sum(course.credits for course in courses if course.code not in report.already_enrolled)
    needed = report.current_credits + new_required
    if report.required_credits > report.criteria.max_credits or needed > report.criteria.max_credits:
        errors.append(ErrorItem("REQUIRED_EXCEEDS_MAX", f"必修學分 {report.required_credits}，含已選後至少 {needed} 學分，超過最高學分 {report.criteria.max_credits}"))
    return errors


def _feasibility(data: SystemData, sid: str, report: FilterReport, required: set) -> list[ErrorItem]:
    criteria = report.criteria
    errors = []
    if criteria.min_credits > criteria.max_credits:
        errors.append(ErrorItem("CREDIT_RANGE_INVALID", "最低學分大於最高學分"))
    if criteria.max_credits > data.students[sid].credit_limit:
        errors.append(ErrorItem("CREDIT_RANGE_INVALID", f"最高學分超過學生上限 {data.students[sid].credit_limit}"))
    errors.extend(_required_errors(data, required, report))
    report.available_credits = report.current_credits + sum(item.credits for item in report.candidates)
    if report.available_credits < criteria.min_credits:
        errors.append(ErrorItem("MIN_CREDITS_UNREACHABLE", f"可選學分最多 {report.available_credits}，低於最低學分 {criteria.min_credits}"))
    return errors


def filter_courses(data: SystemData, sid: str, criteria: FilterCriteria | dict) -> Result:
    """篩選課程並回傳 Result(data=FilterReport)，不修改輸入。

    參數為 SystemData、學號、FilterCriteria 或同欄位 dict。
    格式錯誤回傳 INVALID_VALUE／INVALID_SLOT／NOT_FOUND；必要條件不符
    回傳 CREDIT_RANGE_INVALID、REQUIRED_EXCLUDED、REQUIRED_CONFLICT、
    REQUIRED_EXCEEDS_MAX、MIN_CREDITS_UNREACHABLE，保留完整篩選報告。
    """
    criteria, errors = _criteria(criteria)
    try:
        data = normalise_data(data)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return Result(False, errors=errors + [ErrorItem("INVALID_VALUE", f"系統資料不完整或格式錯誤：{exc}")])
    sid = sid.strip().upper() if isinstance(sid, str) else ""
    if sid not in data.students:
        errors.append(ErrorItem("NOT_FOUND", f"學生 {sid} 不存在", related_id=sid))
    if errors:
        return Result(False, errors=errors)
    student = data.students[sid]
    try:
        occupancies = student_occupancies(data, sid)
    except (ValueError, TypeError, KeyError) as exc:
        return Result(False, errors=[ErrorItem("INVALID_SLOT", f"已選課程或活動時段無法檢查：{exc}")])
    enrolled = {code for code in student.enrolled_courses if data.courses[code].status != "cancelled"}
    report = FilterReport(sid, student.name, criteria, already_enrolled=sorted(enrolled))
    report.current_credits = sum(data.courses[code].credits for code in enrolled)
    required = set(criteria.required_courses)
    codes = (set(criteria.desired_courses) | required) - enrolled
    forbidden = {parse_slot(slot) for slot in criteria.forbidden_slots}
    for code in sorted(codes, key=lambda item: (item not in required, item)):
        option = _course_option(data, code, required, forbidden, set(criteria.preferred_days), occupancies)
        (report.excluded if option.reasons else report.candidates).append(option)
    errors = _feasibility(data, sid, report, required)
    report.feasible = not errors
    return Result(report.feasible, report, errors)
