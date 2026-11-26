"""F7 舊版 camelCase／v1 JSON 轉接；正式介面在 scheduler.optimizer。"""
from scheduler.adapters import system_data_from_records
from scheduler.models import FilterCriteria, ScoreWeights
from scheduler.optimizer import search_best_timetables
from scheduler.optimizer_display import format_optimizer_report
from scheduler.result import ErrorItem, Result


def searchBestTimetables(studentId: str, criteria: FilterCriteria | dict,
                         courses: list | dict, students: list | dict,
                         activities: list | dict, classrooms: list | dict,
                         *, weights: ScoreWeights | dict | None = None,
                         preferred_courses: list[str] | None = None,
                         top_k: int | None = 5) -> Result:
    """將舊清單／v1 records 轉為 F7 建議，不修改資料。

    輸入為學號、F5 條件及四類資料；回傳 Result(data=OptimizerReport)。
    格式錯誤為 INVALID_VALUE，其餘錯誤與 search_best_timetables 相同。
    """
    try:
        data = system_data_from_records(courses, students, activities, classrooms)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return Result(False, errors=[ErrorItem("INVALID_VALUE", f"資料無法載入：{exc}")])
    return search_best_timetables(data, studentId, criteria, weights=weights,
                                  preferred_courses=preferred_courses, top_k=top_k)
