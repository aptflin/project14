"""F6 缺口驗收：真實型別錯誤、I/O 故障、跨模組與 CLI 自動儲存。"""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scheduler import storage
from scheduler.cli import commit_operation
from scheduler.course_filter import filter_courses
from scheduler.models import Activity, Course, FilterCriteria, Student, SystemData
from scheduler.operations import apply_operation
from scheduler.result import ErrorItem, Result
from scheduler.sample_data import create_sample_data


@pytest.fixture
def storage_data():
    return create_sample_data()


def write_records(folder, name, rows, version=1):
    (folder / name).write_text(json.dumps({"schema_version": version, "records": rows}), encoding="utf-8")


def snapshot(folder):
    return {path.name: path.read_bytes() for path in folder.glob("*.json")}


@pytest.mark.normal
def test_result_contract_and_legacy_unpacking(storage_data, tmp_path):
    """T-F6-N12 儲存回傳 Result，保留舊 tuple 拆包相容性。"""
    result = storage.save_all(storage_data, tmp_path)
    assert isinstance(result, Result) and result.ok
    ok, message = result
    assert ok and "成功" in message
    loaded, _ = storage.load_all(tmp_path)
    assert isinstance(loaded, SystemData)


@pytest.mark.normal
def test_model_dataclasses_roundtrip(tmp_path):
    """T-F6-N13 公開 SystemData 的 dataclass 紀錄可完整往返。"""
    data = SystemData(
        courses={"CS101": Course("CS101", "課程", 3, "required", "老師", 10, "EE-101", ["1-1"])},
        students={"S001": Student("S001", "同學", "資工二", 25, ["CS101"])},
        classrooms={"EE-101": {"room_id": "EE-101", "name": "教室", "building": "EE", "capacity": 30,
                               "equipment": [], "unavailable_slots": [], "status": "active"}},
        activities={"EV001": Activity("EV001", "讀書會", "2026-11-23", "13:10", "14:00",
                                        participants=["S001"], organizer="學會")},
    )
    assert storage.save_all(data, tmp_path).ok
    loaded, report = storage.load_all(tmp_path)
    assert report.safe_to_save and not report.warnings
    assert loaded == data


@pytest.mark.normal
def test_loaded_storage_data_works_with_f5(storage_data, tmp_path):
    """T-F6-N14 儲存載入的 SystemData 可直接供 F5 使用。"""
    assert storage.save_all(storage_data, tmp_path).ok
    loaded, _ = storage.load_all(tmp_path)
    result = filter_courses(loaded, "S001", FilterCriteria(["CS101"], [], 1, 20))
    assert result.ok and result.data.available_credits == 1


@pytest.mark.normal
def test_successful_add_drop_persists_history(storage_data, tmp_path):
    """T-F6-N15 成功加退選自動儲存五檔，歷程只追加且重啟後一致。"""
    original = deepcopy(storage_data)
    action = apply_operation(storage_data, "add", "s001", "cs101")
    assert action.ok and storage_data == original
    assert commit_operation(storage_data, action, tmp_path).ok
    loaded, _ = storage.load_all(tmp_path)
    assert loaded.students["S001"]["enrolled_courses"] == ["CS101"]
    assert loaded.enrollment_log[-1]["action"] == "add"
    assert commit_operation(storage_data, apply_operation(storage_data, "drop", "S001", "CS101"), tmp_path).ok
    loaded, _ = storage.load_all(tmp_path)
    assert loaded.students["S001"]["enrolled_courses"] == []
    assert [entry["action"] for entry in loaded.enrollment_log] == ["add", "drop"]


@pytest.mark.boundary
def test_failed_business_operation_creates_no_files(storage_data, tmp_path):
    """T-F6-B12 業務錯誤不觸發儲存。"""
    action = apply_operation(storage_data, "add", "S001", "missing")
    assert not commit_operation(storage_data, action, tmp_path).ok
    assert list(tmp_path.iterdir()) == []


@pytest.mark.error
def test_save_failure_preserves_in_memory_session(storage_data, tmp_path, monkeypatch):
    """T-F6-E13 寫入失敗不得先改掉記憶體選課結果。"""
    before = deepcopy(storage_data)
    monkeypatch.setattr("scheduler.cli.save_all", lambda *_: Result(False, errors=[ErrorItem("SAVE_FAILED", "模擬磁碟錯誤")]))
    assert not commit_operation(storage_data, apply_operation(storage_data, "add", "S001", "CS101"), tmp_path).ok
    assert storage_data == before and list(tmp_path.iterdir()) == []


