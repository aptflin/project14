"""F5 命令列輸入輸出；既有選單呼叫本模組，不混入服務層。"""
import re

from f5_system import filterCourses
from .filter_display import format_filter_report
from .models import FilterCriteria
from .timeslot import PERIODS


def _tokens(text: str) -> list[str]:
    return [item for item in re.split(r"[\s,，、;；]+", text.strip()) if item]


def run_filter(courses: list | dict, students: list | dict,
               activities: list | dict, classrooms: list | dict) -> None:
    """詢問 F5 六項條件，顯示篩選報告；非法輸入顯示錯誤，不修改資料。"""
    print("\n--- F5 多條件課程篩選與可行性檢查 ---")
    sid = input("學號：").strip()
    desired = _tokens(input("希望修習課程（逗號或空白分隔，可留空）："))
    required = _tokens(input("必修課程（逗號或空白分隔，可留空）："))
    minimum = input("最低學分（預設 0）：").strip()
    maximum = input("最高學分（預設為學生上限）：").strip()
    blocked = _tokens(input("不可上課時段（如 2-3,5-a；星期五全天輸入 5-*）："))
    preferred = _tokens(input("偏好星期（如 1,2,3；留空不限）："))
    try:
        student_rows = students.get("records", []) if isinstance(students, dict) else students
        student = next((item for item in student_rows
                        if str(item.get("student_id", item.get("studentId", ""))).strip().upper() == sid.upper()), {})
        limit = student.get("credit_limit", student.get("maxCredits", 25))
        expanded = []
        for slot in blocked:
            if re.fullmatch(r"[1-7]-\*", slot):
                expanded.extend(f"{slot[0]}-{period}" for period in PERIODS)
            else:
                expanded.append(slot)
        criteria = FilterCriteria(desired, required, int(minimum or 0),
                                  int(maximum) if maximum else limit, expanded,
                                  [int(day) for day in preferred])
    except (ValueError, TypeError):
        print("[INVALID_VALUE] 學分與偏好星期必須輸入整數。")
        return
    print(format_filter_report(filterCourses(sid, criteria, courses, students, activities, classrooms)))
