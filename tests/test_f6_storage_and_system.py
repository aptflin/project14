import json
import os
from pathlib import Path
import pytest
from scheduler.storage import StorageSystemData, load_all, save_all


def _make_valid_dataset() -> StorageSystemData:
    data = StorageSystemData()
    data.classrooms["EE-101"] = {
        "room_id": "EE-101",
        "name": "電機館 101 教室",
        "building": "EE",
        "capacity": 60,
        "equipment": ["projector", "whiteboard"],
        "unavailable_slots": [],
        "status": "active",
    }
    data.classrooms["LIB-101"] = {
        "room_id": "LIB-101",
        "name": "圖書館 101 討論室",
        "building": "LIB",
        "capacity": 30,
        "equipment": ["whiteboard"],
        "unavailable_slots": ["5-a"],
        "status": "active",
    }
    data.courses["CS101"] = {
        "code": "CS101",
        "name": "程式設計(一)",
        "credits": 3,
        "type": "required",
        "teacher": "王大明",
        "capacity": 60,
        "room_id": "EE-101",
        "slots": ["2-3", "2-4", "4-5"],
        "status": "open",
    }
    data.students["S001"] = {
        "student_id": "S001",
        "name": "林小華",
        "dept_year": "資工二",
        "credit_limit": 24,
        "enrolled_courses": ["CS101"],
    }
    data.activities["EV001"] = {
        "activity_id": "EV001",
        "name": "程式設計讀書會",
        "activity_type": "study_group",
        "date": "2026-10-01",
        "start_time": "12:10",
        "end_time": "13:00",
        "recurrence": "weekly",
        "expected_attendees": 20,
        "required_equipment": ["whiteboard"],
        "room_id": "LIB-101",
        "participants": ["S001"],
        "organizer": "資工系學會",
        "status": "scheduled",
    }
    data.enrollment_log.append({
        "timestamp": "2026-10-05T14:30:00",
        "student_id": "S001",
        "course_code": "CS101",
        "action": "add",
        "reason": "",
    })
    return data


def _write_json(path, records):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"schema_version": 1, "records": records}, f, ensure_ascii=False, indent=2)


# =====================================================================
# 一、正常案例（11 個，要求 >= 10）
# =====================================================================

@pytest.mark.normal
def test_n01_save_and_reload_roundtrip(tmp_path):
    """T-F6-N01 儲存後重新載入，五類資料與儲存前完全一致（round-trip）"""
    original = _make_valid_dataset()
    ok, _ = save_all(original, str(tmp_path))
    assert ok is True
    loaded, report = load_all(str(tmp_path))
    assert loaded == original
    assert report.warnings == []


