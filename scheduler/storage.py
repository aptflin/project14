import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


VALID_SLOTS_DAYS = set(range(1, 8))
VALID_SLOTS_PERIODS = set(list("123456789abc"))
VALID_EQUIPMENT = {
    "projector", "microphone", "computer",
    "whiteboard", "speaker", "video_conf"
}


@dataclass
class LoadSkipItem:
    index: int
    code: str
    message: str


@dataclass
class FileLoadSummary:
    filename: str
    total_read: int = 0
    success_count: int = 0
    file_missing: bool = False
    corrupt_backup: str | None = None
    skipped: list[LoadSkipItem] = field(default_factory=list)


@dataclass
class LoadReport:
    summaries: dict[str, FileLoadSummary] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def format_text(self) -> str:
        lines = ["資料載入報告"]
        for fname in [
            "courses.json",
            "students.json",
            "classrooms.json",
            "activities.json",
            "enrollments.json",
        ]:
            s = self.summaries.get(fname)
            if not s:
                continue
            if s.file_missing:
                lines.append(f"{fname:<17} 檔案不存在，以空資料開始")
            elif s.corrupt_backup:
                lines.append(
                    f"{fname:<17} JSON 語法毀損，已備份為 {s.corrupt_backup} 並以空資料開始"
                )
            else:
                lines.append(
                    f"{fname:<17} 讀取 {s.total_read} 筆，成功 {s.success_count} 筆，略過 {len(s.skipped)} 筆"
                )
                for item in s.skipped:
                    lines.append(f"  第 {item.index} 筆 [{item.code}] {item.message}")
        for w in self.warnings:
            lines.append(f"[WARNING] {w}")
        return "\n".join(lines)


@dataclass
class StorageSystemData:
    courses: dict[str, dict[str, Any]] = field(default_factory=dict)
    students: dict[str, dict[str, Any]] = field(default_factory=dict)
    classrooms: dict[str, dict[str, Any]] = field(default_factory=dict)
    activities: dict[str, dict[str, Any]] = field(default_factory=dict)
    enrollment_log: list[dict[str, Any]] = field(default_factory=list)


def _is_valid_slot(slot_str: Any) -> bool:
    if not isinstance(slot_str, str):
        return False
    parts = slot_str.strip().lower().split("-")
    if len(parts) != 2:
        return False
    day_s, period_s = parts
    if not day_s.isdigit() or int(day_s) not in VALID_SLOTS_DAYS:
        return False
    return period_s in VALID_SLOTS_PERIODS


def _is_int_strict(val: Any) -> bool:
    return isinstance(val, int) and not isinstance(val, bool)


def _validate_classroom(rec: Any, existing_ids: set[str]) -> tuple[bool, str, str, dict[str, Any]]:
    if not isinstance(rec, dict):
        return False, "RECORD_INVALID", "紀錄必須為 JSON 物件", {}
    required = ["room_id", "name", "building", "capacity", "equipment", "unavailable_slots", "status"]
    for k in required:
        if k not in rec:
            return False, "MISSING_FIELD", f"缺少必填欄位 {k}", {}

    room_id = str(rec["room_id"]).strip().upper()
    if not re.match(r"^[A-Z]{2,4}-[0-9]{3}$", room_id):
        return False, "INVALID_ID_FORMAT", f"教室代號 {room_id} 格式不合法", {}
    if room_id in existing_ids:
        return False, "DUPLICATE_ID", f"教室代號 {room_id} 重複", {}

    if not isinstance(rec["name"], str) or not (1 <= len(rec["name"].strip()) <= 50):
        return False, "RECORD_INVALID", f"{room_id} 名稱長度不合法", {}
    building = str(rec["building"]).strip().upper()
    if building != room_id.split("-")[0]:
        return False, "RECORD_INVALID", f"{room_id} 所屬建築 {building} 與代號前綴不符", {}
    if not _is_int_strict(rec["capacity"]) or rec["capacity"] < 1:
        return False, "RECORD_INVALID", f"{room_id} 容量須為 >= 1 的整數", {}
    if not isinstance(rec["equipment"], list) or any(e not in VALID_EQUIPMENT for e in rec["equipment"]):
        return False, "RECORD_INVALID", f"{room_id} 設備清單包含不合法代碼", {}
    if not isinstance(rec["unavailable_slots"], list) or any(not _is_valid_slot(s) for s in rec["unavailable_slots"]):
        return False, "INVALID_SLOT", f"{room_id} 停用時段格式不合法", {}
    if rec["status"] not in {"active", "disabled"}:
        return False, "RECORD_INVALID", f"{room_id} 狀態不合法", {}

    clean = {
        "room_id": room_id,
        "name": rec["name"].strip(),
        "building": building,
        "capacity": rec["capacity"],
        "equipment": list(dict.fromkeys(rec["equipment"])),
        "unavailable_slots": [s.strip().lower() for s in rec["unavailable_slots"]],
        "status": rec["status"],
    }
    return True, "", "", clean


