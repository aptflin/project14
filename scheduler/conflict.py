"""所有服務共用的時間重疊與日期規則（需求規格 3.5）。"""
from datetime import date

from .models import Course, Occupancy, SystemData
from .result import ErrorItem, Slot
from .timeslot import describe_slots, parse_slot, time_range_to_slots


def dates_can_overlap(a_date: str | None, b_date: str | None) -> bool:
    """None 表示每週；兩個單次占用只有同日期才可能衝突。"""
    return a_date is None or b_date is None or a_date == b_date


def overlap_slots(a: Occupancy, b: Occupancy) -> list[Slot]:
    """回傳依星期、節次排序的重疊時段；None 日期代表每週重複。"""
    if not dates_can_overlap(a.date, b.date):
        return []
    return sorted(a.slots & b.slots)


def course_occupancy(course: Course) -> Occupancy:
    """將課程轉成每週 Occupancy；非法時段會拋出 ValueError。"""
    if not course.slots:
        raise ValueError(f"課程 {course.code} 缺少時段")
    return Occupancy("course", course.code, course.name,
                     frozenset(parse_slot(slot) for slot in course.slots), room_id=course.room_id)


def student_occupancies(data: SystemData, sid: str) -> list[Occupancy]:
    """取得學生有效課程與報名活動；報名名單由 activities.participants 推得。"""
    student = data.students[sid]
    items = [course_occupancy(data.courses[code]) for code in set(student.enrolled_courses)
             if data.courses[code].status != "cancelled"]
    for activity in data.activities.values():
        if activity.status == "cancelled" or sid not in activity.participants:
            continue
        slots = ([parse_slot(slot) for slot in activity.slots] if activity.slots else
                 time_range_to_slots(date.fromisoformat(activity.date).isoweekday(),
                                     activity.start_time, activity.end_time))
        items.append(Occupancy("activity", activity.activity_id, activity.name,
                               frozenset(slots), activity.date if activity.recurrence == "once" else None,
                               activity.room_id))
    return items


def find_time_conflicts(target: Occupancy, others: list[Occupancy]) -> list[ErrorItem]:
    """回傳所有衝突，依星期節次排序；同對象同日的連續節次合併。"""
    errors = []
    for other in others:
        if (target.source_type, target.source_id) == (other.source_type, other.source_id):
            continue
        groups = []
        for slot in overlap_slots(target, other):
            if groups and groups[-1][-1] == (slot[0], slot[1] - 1):
                groups[-1].append(slot)
            else:
                groups.append([slot])
        code = "STUDENT_TIME_CONFLICT" if other.source_type == "course" else "ACTIVITY_TIME_CONFLICT"
        for slots in groups:
            errors.append(ErrorItem(code, f"{describe_slots(slots)}與 {other.source_id} {other.name} 衝突",
                                    slots, other.source_id))
    return sorted(errors, key=lambda error: (error.slots[0], error.related_id))


def legacy_overlap(a: dict, a_slots: set, b: dict, b_slots: set) -> list[tuple[int, str]]:
    """既有 camelCase 模組轉接；時間交集與日期判斷仍只由 overlap_slots 執行。"""
    from .timeslot import PERIODS

    def occupancy(item: dict, slots: set) -> Occupancy:
        once = "courseId" not in item and item.get("recurrence", "weekly") == "once"
        return Occupancy("activity" if once else "course", "", "",
                         frozenset((day, PERIODS.index(period)) for day, period in slots),
                         item.get("date") if once else None)

    return [(day, PERIODS[index]) for day, index in overlap_slots(occupancy(a, a_slots), occupancy(b, b_slots))]