@pytest.mark.error
def test_replace_failure_rolls_back_all_five_files(storage_data, tmp_path, monkeypatch):
    """T-F6-E14 第三個取代失敗時，已取代檔案也須還原。"""
    assert storage.save_all(storage_data, tmp_path).ok
    before = snapshot(tmp_path)
    storage_data.classrooms["EE-101"]["name"] = "變更教室"
    storage_data.courses["CS101"]["name"] = "變更課程"
    original_replace = storage.os.replace
    failed = False
    def fail_once(source, target):
        nonlocal failed
        if Path(target).name == "students.json" and not failed:
            failed = True
            raise OSError("模擬第三檔失敗")
        return original_replace(source, target)
    monkeypatch.setattr(storage.os, "replace", fail_once)
    result = storage.save_all(storage_data, tmp_path)
    assert not result.ok and result.errors[0].code == "SAVE_FAILED"
    assert snapshot(tmp_path) == before
    assert not list(tmp_path.glob(".tmp_*")) and not list(tmp_path.glob(".rollback_*"))


@pytest.mark.error
def test_unserializable_record_does_not_modify_any_file(storage_data, tmp_path):
    """T-F6-E15 序列化失敗不會留下部分新檔。"""
    storage.save_all(storage_data, tmp_path)
    before = snapshot(tmp_path)
    storage_data.students["S001"]["unserializable"] = object()
    result = storage.save_all(storage_data, tmp_path)
    assert not result.ok and result.errors[0].code == "SAVE_FAILED"
    assert snapshot(tmp_path) == before


@pytest.mark.error
@pytest.mark.parametrize("field,value", [("type", []), ("status", {}), ("name", None), ("slots", [None]), ("credits", {})])
def test_unhashable_or_nested_bad_course_does_not_abort_load(storage_data, tmp_path, field, value):
    """T-F6-E16 深層型別錯誤只略過該筆，後續有效紀錄保留。"""
    storage.save_all(storage_data, tmp_path)
    valid = storage_data.courses["CS101"]
    write_records(tmp_path, "courses.json", [dict(valid, **{field: value}), dict(valid, code="CS999")])
    loaded, report = storage.load_all(tmp_path)
    assert list(loaded.courses) == ["CS999"]
    assert len(report.summaries["courses.json"].skipped) == 1


@pytest.mark.error
@pytest.mark.parametrize("field,value", [("equipment", [{}]), ("status", []), ("capacity", True)])
def test_bad_classroom_type_is_reported(storage_data, tmp_path, field, value):
    """T-F6-E17 教室錯誤型別不使整個載入中止。"""
    storage.save_all(storage_data, tmp_path)
    write_records(tmp_path, "classrooms.json", [dict(storage_data.classrooms["EE-101"], **{field: value})])
    loaded, report = storage.load_all(tmp_path)
    assert loaded.classrooms == {}
    assert len(report.summaries["classrooms.json"].skipped) == 1


@pytest.mark.error
@pytest.mark.parametrize("field,value", [("required_equipment", [{}]), ("activity_type", []), ("status", {}),
                                         ("start_time", "13:99"), ("date", "2026-2-3")])
def test_bad_activity_value_is_skipped(storage_data, tmp_path, field, value):
    """T-F6-E18 活動無效日期、時分與型別均拒絕該筆。"""
    storage.save_all(storage_data, tmp_path)
    activity = storage_data.activities["EV001"]
    write_records(tmp_path, "activities.json", [dict(activity, **{field: value}), dict(activity, activity_id="EV999")])
    loaded, report = storage.load_all(tmp_path)
    assert list(loaded.activities) == ["EV999"]
    assert len(report.summaries["activities.json"].skipped) == 1


@pytest.mark.error
@pytest.mark.parametrize("version", [None, True, 0, 2, "1"])
def test_unsupported_schema_is_read_only_and_original_unchanged(tmp_path, version):
    """T-F6-E19 不支援版本不得改名或當成空資料直接覆寫。"""
    write_records(tmp_path, "courses.json", [], version)
    before = (tmp_path / "courses.json").read_bytes()
    _, report = storage.load_all(tmp_path)
    assert not report.safe_to_save
    assert report.summaries["courses.json"].errors[0].code == "RECORD_INVALID"
    assert (tmp_path / "courses.json").read_bytes() == before


@pytest.mark.error
def test_read_permission_error_returns_report(tmp_path, monkeypatch):
    """T-F6-E20 檔案讀取權限錯誤回報，不拋到選單。"""
    path = tmp_path / "courses.json"
    write_records(tmp_path, "courses.json", [])
    original = open
    def denied(name, *args, **kwargs):
        if Path(name) == path:
            raise PermissionError("模擬無法讀取")
        return original(name, *args, **kwargs)
    monkeypatch.setattr("builtins.open", denied)
    _, report = storage.load_all(tmp_path)
    assert not report.safe_to_save
    assert report.summaries["courses.json"].errors


