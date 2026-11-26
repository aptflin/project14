"""F7：以獨立資料驗證搜尋完整性、偏好與必要條件。"""
from copy import deepcopy
from itertools import combinations

import pytest

from scheduler.models import Activity, Course, FilterCriteria, Student, SystemData
from scheduler.optimizer import ScoreWeights, search_best_timetables


def catalog():
    return SystemData(courses={
        "CS101": Course("CS101", "必修", 3, "required", "教師", 20, "EE-101", ["1-2"]),
        "CS102": Course("CS102", "相鄰", 3, "elective", "教師", 20, "EE-102", ["1-3"]),
        "CS103": Course("CS103", "分散", 3, "elective", "教師", 20, "EE-103", ["2-1"]),
        "CS104": Course("CS104", "衝堂", 3, "elective", "教師", 20, "EE-104", ["1-2"]),
    }, students={"S001": Student("S001", "測試學生", "資工二", 24)})


@pytest.mark.normal
def test_enumerates_every_feasible_schedule_and_ranks():
    """T-F7-01 完整搜尋，必修固定，集中且無早八者優先。"""
    result = search_best_timetables(catalog(), "S001", FilterCriteria(
        ["CS102", "CS103", "CS104"], ["CS101"], 6, 9), top_k=None)
    assert result.ok
    assert result.data.feasible_count == 3
    assert result.data.schedules[0].course_codes == ["CS101", "CS102"]
    assert all("CS104" not in s.course_codes for s in result.data.schedules)
    assert [s.score.total for s in result.data.schedules] == sorted(
        [s.score.total for s in result.data.schedules], reverse=True)


@pytest.mark.boundary
def test_top_k_does_not_stop_search_or_change_count():
    """T-F7-02 只顯示一組仍搜尋全部，空組合也是合法解。"""
    criteria = FilterCriteria(["CS101", "CS102", "CS103"], [], 0, 24)
    result = search_best_timetables(catalog(), "S001", criteria, top_k=1)
    assert result.ok and result.data.feasible_count == 8
    assert len(result.data.schedules) == 1


@pytest.mark.normal
def test_exact_solutions_match_independent_small_oracle():
    """T-F7-03 與獨立窮舉對照，防止漏解或重複。"""
    data = catalog()
    names = sorted(data.courses)
    expected = set()
    for size in range(5):
        for subset in combinations(names, size):
            slots = [slot for code in subset for slot in data.courses[code].slots]
            credits = sum(data.courses[code].credits for code in subset)
            if len(slots) == len(set(slots)) and 3 <= credits <= 9:
                expected.add(tuple(subset))
    result = search_best_timetables(data, "S001", FilterCriteria(names, [], 3, 9), top_k=None)
    assert result.ok
    assert {tuple(s.course_codes) for s in result.data.schedules} == expected
    assert result.data.feasible_count == len(expected)


@pytest.mark.error
def test_f5_possible_but_no_joint_solution():
    """T-F7-04 候選總學分足夠但彼此衝堂，精確搜尋指出無解。"""
    result = search_best_timetables(catalog(), "S001", FilterCriteria(
        ["CS101", "CS104"], [], 6, 6))
    assert not result.ok
    assert "NO_FEASIBLE_TIMETABLE" in [e.code for e in result.errors]
    assert result.data.feasible_count == 0


@pytest.mark.boundary
def test_enrolled_required_is_fixed_and_not_counted_twice():
    """T-F7-05 已選課額滿不排除本人，不重複計學分。"""
    data = catalog()
    data.students["S001"].enrolled_courses = ["CS101"]
    data.courses["CS101"].capacity = 1
    result = search_best_timetables(data, " s001 ", FilterCriteria(
        ["cs101", "CS102"], ["cs101"], 6, 6))
    assert result.ok and result.data.feasible_count == 1
    assert result.data.schedules[0].course_codes == ["CS101", "CS102"]
    assert result.data.schedules[0].added_courses == ["CS102"]
    assert result.data.schedules[0].total_credits == 6


