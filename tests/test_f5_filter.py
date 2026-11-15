"""F5 驗收測試；編號對應需求 FR-5.1–5.6。"""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import json
import subprocess
import sys

import pytest

from f5_system import filterCourses
from scheduler.conflict import overlap_slots
from scheduler.course_filter import filter_courses
from scheduler.filter_display import format_filter_report
from scheduler.models import FilterCriteria, Occupancy


def codes(result):
    return [error.code for error in result.errors]


@pytest.mark.normal
def test_relaxed_conditions_are_feasible(sample_data):
    """T-F5-01 條件寬鬆、候選聯集與必修優先排序。"""
    result = filter_courses(sample_data, "S001", FilterCriteria(
        ["PH101", "CS101", "EN101", "cs101"], ["MA101"], 8, 20, [], [1, 2, 3]))
    assert result.ok
    assert [item.code for item in result.data.candidates] == ["MA101", "CS101", "EN101", "PH101"]
    assert result.data.available_credits == 11
    assert result.data.candidates[-1].preferred is False


@pytest.mark.error
def test_minimum_above_maximum(sample_data):
    """T-F5-02 最低學分大於最高學分。"""
    result = filter_courses(sample_data, "S001", FilterCriteria(["CS101"], [], 10, 5))
    assert not result.ok
    assert "CREDIT_RANGE_INVALID" in codes(result)
    assert "MIN_CREDITS_UNREACHABLE" in codes(result)


@pytest.mark.error
def test_required_courses_conflict(sample_data):
    """T-F5-03 必修彼此衝堂，選項仍保留供報告顯示。"""
    sample_data.courses["MA101"].slots = ["1-1", "1-2"]
    result = filter_courses(sample_data, "S001", FilterCriteria([], ["CS101", "MA101"], 3, 20))
    assert "REQUIRED_CONFLICT" in codes(result)
    assert len(result.data.candidates) == 2
    assert result.errors[0].slots == [(1, 0), (1, 1)]


@pytest.mark.error
def test_full_required_course_is_excluded(sample_data):
    """T-F5-04 必修額滿，名額由學生選課清單推算。"""
    sample_data.courses["CS101"].capacity = 1
    sample_data.students["S002"].enrolled_courses = ["CS101"]
    result = filter_courses(sample_data, "S001", FilterCriteria([], ["CS101"], 3, 20))
    assert "REQUIRED_EXCLUDED" in codes(result)
    assert result.data.excluded[0].reasons[0].code == "COURSE_FULL"


@pytest.mark.error
def test_insufficient_candidate_credits(sample_data):
    """T-F5-05 可選學分不足最低學分。"""
    result = filter_courses(sample_data, "S001", FilterCriteria(["EN101"], [], 3, 20))
    assert codes(result) == ["MIN_CREDITS_UNREACHABLE"]
    assert result.data.available_credits == 2


@pytest.mark.error
def test_all_infeasible_reasons_are_collected(sample_data):
    """T-F5-06 範圍、必修排除、必修衝堂、必修超分、最低不足全部回報。"""
    sample_data.courses["MA101"].slots = ["1-1"]
    sample_data.courses["CS101"].status = "cancelled"
    result = filter_courses(sample_data, "S001", FilterCriteria([], ["CS101", "MA101"], 30, 4))
    assert set(codes(result)) == {"CREDIT_RANGE_INVALID", "REQUIRED_EXCLUDED", "REQUIRED_CONFLICT",
                                 "REQUIRED_EXCEEDS_MAX", "MIN_CREDITS_UNREACHABLE"}