def _validate_course(
    rec: Any, existing_codes: set[str], classrooms: dict[str, dict[str, Any]]
) -> tuple[bool, str, str, dict[str, Any]]:
    if not isinstance(rec, dict):
        return False, "RECORD_INVALID", "紀錄必須為 JSON 物件", {}
    required = ["code", "name", "credits", "type", "teacher", "capacity", "room_id", "slots", "status"]
    for k in required:
        if k not in rec:
            return False, "MISSING_FIELD", f"缺少必填欄位 {k}", {}

    code = str(rec["code"]).strip().upper()
    if not re.match(r"^[A-Z]{2,4}[0-9]{3}$", code):
        return False, "INVALID_ID_FORMAT", f"課程代號 {code} 格式不合法", {}
    if code in existing_codes:
        return False, "DUPLICATE_ID", f"課程代號 {code} 重複", {}

    if not isinstance(rec["name"], str) or not (1 <= len(rec["name"].strip()) <= 50):
        return False, "RECORD_INVALID", f"{code} 課程名稱不合法", {}
    if not _is_int_strict(rec["credits"]) or not (1 <= rec["credits"] <= 6):
        return False, "RECORD_INVALID", f"{code} 學分須為 1~6 整數", {}
    if rec["type"] not in {"required", "elective"}:
        return False, "RECORD_INVALID", f"{code} 必選修類型不合法", {}
    if not isinstance(rec["teacher"], str) or not (1 <= len(rec["teacher"].strip()) <= 50):
        return False, "RECORD_INVALID", f"{code} 授課教師不合法", {}
    if not _is_int_strict(rec["capacity"]) or rec["capacity"] < 1:
        return False, "RECORD_INVALID", f"{code} 修課人數上限不合法", {}

    room_id = str(rec["room_id"]).strip().upper()
    if room_id not in classrooms:
        return False, "REFERENCE_MISSING", f"{code} 指定教室 {room_id} 不存在", {}
    if rec["capacity"] > classrooms[room_id]["capacity"]:
        return False, "RECORD_INVALID", f"{code} 人數上限超過教室 {room_id} 容量", {}

    if not isinstance(rec["slots"], list) or len(rec["slots"]) < 1:
        return False, "INVALID_SLOT", f"{code} 至少需有 1 個上課時段", {}
    norm_slots = []
    for s in rec["slots"]:
        if not _is_valid_slot(s):
            return False, "INVALID_SLOT", f"{code} 時段 {s!r} 不合法", {}
        norm_slots.append(s.strip().lower())
    if len(set(norm_slots)) != len(norm_slots):
        return False, "INVALID_SLOT", f"{code} 時段重複", {}

    if rec["status"] not in {"open", "cancelled"}:
        return False, "RECORD_INVALID", f"{code} 狀態不合法", {}

    clean = {
        "code": code,
        "name": rec["name"].strip(),
        "credits": rec["credits"],
        "type": rec["type"],
        "teacher": rec["teacher"].strip(),
        "capacity": rec["capacity"],
        "room_id": room_id,
        "slots": norm_slots,
        "status": rec["status"],
    }
    return True, "", "", clean