@pytest.mark.error
def test_collects_all_required_and_credit_failures():
    """T-F7-06 不在第一項條件失敗後停止檢查。"""
    data = catalog()
    data.courses["CS101"].status = "cancelled"
    result = search_best_timetables(data, "S001", FilterCriteria(
        [], ["CS101", "CS104"], 30, 2))
    assert {e.code for e in result.errors} >= {
        "CREDIT_RANGE_INVALID", "REQUIRED_EXCLUDED", "REQUIRED_CONFLICT",
        "REQUIRED_EXCEEDS_MAX", "MIN_CREDITS_UNREACHABLE"}


@pytest.mark.boundary
def test_search_is_read_only():
    """T-F7-07 搜尋不修改條件、課程、學生、活動與選課紀錄。"""
    data = catalog()
    criteria = FilterCriteria(["cs102", "CS103"], ["CS101"], 3, 9)
    before = deepcopy((data, criteria))
    search_best_timetables(data, "S001", criteria)
    assert (data, criteria) == before


@pytest.mark.error
@pytest.mark.parametrize("top_k", [0, -1, True, 1.5, "5"])
def test_invalid_output_limit(top_k):
    """T-F7-08 非法輸出數量以 Result 拒絕。"""
    result = search_best_timetables(catalog(), "S001", FilterCriteria(), top_k=top_k)
    assert not result.ok and "INVALID_VALUE" in [e.code for e in result.errors]


@pytest.mark.normal
def test_adjustable_weights_can_prefer_course_ratio():
    """T-F7-09 偏好比例能透過權重影響排名。"""
    result = search_best_timetables(catalog(), "S001", FilterCriteria(
        ["CS102", "CS103"], ["CS101"], 6, 6), preferred_courses=["CS103"],
        weights=ScoreWeights(days=0, gaps=0, early=0, span=0, preferred_courses=10, preferred_days=0))
    assert result.ok
    assert result.data.schedules[0].course_codes == ["CS101", "CS103"]


@pytest.mark.boundary
def test_tie_is_deterministic_independent_of_input_order():
    """T-F7-10 完全同分時依課程代號，與輸入順序無關。"""
    data = catalog()
    data.courses["CS102"].slots = ["1-2"]
    weights = ScoreWeights(0, 0, 0, 0, 0, 0)
    a = search_best_timetables(data, "S001", FilterCriteria(["CS102", "CS101"], [], 3, 3), weights=weights)
    b = search_best_timetables(data, "S001", FilterCriteria(["CS101", "CS102", "cs101"], [], 3, 3), weights=weights)
    assert [s.course_codes for s in a.data.schedules] == [["CS101"], ["CS102"]]
    assert a.data.schedules == b.data.schedules


@pytest.mark.normal
def test_score_metrics_include_fixed_activity_and_night_periods():
    """T-F7-11 活動納入占用，9/a/b/c 依正確節次順序計算空堂與跨度。"""
    data = catalog()
    data.courses["CS101"].slots = ["7-9", "7-c"]
    data.activities["EV001"] = Activity("EV001", "晚間活動", "2026-11-29", "17:10", "18:00",
                                        "once", participants=["S001"])
    result = search_best_timetables(data, "S001", FilterCriteria([], ["CS101"], 3, 3, [], [7]))
    score = result.data.schedules[0].score
    assert (score.days, score.gaps, score.early, score.span) == (1, 1, 0, 4)
    assert score.preferred_day_ratio == 1
    assert score.preferred_course_ratio == 0
    assert score.total == -6  # -5*1 -2*1 -1*4 +5*1


@pytest.mark.normal
def test_nonpreferred_days_are_soft_conditions():
    """T-F7-12 不在偏好星期仍可行，僅評分較低。"""
    result = search_best_timetables(catalog(), "S001", FilterCriteria(
        ["CS102", "CS103"], [], 3, 3, [], [2]),
        weights=ScoreWeights(0, 0, 0, 0, 0, 10))
    assert result.ok and result.data.feasible_count == 2
    assert result.data.schedules[0].course_codes == ["CS103"]