@pytest.mark.error
def test_all_exclusion_reasons_for_same_course(sample_data):
    """T-F5-07 同門課所有排除原因均保留，且時間類衝突排序。"""
    sample_data.courses["CS101"].status = "cancelled"
    sample_data.courses["CS101"].capacity = 1
    sample_data.students["S002"].enrolled_courses = ["CS101"]
    sample_data.students["S001"].enrolled_courses = ["MA101"]
    sample_data.courses["CS101"].slots = ["4-5", "2-4", "2-3"]
    result = filter_courses(sample_data, "S001", FilterCriteria(["CS101"], [], 0, 20, ["2-3"]))
    reasons = result.data.excluded[0].reasons
    assert {error.code for error in reasons} == {"COURSE_CANCELLED", "COURSE_FULL", "FORBIDDEN_SLOT",
                                               "STUDENT_TIME_CONFLICT", "ACTIVITY_TIME_CONFLICT"}
    timed = [error for error in reasons if error.code.endswith("TIME_CONFLICT")]
    assert [error.slots for error in timed] == [[(2, 2), (2, 3)], [(4, 4)]]


@pytest.mark.normal
def test_missing_course_and_cancelled_course_have_reasons(sample_data):
    """T-F5-08 不存在與取消項目均明列原因，不影響其他候選。"""
    sample_data.courses["CS101"].status = "cancelled"
    result = filter_courses(sample_data, "S001", FilterCriteria(["ZZ999", "CS101", "EN101"], [], 0, 20))
    assert result.ok  # 排除選修並不等於整體不可行。
    assert [item.code for item in result.data.candidates] == ["EN101"]
    assert [item.reasons[0].code for item in result.data.excluded] == ["COURSE_CANCELLED", "NOT_FOUND"]


@pytest.mark.boundary
def test_credits_equal_limits_and_one_seat_left(sample_data):
    """T-F5-09 學分恰等於範圍、人數差一額滿皆可用。"""
    sample_data.courses["CS101"].capacity = 1
    result = filter_courses(sample_data, "S001", FilterCriteria(["CS101"], ["CS101"], 3, 3))
    assert result.ok
    assert result.data.required_credits == result.data.available_credits == 3


@pytest.mark.boundary
def test_already_enrolled_not_double_counted_or_self_conflicting(sample_data):
    """T-F5-10 已選必修視為已滿足且不重複計分。"""
    sample_data.students["S001"].enrolled_courses = ["CS101"]
    result = filter_courses(sample_data, "S001", FilterCriteria(["CS101", "EN101"], ["CS101"], 5, 5))
    assert result.ok
    assert result.data.current_credits == 3
    assert result.data.available_credits == 5
    assert result.data.already_enrolled == ["CS101"]
    assert [item.code for item in result.data.candidates] == ["EN101"]


@pytest.mark.error
def test_maximum_cannot_exceed_student_limit(sample_data):
    """T-F5-11 最高學分超過學生上限仍列出其他原因。"""
    result = filter_courses(sample_data, "S001", FilterCriteria([], ["NO999"], 30, 25))
    assert "CREDIT_RANGE_INVALID" in codes(result)
    assert "REQUIRED_EXCLUDED" in codes(result)
    assert "MIN_CREDITS_UNREACHABLE" in codes(result)


@pytest.mark.normal
def test_cancelled_activity_does_not_exclude_course(sample_data):
    """T-F5-12 取消活動不占用學生時間。"""
    sample_data.courses["PH101"].slots = ["4-5"]
    sample_data.activities["EV001"].status = "cancelled"
    result = filter_courses(sample_data, "S001", FilterCriteria(["PH101"], [], 3, 20))
    assert result.ok and not result.data.excluded


@pytest.mark.normal
def test_once_activity_conflicts_with_weekly_course(sample_data):
    """T-F5-13 課程一律每週，單次已報名活動仍會衝突。"""
    sample_data.courses["PH101"].slots = ["4-5"]
    sample_data.activities["EV001"].recurrence = "once"
    result = filter_courses(sample_data, "S001", FilterCriteria(["PH101"], [], 0, 20))
    assert result.data.excluded[0].reasons[0].code == "ACTIVITY_TIME_CONFLICT"