def _validate_student(rec: Any, existing_ids: set[str]) -> tuple[bool, str, str, dict[str, Any]]:
    if not isinstance(rec, dict):
        return False, "RECORD_INVALID", "紀錄必須為 JSON 物件", {}
    required = ["student_id", "name", "dept_year", "credit_limit", "enrolled_courses"]
    for k in required:
        if k not in rec:
            return False, "MISSING_FIELD", f"缺少必填欄位 {k}", {}

    sid = str(rec["student_id"]).strip().upper()
    if not re.match(r"^S[0-9]{3}$", sid):
        return False, "INVALID_ID_FORMAT", f"學號 {sid} 格式不合法", {}
    if sid in existing_ids:
        return False, "DUPLICATE_ID", f"學號 {sid} 重複", {}

    if not isinstance(rec["name"], str) or not (1 <= len(rec["name"].strip()) <= 50):
        return False, "RECORD_INVALID", f"{sid} 姓名不合法", {}
    if not isinstance(rec["dept_year"], str) or not (1 <= len(rec["dept_year"].strip()) <= 20):
        return False, "RECORD_INVALID", f"{sid} 系級不合法", {}
    if not _is_int_strict(rec["credit_limit"]) or not (1 <= rec["credit_limit"] <= 30):
        return False, "RECORD_INVALID", f"{sid} 學分上限須為 1~30 整數", {}
    if not isinstance(rec["enrolled_courses"], list) or any(not isinstance(c, str) for c in rec["enrolled_courses"]):
        return False, "RECORD_INVALID", f"{sid} 已選課程清單型別錯誤", {}

    clean = {
        "student_id": sid,
        "name": rec["name"].strip(),
        "dept_year": rec["dept_year"].strip(),
        "credit_limit": rec["credit_limit"],
        "enrolled_courses": list(dict.fromkeys(c.strip().upper() for c in rec["enrolled_courses"])),
    }
    return True, "", "", clean


def _validate_activity(
    rec: Any, existing_ids: set[str], classrooms: dict[str, dict[str, Any]]
) -> tuple[bool, str, str, dict[str, Any]]:
    if not isinstance(rec, dict):
        return False, "RECORD_INVALID", "紀錄必須為 JSON 物件", {}
    required = [
        "activity_id", "name", "activity_type", "date", "start_time",
        "end_time", "recurrence", "expected_attendees", "required_equipment",
        "room_id", "participants", "organizer", "status"
    ]
    for k in required:
        if k not in rec:
            return False, "MISSING_FIELD", f"缺少必填欄位 {k}", {}

    aid = str(rec["activity_id"]).strip().upper()
    if not re.match(r"^EV[0-9]{3}$", aid):
        return False, "INVALID_ID_FORMAT", f"活動代號 {aid} 格式不合法", {}
    if aid in existing_ids:
        return False, "DUPLICATE_ID", f"活動代號 {aid} 重複", {}

    if not isinstance(rec["name"], str) or not (1 <= len(rec["name"].strip()) <= 50):
        return False, "RECORD_INVALID", f"{aid} 活動名稱不合法", {}
    if rec["activity_type"] not in {"lecture", "club", "study_group", "competition", "other"}:
        return False, "RECORD_INVALID", f"{aid} 活動類型不合法", {}
    try:
        datetime.strptime(str(rec["date"]), "%Y-%m-%d")
    except ValueError:
        return False, "RECORD_INVALID", f"{aid} 日期格式錯誤", {}
    if not re.match(r"^\d{2}:\d{2}$", str(rec["start_time"])) or not re.match(r"^\d{2}:\d{2}$", str(rec["end_time"])):
        return False, "RECORD_INVALID", f"{aid} 時間格式錯誤", {}
    if rec["start_time"] < "08:10" or rec["end_time"] > "20:00" or rec["end_time"] <= rec["start_time"]:
        return False, "RECORD_INVALID", f"{aid} 時間區間不合法", {}
    if rec["recurrence"] not in {"once", "weekly"}:
        return False, "RECORD_INVALID", f"{aid} 重複類型不合法", {}
    if not _is_int_strict(rec["expected_attendees"]) or rec["expected_attendees"] < 1:
        return False, "RECORD_INVALID", f"{aid} 預計人數不合法", {}
    if not isinstance(rec["required_equipment"], list) or any(e not in VALID_EQUIPMENT for e in rec["required_equipment"]):
        return False, "RECORD_INVALID", f"{aid} 需求設備不合法", {}

    room_id = rec["room_id"]
    if room_id is not None:
        room_id = str(room_id).strip().upper()
        if room_id not in classrooms:
            return False, "REFERENCE_MISSING", f"{aid} 配置教室 {room_id} 不存在", {}

    if not isinstance(rec["participants"], list) or any(not isinstance(p, str) for p in rec["participants"]):
        return False, "RECORD_INVALID", f"{aid} 報名名單型別錯誤", {}
    if not isinstance(rec["organizer"], str) or not (1 <= len(rec["organizer"].strip()) <= 50):
        return False, "RECORD_INVALID", f"{aid} 主辦人欄位不合法", {}
    if rec["status"] not in {"scheduled", "cancelled"}:
        return False, "RECORD_INVALID", f"{aid} 活動狀態不合法", {}

    clean = {
        "activity_id": aid,
        "name": rec["name"].strip(),
        "activity_type": rec["activity_type"],
        "date": str(rec["date"]),
        "start_time": str(rec["start_time"]),
        "end_time": str(rec["end_time"]),
        "recurrence": rec["recurrence"],
        "expected_attendees": rec["expected_attendees"],
        "required_equipment": list(dict.fromkeys(rec["required_equipment"])),
        "room_id": room_id,
        "participants": list(dict.fromkeys(p.strip().upper() for p in rec["participants"])),
        "organizer": rec["organizer"].strip(),
        "status": rec["status"],
    }
    return True, "", "", clean