@pytest.mark.error
def test_full_cancelled_forbidden_missing_and_activity_exclusions():
    """T-F7-13 同時記錄所有候選排除原因，必修被排除則無解。"""
    data = catalog()
    data.courses["CS101"].capacity = 1
    data.students["S002"] = Student("S002", "其他", "資工一", 25, ["CS101"])
    data.courses["CS102"].status = "cancelled"
    data.activities["EV001"] = Activity("EV001", "活動", "2026-11-24", "08:10", "09:00",
                                        "once", participants=["S001"])
    result = search_best_timetables(data, "S001", FilterCriteria(
        ["CS101", "CS102", "CS103", "ZZ999"], ["CS104"], 0, 24, ["1-2"]))
    excluded = {item.code: {e.code for e in item.reasons} for item in result.data.filter_report.excluded}
    assert excluded == {
        "CS101": {"COURSE_FULL", "FORBIDDEN_SLOT"}, "CS102": {"COURSE_CANCELLED"},
        "CS103": {"ACTIVITY_TIME_CONFLICT"}, "CS104": {"FORBIDDEN_SLOT"}, "ZZ999": {"NOT_FOUND"}}
    assert not result.ok and "REQUIRED_EXCLUDED" in [e.code for e in result.errors]


@pytest.mark.boundary
def test_cancelled_activity_does_not_block_candidate():
    """T-F7-14 已取消活動釋放時段。"""
    data = catalog()
    data.activities["EV001"] = Activity("EV001", "活動", "2026-11-23", "09:10", "10:00",
                                        "weekly", participants=["S001"], status="cancelled")
    result = search_best_timetables(data, "S001", FilterCriteria([], ["CS101"], 3, 3))
    assert result.ok


@pytest.mark.error
def test_fixed_schedule_violations_are_all_rejected():
    """T-F7-15 已選課本身衝堂、違反禁課與學分上限也須回報。"""
    data = catalog()
    data.students["S001"].enrolled_courses = ["CS101", "CS104"]
    result = search_best_timetables(data, "S001", FilterCriteria([], [], 0, 3, ["1-2"]))
    assert not result.ok
    assert {e.code for e in result.errors} >= {
        "STUDENT_TIME_CONFLICT", "FORBIDDEN_SLOT", "CREDIT_LIMIT_EXCEEDED"}
    assert result.data.feasible_count == 0


@pytest.mark.boundary
def test_once_activities_same_weekday_different_dates_do_not_conflict():
    """T-F7-16 單次活動不同日期不互斥；仍保留於建議課表。"""
    data = catalog()
    for i, date in enumerate(["2026-11-24", "2026-12-01"], 1):
        key = f"EV{i:03}"
        data.activities[key] = Activity(key, "單次活動", date, "12:10", "13:00",
                                        "once", participants=["S001"])
    result = search_best_timetables(data, "S001", FilterCriteria(max_credits=24))
    assert result.ok and len(result.data.schedules[0].occupancies) == 2
    data.activities["EV002"].recurrence = "weekly"
    result = search_best_timetables(data, "S001", FilterCriteria(max_credits=24))
    assert not result.ok and "ACTIVITY_TIME_CONFLICT" in [e.code for e in result.errors]


@pytest.mark.error
@pytest.mark.parametrize("weights", [
    {"days": -1}, {"gaps": True}, {"early": float("nan")}, {"span": float("inf")},
    {"preferred_courses": "10"}, {"unknown": 1}, [], {"days": 10**400},
])
def test_invalid_weights_are_results_not_exceptions(weights):
    """T-F7-17 拒絕負權重、布林、非有限值與未知欄位。"""
    result = search_best_timetables(catalog(), "S001", FilterCriteria(), weights=weights)
    assert not result.ok and "INVALID_VALUE" in [e.code for e in result.errors]


@pytest.mark.error
@pytest.mark.parametrize("preferred", ["CS101", [True], [" "]])
def test_invalid_preferred_course_list(preferred):
    """T-F7-18 偏好課程清單格式驗證。"""
    result = search_best_timetables(catalog(), "S001", FilterCriteria(), preferred_courses=preferred)
    assert not result.ok and "INVALID_VALUE" in [e.code for e in result.errors]