@pytest.mark.error
def test_corrupt_backup_failure_preserves_original(tmp_path, monkeypatch):
    """T-F6-E21 毀損備份無權限時保留原檔、回報且不中止。"""
    path = tmp_path / "courses.json"
    path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(storage.os, "replace", lambda *_: (_ for _ in ()).throw(PermissionError("拒絕搬移")))
    _, report = storage.load_all(tmp_path)
    assert path.read_text(encoding="utf-8") == "{broken"
    assert not report.safe_to_save
    assert {error.code for error in report.summaries["courses.json"].errors} == {"JSON_SYNTAX", "SAVE_FAILED"}


@pytest.mark.error
def test_activity_participant_count_must_not_exceed_capacity(storage_data, tmp_path):
    """T-F6-E22 有效報名名單超過活動上限時拒絕載入該活動。"""
    storage_data.activities["EV001"]["expected_attendees"] = 1
    storage_data.activities["EV001"]["participants"] = ["S001", "S002"]
    storage.save_all(storage_data, tmp_path)
    loaded, report = storage.load_all(tmp_path)
    assert "EV001" not in loaded.activities
    assert report.summaries["activities.json"].skipped[0].code == "RECORD_INVALID"


@pytest.mark.boundary
def test_runtime_activity_cache_is_not_persisted(storage_data, tmp_path):
    """T-F6-B13 活動時段快取與學生衍生報名清單不得寫入 JSON。"""
    storage_data.activities["EV001"]["slots"] = ["1-1"]
    storage_data.students["S001"]["enrolled_activities"] = ["EV001"]
    storage.save_all(storage_data, tmp_path)
    assert "slots" not in json.loads((tmp_path / "activities.json").read_text(encoding="utf-8"))["records"][0]
    assert "enrolled_activities" not in json.loads((tmp_path / "students.json").read_text(encoding="utf-8"))["records"][0]


@pytest.mark.normal
def test_cli_autosaves_and_reloads(storage_data, tmp_path):
    """T-F6-N16 從程式入口加選，再重新載入可見結果及紀錄。"""
    storage.save_all(storage_data, tmp_path)
    script = Path(__file__).resolve().parents[1] / "main.py"
    run = subprocess.run([sys.executable, "-B", "-X", "utf8", str(script), "--data-dir", str(tmp_path)],
                         input="2\nS001\nCS101\n0\n", text=True, encoding="utf-8", capture_output=True, timeout=15)
    assert run.returncode == 0, run.stderr
    assert "資料載入報告" in run.stdout and "操作成功，已儲存五類資料" in run.stdout
    loaded, _ = storage.load_all(tmp_path)
    assert loaded.students["S001"]["enrolled_courses"] == ["CS101"]
    assert loaded.enrollment_log[-1]["action"] == "add"


@pytest.mark.boundary
def test_demo_initializer_never_overwrites_existing_files(tmp_path):
    """T-F6-B14 示範資料產生器保護既有資料。"""
    assert storage.initialize_demo(tmp_path).ok
    before = snapshot(tmp_path)
    assert not storage.initialize_demo(tmp_path).ok
    assert snapshot(tmp_path) == before
    loaded, _ = storage.load_all(tmp_path)
    assert (len(loaded.courses), len(loaded.students), len(loaded.classrooms), len(loaded.activities)) == (20, 15, 5, 10)


@pytest.mark.error
def test_nonfinite_json_is_backed_up(tmp_path):
    """T-F6-E23 非標準 NaN JSON 保留原始 bytes 並回報。"""
    raw = b'{"schema_version":1,"records":[NaN]}'
    (tmp_path / "courses.json").write_bytes(raw)
    _, report = storage.load_all(tmp_path)
    summary = report.summaries["courses.json"]
    assert summary.errors[0].code == "JSON_SYNTAX"
    assert (tmp_path / summary.corrupt_backup).read_bytes() == raw


@pytest.mark.error
def test_staging_failure_never_starts_replacement(storage_data, tmp_path, monkeypatch):
    """T-F6-E24 暫存檔寫入階段失敗，五份原檔全部不動。"""
    storage.save_all(storage_data, tmp_path)
    before = snapshot(tmp_path)
    original_stage = storage._stage_bytes
    writes = 0
    def fail_second_new_file(folder, content, prefix):
        nonlocal writes
        if prefix == ".tmp_":
            writes += 1
            if writes == 2:
                raise OSError("模擬暫存空間不足")
        return original_stage(folder, content, prefix)
    monkeypatch.setattr(storage, "_stage_bytes", fail_second_new_file)
    assert not storage.save_all(storage_data, tmp_path).ok
    assert snapshot(tmp_path) == before
    assert not list(tmp_path.glob(".tmp_*")) and not list(tmp_path.glob(".rollback_*"))