def _validate_enrollment(
    rec: Any,
    students: dict[str, dict[str, Any]],
    courses: dict[str, dict[str, Any]],
) -> tuple[bool, str, str, dict[str, Any]]:
    if not isinstance(rec, dict):
        return False, "RECORD_INVALID", "紀錄必須為 JSON 物件", {}
    for k in ["timestamp", "student_id", "course_code", "action"]:
        if k not in rec:
            return False, "MISSING_FIELD", f"缺少必填欄位 {k}", {}

    sid = str(rec["student_id"]).strip().upper()
    code = str(rec["course_code"]).strip().upper()
    if sid not in students:
        return False, "REFERENCE_MISSING", f"學號 {sid} 不存在，已略過", {}
    if code not in courses:
        return False, "REFERENCE_MISSING", f"課程 {code} 不存在，已略過", {}
    if rec["action"] not in {"add", "drop", "auto_drop"}:
        return False, "RECORD_INVALID", f"操作類型 {rec['action']} 不合法", {}
    if not isinstance(rec["timestamp"], str) or not rec["timestamp"].strip():
        return False, "RECORD_INVALID", "timestamp 不可為空", {}

    clean = {
        "timestamp": rec["timestamp"].strip(),
        "student_id": sid,
        "course_code": code,
        "action": rec["action"],
        "reason": str(rec.get("reason", "")),
    }
    return True, "", "", clean


def _read_raw_records(filepath: str, filename: str) -> tuple[list[Any] | None, FileLoadSummary]:
    summary = FileLoadSummary(filename=filename)
    if not os.path.exists(filepath):
        summary.file_missing = True
        return None, summary

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_name = f"{filename}.corrupt-{ts}"
        backup_path = os.path.join(os.path.dirname(filepath), backup_name)
        os.replace(filepath, backup_path)
        summary.corrupt_backup = backup_name
        return None, summary

    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_name = f"{filename}.corrupt-{ts}"
        backup_path = os.path.join(os.path.dirname(filepath), backup_name)
        os.replace(filepath, backup_path)
        summary.corrupt_backup = backup_name
        return None, summary

    records = payload["records"]
    summary.total_read = len(records)
    return records, summary