@pytest.mark.error
def test_unknown_student_and_invalid_criteria():
    """T-F7-19 前置錯誤以 Result 一次回傳。"""
    result = search_best_timetables(catalog(), "S999", {"forbidden_slots": ["8-d"]}, top_k=0)
    assert {e.code for e in result.errors} == {"NOT_FOUND", "INVALID_SLOT", "INVALID_VALUE"}


@pytest.mark.boundary
def test_empty_and_exact_credit_boundaries():
    """T-F7-20 零課程零學分與剛好達上下限皆為合法解。"""
    empty = search_best_timetables(catalog(), "S001", FilterCriteria([], [], 0, 0))
    assert empty.ok and empty.data.feasible_count == 1
    assert empty.data.schedules[0].score.total == 0
    exact = search_best_timetables(catalog(), "S001", FilterCriteria(["CS101"], [], 3, 3))
    assert exact.ok and exact.data.schedules[0].total_credits == 3


@pytest.mark.normal
def test_adapter_accepts_legacy_and_v1_records():
    """T-F7-21 舊 JSON 與 v1 包裝得到一致建議。"""
    from dataclasses import asdict
    from f7_system import searchBestTimetables
    from scheduler.storage_bridge import legacy_views

    data = catalog()
    views = legacy_views(data)
    criteria = FilterCriteria(["CS102"], ["CS101"], 6, 6)
    old = searchBestTimetables("s001", criteria, views["courses"], views["students"], [], [])
    wrap = lambda rows: {"schema_version": 1, "records": rows}
    new = searchBestTimetables("S001", criteria, wrap([asdict(c) for c in data.courses.values()]),
                               wrap([asdict(s) for s in data.students.values()]), wrap([]), wrap([]))
    assert old.ok and new.ok
    assert old.data.schedules == new.data.schedules


@pytest.mark.error
def test_adapter_returns_error_for_bad_records():
    """T-F7-22 舊資料轉接失敗仍回傳 Result。"""
    from f7_system import searchBestTimetables
    result = searchBestTimetables("S001", {}, [{"code": "CS101"}], [], [], [])
    assert not result.ok and result.errors[0].code == "INVALID_VALUE"


@pytest.mark.normal
def test_report_contains_scores_grid_and_exclusion_reasons():
    """T-F7-23 報告呈現完整課表、排名、評分與排除原因。"""
    from scheduler.optimizer_display import format_optimizer_report
    result = search_best_timetables(catalog(), "S001", FilterCriteria(["CS102", "ZZ999"], ["CS101"], 6, 6))
    text = format_optimizer_report(result)
    assert all(s in text for s in ["第 1 名", "總學分 6", "CS101", "CS102", "空堂", "NOT_FOUND", "星期日"])
    error = search_best_timetables(catalog(), "S999", {})
    assert "NOT_FOUND" in format_optimizer_report(error)