@pytest.mark.normal
def test_n02_json_output_structure_and_utf8(tmp_path):
    """T-F6-N02 確認儲存的 JSON 包含 schema_version=1、records 清單與完整中文字符"""
    original = _make_valid_dataset()
    save_all(original, str(tmp_path))
    raw = (tmp_path / "courses.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["schema_version"] == 1
    assert isinstance(parsed["records"], list)
    assert "程式設計(一)" in raw


@pytest.mark.normal
def test_n03_load_multiple_valid_courses(tmp_path):
    """T-F6-N03 正常載入多筆課程資料並統計成功筆數"""
    data = _make_valid_dataset()
    data.courses["MA101"] = {
        "code": "MA101",
        "name": "微積分",
        "credits": 4,
        "type": "required",
        "teacher": "陳美華",
        "capacity": 50,
        "room_id": "EE-101",
        "slots": ["3-1", "3-2"],
        "status": "open",
    }
    save_all(data, str(tmp_path))
    loaded, report = load_all(str(tmp_path))
    assert len(loaded.courses) == 2
    assert report.summaries["courses.json"].success_count == 2


@pytest.mark.normal
def test_n04_normalize_lowercase_ids_and_slots(tmp_path):
    """T-F6-N04 載入時自動將代號轉大寫、時段節次轉小寫"""
    _write_json(tmp_path / "classrooms.json", [{
        "room_id": "ee-101", "name": "電機101", "building": "ee",
        "capacity": 40, "equipment": ["projector"], "unavailable_slots": ["5-A"], "status": "active"
    }])
    _write_json(tmp_path / "courses.json", [{
        "code": "cs101", "name": "程設", "credits": 3, "type": "required",
        "teacher": "王師", "capacity": 30, "room_id": "ee-101", "slots": ["2-A"], "status": "open"
    }])
    loaded, _ = load_all(str(tmp_path))
    assert "EE-101" in loaded.classrooms
    assert loaded.classrooms["EE-101"]["unavailable_slots"] == ["5-a"]
    assert "CS101" in loaded.courses
    assert loaded.courses["CS101"]["slots"] == ["2-a"]


@pytest.mark.normal
def test_n05_activity_with_null_room_id(tmp_path):
    """T-F6-N05 尚未配置教室（room_id 為 null）的活動可正常載入"""
    data = _make_valid_dataset()
    data.activities["EV001"]["room_id"] = None
    save_all(data, str(tmp_path))
    loaded, report = load_all(str(tmp_path))
    assert loaded.activities["EV001"]["room_id"] is None
    assert report.summaries["activities.json"].success_count == 1


@pytest.mark.normal
def test_n06_enrollment_actions_all_types(tmp_path):
    """T-F6-N06 選課紀錄支援 add、drop、auto_drop 三種動作類型"""
    data = _make_valid_dataset()
    data.enrollment_log.extend([
        {"timestamp": "2026-10-06T10:00:00", "student_id": "S001", "course_code": "CS101", "action": "drop", "reason": "退選"},
        {"timestamp": "2026-10-07T10:00:00", "student_id": "S001", "course_code": "CS101", "action": "auto_drop", "reason": "課程取消"},
    ])
    save_all(data, str(tmp_path))
    loaded, report = load_all(str(tmp_path))
    assert len(loaded.enrollment_log) == 3
    assert report.summaries["enrollments.json"].success_count == 3


@pytest.mark.normal
def test_n07_overwrite_existing_files_cleanly(tmp_path):
    """T-F6-N07 重複執行 save_all 可正確覆蓋舊資料且不殘留暫存檔"""
    data = _make_valid_dataset()
    save_all(data, str(tmp_path))
    data.students["S001"]["name"] = "林大華"
    save_all(data, str(tmp_path))
    loaded, _ = load_all(str(tmp_path))
    assert loaded.students["S001"]["name"] == "林大華"
    tmp_files = [f for f in os.listdir(tmp_path) if f.startswith(".tmp_")]
    assert tmp_files == []


@pytest.mark.normal
def test_n08_load_report_human_readable_output(tmp_path):
    """T-F6-N08 載入報告 format_text() 正確產生五個檔案的中文摘要"""
    data = _make_valid_dataset()
    save_all(data, str(tmp_path))
    _, report = load_all(str(tmp_path))
    text = report.format_text()
    assert "資料載入報告" in text
    assert "courses.json" in text
    assert "讀取 1 筆，成功 1 筆，略過 0 筆" in text


@pytest.mark.normal
def test_n09_student_with_empty_enrolled_courses(tmp_path):
    """T-F6-N09 未選任何課程的學生資料可正常儲存與載入"""
    data = _make_valid_dataset()
    data.students["S002"] = {
        "student_id": "S002", "name": "陳同學", "dept_year": "電機一",
        "credit_limit": 25, "enrolled_courses": []
    }
    save_all(data, str(tmp_path))
    loaded, _ = load_all(str(tmp_path))
    assert loaded.students["S002"]["enrolled_courses"] == []


@pytest.mark.normal
def test_n10_cancelled_course_and_activity_persist(tmp_path):
    """T-F6-N10 狀態為 cancelled 的課程與活動可正確保存與載入"""
    data = _make_valid_dataset()
    data.courses["CS101"]["status"] = "cancelled"
    data.activities["EV001"]["status"] = "cancelled"
    save_all(data, str(tmp_path))
    loaded, _ = load_all(str(tmp_path))
    assert loaded.courses["CS101"]["status"] == "cancelled"
    assert loaded.activities["EV001"]["status"] == "cancelled"


@pytest.mark.normal
def test_n11_deduplicate_enrolled_courses_on_load(tmp_path):
    """T-F6-N11 學生已選課程清單若含重複代號，載入時自動去重並保持順序"""
    data = _make_valid_dataset()
    save_all(data, str(tmp_path))
    _write_json(tmp_path / "students.json", [{
        "student_id": "S001", "name": "林小華", "dept_year": "資工二",
        "credit_limit": 24, "enrolled_courses": ["CS101", "CS101"]
    }])
    loaded, _ = load_all(str(tmp_path))
    assert loaded.students["S001"]["enrolled_courses"] == ["CS101"]


# =====================================================================
# 二、邊界案例（11 個，要求 >= 10）
# =====================================================================

@pytest.mark.boundary
def test_b01_missing_all_files_starts_empty(tmp_path):
    """T-F6-B01 資料夾完全無檔案時以空資料啟動並標記 file_missing"""
    loaded, report = load_all(str(tmp_path))
    assert loaded.courses == {}
    assert loaded.students == {}
    assert all(s.file_missing for s in report.summaries.values())


@pytest.mark.boundary
def test_b02_empty_records_list_in_all_files(tmp_path):
    """T-F6-B02 檔案存在但 records 為空陣列 [] 時正常載入 0 筆"""
    empty_data = StorageSystemData()
    save_all(empty_data, str(tmp_path))
    loaded, report = load_all(str(tmp_path))
    assert loaded == empty_data
    assert report.summaries["courses.json"].total_read == 0
    assert report.summaries["courses.json"].success_count == 0


@pytest.mark.boundary
def test_b03_credits_min_1_and_max_6_accepted(tmp_path):
    """T-F6-B03 課程學分邊界值 1 與 6 皆應合法通過"""
    data = _make_valid_dataset()
    data.courses["CS101"]["credits"] = 1
    data.courses["CS102"] = {**data.courses["CS101"], "code": "CS102", "credits": 6}
    save_all(data, str(tmp_path))
    loaded, _ = load_all(str(tmp_path))
    assert loaded.courses["CS101"]["credits"] == 1
    assert loaded.courses["CS102"]["credits"] == 6


@pytest.mark.boundary
def test_b04_student_credit_limit_min_1_and_max_30(tmp_path):
    """T-F6-B04 學生學分上限邊界值 1 與 30 皆應合法通過"""
    data = _make_valid_dataset()
    data.students["S001"]["credit_limit"] = 1
    data.students["S002"] = {
        "student_id": "S002", "name": "邊界生", "dept_year": "資工一",
        "credit_limit": 30, "enrolled_courses": []
    }
    save_all(data, str(tmp_path))
    loaded, _ = load_all(str(tmp_path))
    assert loaded.students["S001"]["credit_limit"] == 1
    assert loaded.students["S002"]["credit_limit"] == 30


@pytest.mark.boundary
def test_b05_course_capacity_equals_classroom_capacity(tmp_path):
    """T-F6-B05 課程人數上限剛好等於教室容量（60=60）與最小值 1 皆合法"""
    data = _make_valid_dataset()
    data.courses["CS101"]["capacity"] = 60
    data.courses["CS102"] = {**data.courses["CS101"], "code": "CS102", "capacity": 1}
    save_all(data, str(tmp_path))
    loaded, _ = load_all(str(tmp_path))
    assert len(loaded.courses) == 2


@pytest.mark.boundary
def test_b06_slot_extremes_1_1_and_7_c(tmp_path):
    """T-F6-B06 時段邊界 1-1（週一第1節）與 7-c（週日第12節）皆合法"""
    data = _make_valid_dataset()
    data.courses["CS101"]["slots"] = ["1-1", "7-c"]
    save_all(data, str(tmp_path))
    loaded, _ = load_all(str(tmp_path))
    assert loaded.courses["CS101"]["slots"] == ["1-1", "7-c"]


@pytest.mark.boundary
def test_b07_activity_time_boundaries_0810_to_2000(tmp_path):
    """T-F6-B07 活動時間邊界 08:10 與 20:00 合法通過"""
    data = _make_valid_dataset()
    data.activities["EV001"]["start_time"] = "08:10"
    data.activities["EV001"]["end_time"] = "20:00"
    save_all(data, str(tmp_path))
    loaded, _ = load_all(str(tmp_path))
    assert loaded.activities["EV001"]["start_time"] == "08:10"
    assert loaded.activities["EV001"]["end_time"] == "20:00"


@pytest.mark.boundary
def test_b08_name_length_1_and_50_chars(tmp_path):
    """T-F6-B08 名稱長度邊界 1 字元與 50 字元皆合法"""
    data = _make_valid_dataset()
    data.courses["CS101"]["name"] = "A"
    data.courses["CS102"] = {**data.courses["CS101"], "code": "CS102", "name": "課" * 50}
    save_all(data, str(tmp_path))
    loaded, _ = load_all(str(tmp_path))
    assert len(loaded.courses["CS101"]["name"]) == 1
    assert len(loaded.courses["CS102"]["name"]) == 50


@pytest.mark.boundary
def test_b09_id_prefix_length_2_and_4_letters(tmp_path):
    """T-F6-B09 代號英文字母長度邊界（2碼 CS101 與 4碼 MATH101）皆合法"""
    data = _make_valid_dataset()
    data.courses["MATH101"] = {**data.courses["CS101"], "code": "MATH101"}
    save_all(data, str(tmp_path))
    loaded, _ = load_all(str(tmp_path))
    assert "CS101" in loaded.courses
    assert "MATH101" in loaded.courses


@pytest.mark.boundary
def test_b10_single_corrupt_record_among_many_valid(tmp_path):
    """T-F6-B10 10 筆資料中僅 1 筆錯誤時，其餘 9 筆全部保留"""
    data = _make_valid_dataset()
    save_all(data, str(tmp_path))
    courses = [{**data.courses["CS101"], "code": f"CS10{i}"} for i in range(9)]
    courses.append({**data.courses["CS101"], "code": "CS199", "slots": ["8-3"]})
    _write_json(tmp_path / "courses.json", courses)
    loaded, report = load_all(str(tmp_path))
    assert len(loaded.courses) == 9
    assert len(report.summaries["courses.json"].skipped) == 1


@pytest.mark.boundary
def test_b11_partial_missing_files_loads_existing_ones(tmp_path):
    """T-F6-B11 僅存在部分檔案（如 activities.json 缺失）時不影響其他檔案載入"""
    data = _make_valid_dataset()
    save_all(data, str(tmp_path))
    os.remove(tmp_path / "activities.json")
    loaded, report = load_all(str(tmp_path))
    assert len(loaded.courses) == 1
    assert loaded.activities == {}
    assert report.summaries["activities.json"].file_missing is True


# =====================================================================
# 三、錯誤及衝突案例（11 個，要求 >= 10）
# =====================================================================

@pytest.mark.error
def test_e01_corrupt_json_syntax_backed_up_and_continues(tmp_path):
    """T-F6-E01 JSON 語法毀損時備份為 .corrupt-時間戳，程式不崩潰"""
    data = _make_valid_dataset()
    save_all(data, str(tmp_path))
    (tmp_path / "courses.json").write_text("{ invalid json !!!", encoding="utf-8")
    loaded, report = load_all(str(tmp_path))
    assert loaded.courses == {}
    backup = report.summaries["courses.json"].corrupt_backup
    assert backup is not None and backup.startswith("courses.json.corrupt-")
    assert (tmp_path / backup).exists()


@pytest.mark.error
def test_e02_missing_required_field_skipped(tmp_path):
    """T-F6-E02 單筆紀錄缺少必填欄位（MISSING_FIELD）時略過該筆並記錄"""
    data = _make_valid_dataset()
    save_all(data, str(tmp_path))
    broken = dict(data.courses["CS101"])
    del broken["credits"]
    _write_json(tmp_path / "courses.json", [broken])
    loaded, report = load_all(str(tmp_path))
    assert loaded.courses == {}
    assert report.summaries["courses.json"].skipped[0].code == "MISSING_FIELD"


@pytest.mark.error
def test_e03_wrong_field_types_rejected(tmp_path):
    """T-F6-E03 欄位型別錯誤（如學分為字串或布林值 True）時拒絕該筆"""
    data = _make_valid_dataset()
    save_all(data, str(tmp_path))
    c1 = {**data.courses["CS101"], "code": "CS101", "credits": "3"}
    c2 = {**data.courses["CS101"], "code": "CS102", "credits": True}
    _write_json(tmp_path / "courses.json", [c1, c2])
    loaded, report = load_all(str(tmp_path))
    assert loaded.courses == {}
    assert len(report.summaries["courses.json"].skipped) == 2


@pytest.mark.error
def test_e04_invalid_slot_formats_rejected(tmp_path):
    """T-F6-E04 非法時段（8-3、2-0、2-d、23）皆被攔截並記錄 INVALID_SLOT"""
    data = _make_valid_dataset()
    save_all(data, str(tmp_path))
    bad_slots = ["8-3", "2-0", "2-d", "23"]
    records = [{**data.courses["CS101"], "code": f"CS10{i}", "slots": [s]} for i, s in enumerate(bad_slots)]
    _write_json(tmp_path / "courses.json", records)
    loaded, report = load_all(str(tmp_path))
    assert loaded.courses == {}
    assert all(x.code == "INVALID_SLOT" for x in report.summaries["courses.json"].skipped)


@pytest.mark.error
def test_e05_duplicate_course_id_skipped(tmp_path):
    """T-F6-E05 重複課程代號（DUPLICATE_ID）保留第一筆、略過後續重複筆"""
    data = _make_valid_dataset()
    save_all(data, str(tmp_path))
    c1 = {**data.courses["CS101"], "name": "第一筆"}
    c2 = {**data.courses["CS101"], "name": "重複筆"}
    _write_json(tmp_path / "courses.json", [c1, c2])
    loaded, report = load_all(str(tmp_path))
    assert loaded.courses["CS101"]["name"] == "第一筆"
    assert report.summaries["courses.json"].skipped[0].code == "DUPLICATE_ID"


@pytest.mark.error
def test_e06_course_references_nonexistent_room(tmp_path):
    """T-F6-E06 課程指定不存在的教室（REFERENCE_MISSING）時略過該課程"""
    data = _make_valid_dataset()
    save_all(data, str(tmp_path))
    bad_course = {**data.courses["CS101"], "room_id": "ZZ-999"}
    _write_json(tmp_path / "courses.json", [bad_course])
    loaded, report = load_all(str(tmp_path))
    assert loaded.courses == {}
    assert report.summaries["courses.json"].skipped[0].code == "REFERENCE_MISSING"


@pytest.mark.error
def test_e07_student_enrolled_nonexistent_or_cancelled_course_cleaned(tmp_path):
    """T-F6-E07 學生已選課程參照不存在或已取消課程時，移除該參照並產生警告"""
    data = _make_valid_dataset()
    data.courses["CS102"] = {**data.courses["CS101"], "code": "CS102", "status": "cancelled"}
    data.students["S001"]["enrolled_courses"] = ["CS101", "CS102", "CS999"]
    save_all(data, str(tmp_path))
    loaded, report = load_all(str(tmp_path))
    assert loaded.students["S001"]["enrolled_courses"] == ["CS101"]
    assert len(report.warnings) == 2


@pytest.mark.error
def test_e08_activity_participant_nonexistent_student_cleaned(tmp_path):
    """T-F6-E08 活動報名者包含不存在學號時，自動移除該學號並記錄警告"""
    data = _make_valid_dataset()
    data.activities["EV001"]["participants"] = ["S001", "S999"]
    save_all(data, str(tmp_path))
    loaded, report = load_all(str(tmp_path))
    assert loaded.activities["EV001"]["participants"] == ["S001"]
    assert any("S999" in w for w in report.warnings)


@pytest.mark.error
def test_e09_enrollment_log_missing_reference_skipped(tmp_path):
    """T-F6-E09 選課紀錄參照不存在的課程或學生時，略過該筆紀錄"""
    data = _make_valid_dataset()
    data.enrollment_log.append({
        "timestamp": "2026-10-05T15:00:00",
        "student_id": "S001",
        "course_code": "CS999",
        "action": "add",
        "reason": "",
    })
    save_all(data, str(tmp_path))
    loaded, report = load_all(str(tmp_path))
    assert len(loaded.enrollment_log) == 1
    assert report.summaries["enrollments.json"].skipped[0].code == "REFERENCE_MISSING"


@pytest.mark.error
def test_e10_course_capacity_exceeds_room_capacity_rejected(tmp_path):
    """T-F6-E10 課程人數上限超過所屬教室容量（如 61 > 60）時拒絕載入"""
    data = _make_valid_dataset()
    data.courses["CS101"]["capacity"] = 61
    save_all(data, str(tmp_path))
    loaded, report = load_all(str(tmp_path))
    assert loaded.courses == {}
    assert report.summaries["courses.json"].skipped[0].code == "RECORD_INVALID"


@pytest.mark.error
def test_e11_save_all_handles_os_error_gracefully(tmp_path):
    """T-F6-E11 寫入目標為非法路徑時回傳失敗狀態而非未捕捉例外"""
    file_as_dir = tmp_path / "not_a_dir"
    file_as_dir.write_text("block", encoding="utf-8")
    ok, msg = save_all(_make_valid_dataset(), str(file_as_dir))
    assert ok is False
    assert "SAVE_FAILED" in msg


@pytest.mark.error
def test_broken_courses_fixture_keeps_valid_record_and_reports_invalid_records(tmp_path):
    """混合損壞課程 fixture 時保留有效資料並回報各筆錯誤"""
    _write_json(tmp_path / "classrooms.json", [{
        "room_id": "EE-101", "name": "電機館 101 教室", "building": "EE",
        "capacity": 60, "equipment": [], "unavailable_slots": [], "status": "active"
    }])
    fixture = Path(__file__).parent / "fixtures" / "broken" / "courses.json"
    (tmp_path / "courses.json").write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    loaded, report = load_all(str(tmp_path))

    assert list(loaded.courses) == ["CS101"]
    assert [item.code for item in report.summaries["courses.json"].skipped] == [
        "MISSING_FIELD", "RECORD_INVALID", "INVALID_SLOT", "DUPLICATE_ID"
    ]