@pytest.mark.boundary
def test_adjacent_slot_does_not_conflict(sample_data):
    """T-F5-14 相鄰而不重疊的節次可選。"""
    sample_data.courses["PH101"].slots = ["4-6"]
    assert filter_courses(sample_data, "S001", FilterCriteria(["PH101"], [], 3, 20)).ok


@pytest.mark.boundary
def test_empty_preferences_mean_unrestricted_and_night_slots_sort(sample_data):
    """T-F5-15 空偏好為不限，大寫夜間節次可解析並排序。"""
    sample_data.courses["PH101"].slots = ["7-C", "7-A", "7-9"]
    result = filter_courses(sample_data, "S001", FilterCriteria(["PH101"], [], 0, 20))
    assert result.data.candidates[0].preferred
    assert result.data.candidates[0].slots == [(7, 8), (7, 9), (7, 11)]


@pytest.mark.error
@pytest.mark.parametrize("changes", [
    {"min_credits": True}, {"max_credits": 2.5}, {"min_credits": -1},
    {"desired_courses": "CS101"}, {"required_courses": [""]},
    {"preferred_days": [True]}, {"preferred_days": [8]},
    {"forbidden_slots": ["2-d", "8-3"]}, {"forbidden_slots": "2-3"},
])
def test_invalid_criteria_returns_result_not_exception(sample_data, changes):
    """T-F5-16 不合法條件回傳錯誤而非拋出例外。"""
    result = filter_courses(sample_data, "S001", dict(asdict(FilterCriteria()), **changes))
    assert not result.ok and result.errors
    assert result.data is None


@pytest.mark.error
def test_unknown_student_and_invalid_input_both_reported(sample_data):
    """T-F5-17 不存在學生與輸入格式錯誤皆回報。"""
    result = filter_courses(sample_data, "unknown", {"min_credits": True})
    assert set(codes(result)) == {"NOT_FOUND", "INVALID_VALUE"}


@pytest.mark.boundary
def test_no_mutation_no_output_and_case_insensitive(sample_data, capsys):
    """T-F5-18 不改資料、不讀寫輸出、代號忽略空白與大小寫。"""
    before = deepcopy(sample_data)
    criteria = FilterCriteria([" cs101 ", "CS101"], [], 0, 20)
    original = deepcopy(criteria)
    assert filter_courses(sample_data, " s001 ", criteria).ok
    assert sample_data == before and criteria == original
    assert capsys.readouterr().out == ""


@pytest.mark.normal
def test_optional_conflicts_do_not_trigger_optimizer_search(sample_data):
    """T-F5-19 只檢查必要條件，不搜尋選修的最佳組合。"""
    sample_data.courses["EN101"].slots = ["1-1"]
    result = filter_courses(sample_data, "S001", FilterCriteria(["CS101", "EN101"], [], 5, 20))
    assert result.ok
    assert len(result.data.candidates) == 2


@pytest.mark.error
def test_current_plus_new_required_cannot_exceed_total_max(sample_data):
    """T-F5-20 已選學分納入總學分範圍。"""
    sample_data.students["S001"].enrolled_courses = ["CS101"]
    result = filter_courses(sample_data, "S001", FilterCriteria([], ["MA101"], 0, 5))
    assert "REQUIRED_EXCEEDS_MAX" in codes(result)


@pytest.mark.normal
def test_v1_wrapped_json_derives_activity_slots_and_participants(sample_data):
    """T-F5-21 v1 活動無 slots，報名名單由活動 participants 讀取。"""
    sample_data.courses["PH101"].slots = ["4-5"]
    courses = {"schema_version": 1, "records": [asdict(item) for item in sample_data.courses.values()]}
    students = {"schema_version": 1, "records": [asdict(item) for item in sample_data.students.values()]}
    activity = asdict(sample_data.activities["EV001"])
    del activity["slots"]
    result = filterCourses("S001", FilterCriteria(["PH101"], [], 0, 20), courses, students,
                           {"schema_version": 1, "records": [activity]}, {"schema_version": 1, "records": []})
    assert result.ok
    assert result.data.excluded[0].reasons[0].code == "ACTIVITY_TIME_CONFLICT"