@pytest.mark.normal
def test_v1_cli_search_is_available_in_read_only_mode(monkeypatch, capsys, tmp_path):
    """T-F7-24 v1 選單搜尋可於唯讀狀態操作，不呼叫存檔。"""
    from scheduler import cli
    data = catalog()
    before = deepcopy(data)
    answers = iter(["9", "S001", "CS102", "CS101", "6", "6", "5-*", "1", "", "1", "", "0"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(cli, "save_all", lambda *_: pytest.fail("搜尋不應存檔"))
    cli.run(data, str(tmp_path), writable=False)
    assert "可行課表共 1 組" in capsys.readouterr().out
    assert data == before and not list(tmp_path.iterdir())


@pytest.mark.normal
def test_legacy_cli_search(monkeypatch, capsys):
    """T-F7-25 舊選單第 12 項也能使用 F7，不儲存 JSON。"""
    import f1_system
    from scheduler.cli import run_legacy
    from scheduler.storage_bridge import legacy_views

    views = legacy_views(catalog())
    monkeypatch.setattr(f1_system, "loadData", lambda path: views[path.removesuffix(".json")])
    answers = iter(["12", "S001", "CS102", "CS101", "6", "6", "", "", "", "", "", "0"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    run_legacy()
    assert "可行課表共 1 組" in capsys.readouterr().out


@pytest.mark.error
def test_cli_invalid_numeric_input_does_not_crash(monkeypatch, capsys):
    """T-F7-26 CLI 非法數字顯示錯誤並返回。"""
    from scheduler.cli import run_optimizer
    answers = iter(["S001", "", "", "abc", "", "", "", "", "", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    run_optimizer(catalog())
    assert "INVALID_VALUE" in capsys.readouterr().out


@pytest.mark.normal
@pytest.mark.parametrize("seed", [7, 19, 41])
def test_varied_credits_and_multislot_catalog_match_oracle(seed):
    """T-F7-27 多時段及不同學分的小型資料，逐組與獨立答案比對。"""
    import random
    rng = random.Random(seed)
    data = SystemData(students={"S001": Student("S001", "學生", "資工一", 24)})
    for i in range(8):
        code = f"CS{101+i}"
        slots = sorted({f"{rng.randint(1, 3)}-{rng.randint(1, 5)}" for _ in range(2)})
        data.courses[code] = Course(code, code, rng.randint(1, 6), "elective", "教師", 10, "EE-101", slots)
    names = sorted(data.courses)
    expected = set()
    for size in range(9):
        for subset in combinations(names, size):
            slots = [slot for code in subset for slot in data.courses[code].slots]
            credits = sum(data.courses[code].credits for code in subset)
            if "CS101" in subset and len(slots) == len(set(slots)) and 5 <= credits <= 12:
                expected.add(tuple(subset))
    result = search_best_timetables(data, "S001", FilterCriteria(names, ["CS101"], 5, 12), top_k=None)
    assert {tuple(option.course_codes) for option in result.data.schedules} == expected
    assert result.data.feasible_count == len(expected)


@pytest.mark.error
def test_maximum_cannot_exceed_student_limit():
    """T-F7-28 條件上限高於學生學分上限必須拒絕。"""
    result = search_best_timetables(catalog(), "S001", FilterCriteria([], [], 0, 25))
    assert not result.ok and "CREDIT_RANGE_INVALID" in [e.code for e in result.errors]


@pytest.mark.boundary
def test_last_seat_and_multiple_days_of_same_course():
    """T-F7-29 最後一個名額可用，同門課每個上課時段都納入。"""
    data = catalog()
    data.courses["CS101"].capacity = 1
    data.courses["CS101"].slots = ["1-2", "2-a", "6-c"]
    result = search_best_timetables(data, "S001", FilterCriteria([], ["CS101"], 3, 3))
    assert result.ok
    option = result.data.schedules[0]
    assert option.occupancies[0].slots == frozenset({(1, 1), (2, 9), (6, 11)})
    assert (option.score.days, option.score.gaps, option.score.span) == (3, 0, 3)


@pytest.mark.normal
def test_f6_storage_round_trip_then_f7_search(tmp_path):
    """T-F7-30 F6 初始化、載入後可直接搜尋，搜尋前後五檔完全相同。"""
    from scheduler.storage import initialize_demo, load_all
    assert initialize_demo(tmp_path).ok
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.json")}
    data, report = load_all(tmp_path)
    assert report.safe_to_save
    result = search_best_timetables(data, "S002", FilterCriteria(
        ["CS102", "CS103", "CS104"], ["CS101"], 6, 9, [], [1, 2, 3]))
    assert result.ok and result.data.schedules[0].course_codes == ["CS101", "CS102", "CS103"]
    assert {p.name: p.read_bytes() for p in tmp_path.glob("*.json")} == before


@pytest.mark.normal
def test_cli_accepts_dictionary_records_and_all_results(monkeypatch, capsys):
    """T-F7-31 SystemData 字典資料也能由 CLI 搜尋並顯示所有解。"""
    from dataclasses import asdict
    from scheduler.cli import run_optimizer
    data = catalog()
    data.students = {key: asdict(value) for key, value in data.students.items()}
    answers = iter(["S001", "CS102", "CS101", "6", "", "", "", "", "all", "0,0,0,0,0,0"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    run_optimizer(data)
    assert "可行課表共 1 組" in capsys.readouterr().out