def load_all(data_dir: str = "data") -> tuple[StorageSystemData, LoadReport]:
    """載入資料夾內所有系統 JSON 檔案，執行單筆容錯與參照完整性檢查。"""
    data = StorageSystemData()
    report = LoadReport()

    recs, summary = _read_raw_records(os.path.join(data_dir, "classrooms.json"), "classrooms.json")
    if recs is not None:
        for idx, rec in enumerate(recs, start=1):
            ok, code, msg, clean = _validate_classroom(rec, set(data.classrooms.keys()))
            if ok:
                data.classrooms[clean["room_id"]] = clean
                summary.success_count += 1
            else:
                summary.skipped.append(LoadSkipItem(idx, code, msg))
    report.summaries["classrooms.json"] = summary

    recs, summary = _read_raw_records(os.path.join(data_dir, "courses.json"), "courses.json")
    if recs is not None:
        for idx, rec in enumerate(recs, start=1):
            ok, code, msg, clean = _validate_course(rec, set(data.courses.keys()), data.classrooms)
            if ok:
                data.courses[clean["code"]] = clean
                summary.success_count += 1
            else:
                summary.skipped.append(LoadSkipItem(idx, code, msg))
    report.summaries["courses.json"] = summary

    recs, summary = _read_raw_records(os.path.join(data_dir, "students.json"), "students.json")
    if recs is not None:
        for idx, rec in enumerate(recs, start=1):
            ok, code, msg, clean = _validate_student(rec, set(data.students.keys()))
            if ok:
                valid_enrolled = []
                for c_code in clean["enrolled_courses"]:
                    if c_code not in data.courses or data.courses[c_code]["status"] != "open":
                        report.warnings.append(
                            f"[REFERENCE_MISSING] 學生 {clean['student_id']} 已選課程 {c_code} 不存在或非開放，已移除參照"
                        )
                    else:
                        valid_enrolled.append(c_code)
                clean["enrolled_courses"] = valid_enrolled
                data.students[clean["student_id"]] = clean
                summary.success_count += 1
            else:
                summary.skipped.append(LoadSkipItem(idx, code, msg))
    report.summaries["students.json"] = summary

    recs, summary = _read_raw_records(os.path.join(data_dir, "activities.json"), "activities.json")
    if recs is not None:
        for idx, rec in enumerate(recs, start=1):
            ok, code, msg, clean = _validate_activity(rec, set(data.activities.keys()), data.classrooms)
            if ok:
                valid_participants = []
                for p_id in clean["participants"]:
                    if p_id not in data.students:
                        report.warnings.append(
                            f"[REFERENCE_MISSING] 活動 {clean['activity_id']} 報名者 {p_id} 不存在，已移除參照"
                        )
                    else:
                        valid_participants.append(p_id)
                clean["participants"] = valid_participants
                data.activities[clean["activity_id"]] = clean
                summary.success_count += 1
            else:
                summary.skipped.append(LoadSkipItem(idx, code, msg))
    report.summaries["activities.json"] = summary

    recs, summary = _read_raw_records(os.path.join(data_dir, "enrollments.json"), "enrollments.json")
    if recs is not None:
        for idx, rec in enumerate(recs, start=1):
            ok, code, msg, clean = _validate_enrollment(rec, data.students, data.courses)
            if ok:
                data.enrollment_log.append(clean)
                summary.success_count += 1
            else:
                summary.skipped.append(LoadSkipItem(idx, code, msg))
    report.summaries["enrollments.json"] = summary

    return data, report


def _atomic_write_json(filepath: str, records: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    payload = {"schema_version": 1, "records": records}
    dir_name = os.path.dirname(filepath) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=dir_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def save_all(data: StorageSystemData, data_dir: str = "data") -> tuple[bool, str]:
    """將五類系統資料以暫存檔 + os.replace 原子方式寫入 JSON 檔案。"""
    files_map = {
        "classrooms.json": list(data.classrooms.values()),
        "courses.json": list(data.courses.values()),
        "students.json": list(data.students.values()),
        "activities.json": list(data.activities.values()),
        "enrollments.json": list(data.enrollment_log),
    }
    try:
        for fname, records in files_map.items():
            _atomic_write_json(os.path.join(data_dir, fname), records)
        return True, "資料儲存成功"
    except OSError as exc:
        return False, f"[SAVE_FAILED] 儲存失敗：{exc}"