@pytest.mark.error
def test_initial_save_failure_removes_partially_created_files(storage_data, tmp_path, monkeypatch):
    """T-F6-E25 首次儲存中途失敗，不殘留一半的五檔資料。"""
    original = storage.os.replace
    def fail_students(source, target):
        if Path(target).name == "students.json":
            raise OSError("模擬初次儲存失敗")
        return original(source, target)
    monkeypatch.setattr(storage.os, "replace", fail_students)
    assert not storage.save_all(storage_data, tmp_path).ok
    assert list(tmp_path.iterdir()) == []


@pytest.mark.boundary
def test_readonly_cli_cannot_overwrite_after_corrupt_load(storage_data, tmp_path):
    """T-F6-B15 載入毀損資料後，手動儲存也被拒絕。"""
    storage.save_all(storage_data, tmp_path)
    before = snapshot(tmp_path)
    (tmp_path / "activities.json").write_text("{broken", encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "main.py"
    run = subprocess.run([sys.executable, "-B", "-X", "utf8", str(script), "--data-dir", str(tmp_path)],
                         input="8\n0\n", text=True, encoding="utf-8", capture_output=True, timeout=15)
    assert run.returncode == 0 and "拒絕修改與儲存" in run.stdout
    for name, raw in before.items():
        if name != "activities.json":
            assert (tmp_path / name).read_bytes() == raw
    assert list(tmp_path.glob("activities.json.corrupt-*"))[0].read_text(encoding="utf-8") == "{broken"


@pytest.mark.normal
def test_registration_cancellation_persists_participants_only(storage_data, tmp_path):
    """T-F6-N17 報名與取消自動儲存，學生不重複儲存活動名單。"""
    assert commit_operation(storage_data, apply_operation(storage_data, "register", "S001", "EV001"), tmp_path).ok
    loaded, _ = storage.load_all(tmp_path)
    assert loaded.activities["EV001"]["participants"] == ["S001"]
    assert "enrolledActivities" not in asdict(loaded.students["S001"])
    assert commit_operation(storage_data, apply_operation(storage_data, "cancel_activity", code="EV001"), tmp_path).ok
    loaded, _ = storage.load_all(tmp_path)
    assert loaded.activities["EV001"]["status"] == "cancelled"
    assert loaded.activities["EV001"]["participants"] == []


@pytest.mark.boundary
def test_output_ids_and_slots_are_normalized_without_mutation(storage_data, tmp_path):
    """T-F6-B16 存檔代號轉大寫、節次小寫，輸入資料不變。"""
    storage_data.courses["CS101"]["code"] = " cs101 "
    storage_data.courses["CS101"]["slots"] = ["5-A"]
    before = deepcopy(storage_data)
    assert storage.save_all(storage_data, tmp_path).ok
    raw = json.loads((tmp_path / "courses.json").read_text(encoding="utf-8"))["records"][0]
    assert raw["code"] == "CS101" and raw["slots"] == ["5-a"]
    assert storage_data == before


@pytest.mark.error
def test_all_five_error_kinds_in_one_load(storage_data, tmp_path):
    """T-F6-E26 同一份資料的五種錯誤全部出現在載入報告。"""
    storage.save_all(storage_data, tmp_path)
    valid = storage_data.courses["CS101"]
    missing = dict(valid, code="CS102")
    del missing["credits"]
    write_records(tmp_path, "courses.json", [valid, missing, dict(valid, code="CS103", credits="3"),
                   dict(valid, code="CS104", slots=["8-3"]), valid, dict(valid, code="CS105", room_id="ZZ-999")])
    loaded, report = storage.load_all(tmp_path)
    assert list(loaded.courses) == ["CS101"]
    assert [item.code for item in report.summaries["courses.json"].skipped] == [
        "MISSING_FIELD", "RECORD_INVALID", "INVALID_SLOT", "DUPLICATE_ID", "REFERENCE_MISSING"]


@pytest.mark.boundary
def test_enrollment_history_is_append_only(storage_data, tmp_path):
    """T-F6-B17 有效選課歷程不得被刪除或竄改。"""
    storage_data.enrollment_log.append({"timestamp": "2026-11-23T12:00:00", "student_id": "S001",
                                        "course_code": "CS101", "action": "add", "reason": ""})
    assert storage.save_all(storage_data, tmp_path).ok
    before = snapshot(tmp_path)
    storage_data.enrollment_log.clear()
    result = storage.save_all(storage_data, tmp_path)
    assert not result.ok and "只允許追加" in result.errors[0].message
    assert snapshot(tmp_path) == before