@pytest.mark.error
def test_legacy_activity_enrollment_is_adapted():
    """T-F5-22 舊資料由 enrolledActivities 轉出活動參加者。"""
    courses = [{"courseId": "C001", "name": "課程", "credits": 3, "maxStudents": 10,
                "roomId": "R101", "schedules": [{"day": 4, "period": "5"}]}]
    students = [{"studentId": "115360001", "maxCredits": 25, "enrolledCourses": [], "enrolledActivities": ["A001"]}]
    activities = [{"activityId": "A001", "name": "舊活動", "schedules": [{"day": 4, "period": "5"}]}]
    result = filterCourses("115360001", FilterCriteria(["C001"], [], 3, 20), courses, students, activities, [])
    assert result.data.excluded[0].reasons[0].code == "ACTIVITY_TIME_CONFLICT"


@pytest.mark.error
def test_malformed_course_slot_and_missing_enrolled_reference(sample_data):
    """T-F5-23 時段錯誤拒絕該課，遺失已選參照拒絕整次操作。"""
    sample_data.courses["CS101"].slots = ["8-1"]
    result = filter_courses(sample_data, "S001", FilterCriteria([], ["CS101"], 0, 20))
    assert result.data.excluded[0].reasons[0].code == "INVALID_SLOT"
    assert "REQUIRED_EXCLUDED" in codes(result)
    sample_data.students["S001"].enrolled_courses = ["NO999"]
    assert not filter_courses(sample_data, "S001", FilterCriteria()).ok


@pytest.mark.normal
def test_shared_overlap_obeys_once_and_weekly_dates():
    """T-F5-24 共用時間函式遵循單次日期及每週重複規則。"""
    a = Occupancy("activity", "EV001", "A", frozenset({(1, 0)}), "2026-10-26")
    b = Occupancy("activity", "EV002", "B", frozenset({(1, 0)}), "2026-11-02")
    c = Occupancy("course", "CS101", "課程", frozenset({(1, 0)}))
    assert overlap_slots(a, b) == []
    assert overlap_slots(a, c) == [(1, 0)]


@pytest.mark.normal
def test_report_includes_exclusion_reasons_and_soft_preference(sample_data):
    """T-F5-25 報告包含偏好標記、排除原因及所有不可行原因。"""
    result = filter_courses(sample_data, "S001", FilterCriteria(["EN101", "PH101"], ["MA101"], 20, 20, ["2-3"], [3]))
    text = format_filter_report(result)
    for expected in ("偏好 ✓", "偏好 ✗", "FORBIDDEN_SLOT", "REQUIRED_EXCLUDED", "MIN_CREDITS_UNREACHABLE", "不可行"):
        assert expected in text


@pytest.mark.normal
def test_cli_option_11_uses_temp_data_and_does_not_save(sample_data, tmp_path):
    """T-F5-26 命令列 F5 支援全天禁課，且不儲存任何正式資料。"""
    records = {
        "courses": [{"courseId": "CS101", "name": "Python", "credits": 3, "maxStudents": 10,
                     "roomId": "R101", "schedules": [{"day": 1, "period": "1"}]}],
        "students": [{"studentId": "S001", "name": "測試", "maxCredits": 24, "enrolledCourses": []}],
        "activities": [], "classrooms": [{"roomId": "R101"}],
    }
    for name, data in records.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    script = Path(__file__).resolve().parents[1] / "f1_system.py"
    run = subprocess.run([sys.executable, "-B", "-X", "utf8", str(script)],
                         input="11\nS001\nCS101\n\n3\n20\n5-*\n1\n0\n", encoding="utf-8",
                         capture_output=True, cwd=tmp_path, timeout=10)
    assert run.returncode == 0, run.stderr
    assert "可能可行" in run.stdout and "星期五" in run.stdout
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before
