"""既有 F1–F4 專案的 F5 入口；正式服務介面為 scheduler.course_filter.filter_courses"""
from scheduler.adapters import system_data_from_records
from scheduler.course_filter import filter_courses
from scheduler.filter_display import format_filter_report
from scheduler.models import FilterCriteria
from scheduler.result import ErrorItem, Result


def filterCourses(studentId: str, criteria: FilterCriteria | dict, courses: list | dict,
                  students: list | dict, activities: list | dict, classrooms: list | dict) -> Result:
    """轉接舊／v1 JSON 資料並篩選，不讀寫檔案；格式錯誤回傳 INVALID_VALUE"""
    try:
        data = system_data_from_records(courses, students, activities, classrooms)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return Result(False, errors=[ErrorItem("INVALID_VALUE", f"資料無法載入：{exc}")])
    return filter_courses(data, studentId, criteria)
