import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import Activity, Course, Student, SystemData
from .result import ErrorItem, Result
from .validators import (
    _validate_activity, _validate_classroom, _validate_course,
    _validate_enrollment, _validate_student,
)


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
    errors: list[ErrorItem] = field(default_factory=list)


@dataclass
class LoadReport:
    summaries: dict[str, FileLoadSummary] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def safe_to_save(self) -> bool:
        """檔案讀取或格式有問題時，介面應暫停寫入以免掩蓋缺失資料。"""
        return not any(summary.errors for summary in self.summaries.values())

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
                lines.append(f"{fname:<17} [FILE_NOT_FOUND] 檔案不存在，以空資料開始")
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
        for summary in self.summaries.values():
            lines.extend(f"[{error.code}] {summary.filename}：{error.message}" for error in summary.errors)
        return "\n".join(lines)


# 舊版 import 保持相容，但現在與 F5 使用同一個 SystemData 類別。
StorageSystemData = SystemData


def _reject_constant(value: str) -> None:
    raise ValueError(f"JSON 不接受非有限數值 {value}")


def _read_raw_records(filepath: str, filename: str) -> tuple[list[Any] | None, FileLoadSummary]:
    summary = FileLoadSummary(filename=filename)
    if not os.path.exists(filepath):
        summary.file_missing = True
        return None, summary

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            payload = json.load(f, parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError):
        summary.errors.append(ErrorItem("JSON_SYNTAX", "JSON 語法或 UTF-8 編碼錯誤，以空資料開始"))
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_name = f"{filename}.corrupt-{ts}-{uuid4().hex[:8]}"
            backup_path = os.path.join(os.path.dirname(filepath), backup_name)
            os.replace(filepath, backup_path)
            summary.corrupt_backup = backup_name
        except OSError as exc:
            summary.errors.append(ErrorItem("SAVE_FAILED", f"無法搬移毀損檔，原檔保留：{exc}"))
        return None, summary
    except OSError as exc:
        summary.errors.append(ErrorItem("RECORD_INVALID", f"無法讀取檔案：{exc}"))
        return None, summary

    if (not isinstance(payload, dict) or type(payload.get("schema_version")) is not int
            or payload.get("schema_version") != 1 or not isinstance(payload.get("records"), list)):
        summary.errors.append(ErrorItem("RECORD_INVALID", "須為 schema_version=1 與 records 清單；原檔未更動"))
        return None, summary

    records = payload["records"]
    summary.total_read = len(records)
    return records, summary


def _safe_validate(validator, rec, *args):
    """單筆型別不合法也只略過該筆，不讓 unhashable 等例外中斷載入。"""
    try:
        return validator(rec, *args)
    except (TypeError, ValueError, KeyError, OverflowError) as exc:
        return False, "RECORD_INVALID", f"欄位型別或內容不合法：{exc}", {}


def load_all(data_dir: str = "data") -> tuple[StorageSystemData, LoadReport]:
    """讀取五類 v1 JSON，回傳 (SystemData, LoadReport)，不呼叫介面輸出。

    缺檔以空資料開始；JSON_SYNTAX 保留原檔備份；單筆錯誤略過並記錄；
    權限或格式錯誤寫入報告。呼叫者須查看 report.safe_to_save 才可自動儲存。
    """
    data = StorageSystemData()
    report = LoadReport()

    recs, summary = _read_raw_records(os.path.join(data_dir, "classrooms.json"), "classrooms.json")
    if recs is not None:
        for idx, rec in enumerate(recs, start=1):
            ok, code, msg, clean = _safe_validate(_validate_classroom, rec, set(data.classrooms.keys()))
            if ok:
                data.classrooms[clean["room_id"]] = clean
                summary.success_count += 1
            else:
                summary.skipped.append(LoadSkipItem(idx, code, msg))
    report.summaries["classrooms.json"] = summary

    recs, summary = _read_raw_records(os.path.join(data_dir, "courses.json"), "courses.json")
    if recs is not None:
        for idx, rec in enumerate(recs, start=1):
            ok, code, msg, clean = _safe_validate(_validate_course, rec, set(data.courses.keys()), data.classrooms)
            if ok:
                data.courses[clean["code"]] = Course(**clean)
                summary.success_count += 1
            else:
                summary.skipped.append(LoadSkipItem(idx, code, msg))
    report.summaries["courses.json"] = summary

    recs, summary = _read_raw_records(os.path.join(data_dir, "students.json"), "students.json")
    if recs is not None:
        for idx, rec in enumerate(recs, start=1):
            ok, code, msg, clean = _safe_validate(_validate_student, rec, set(data.students.keys()))
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
                data.students[clean["student_id"]] = Student(**clean)
                summary.success_count += 1
            else:
                summary.skipped.append(LoadSkipItem(idx, code, msg))
    report.summaries["students.json"] = summary

    recs, summary = _read_raw_records(os.path.join(data_dir, "activities.json"), "activities.json")
    if recs is not None:
        for idx, rec in enumerate(recs, start=1):
            ok, code, msg, clean = _safe_validate(_validate_activity, rec, set(data.activities.keys()), data.classrooms)
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
                limit = clean["expected_attendees"]
                if clean["room_id"] is not None:
                    limit = min(limit, data.classrooms[clean["room_id"]]["capacity"])
                if len(valid_participants) > limit:
                    summary.skipped.append(LoadSkipItem(idx, "RECORD_INVALID", "活動有效報名人數超過活動或教室容量"))
                    continue
                data.activities[clean["activity_id"]] = Activity(**clean)
                summary.success_count += 1
            else:
                summary.skipped.append(LoadSkipItem(idx, code, msg))
    report.summaries["activities.json"] = summary

    recs, summary = _read_raw_records(os.path.join(data_dir, "enrollments.json"), "enrollments.json")
    if recs is not None:
        for idx, rec in enumerate(recs, start=1):
            ok, code, msg, clean = _safe_validate(_validate_enrollment, rec, data.students, data.courses)
            if ok:
                data.enrollment_log.append(clean)
                summary.success_count += 1
            else:
                summary.skipped.append(LoadSkipItem(idx, code, msg))
    report.summaries["enrollments.json"] = summary

    return data, report



@dataclass
class SaveResult(Result):
    """符合 Result 介面，同時支援既有 ok, message = save_all(...) 呼叫。"""

    def __iter__(self):
        yield self.ok
        yield self.data if self.ok else "\n".join(
            f"[{item.code}] {item.message}" for item in self.errors
        )


def _record(value: object) -> dict:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    raise TypeError("系統資料紀錄須為 dict 或 dataclass")


def _file_records(data: SystemData) -> dict:
    result = {
        "classrooms.json": [_record(item) for item in data.classrooms.values()],
        "courses.json": [_record(item) for item in data.courses.values()],
        "students.json": [_record(item) for item in data.students.values()],
        "activities.json": [_record(item) for item in data.activities.values()],
        "enrollments.json": [_record(item) for item in data.enrollment_log],
    }
    for activity in result["activities.json"]:
        activity.pop("slots", None)  # 載入後時段快取不寫入 JSON。
    for student in result["students.json"]:
        student.pop("enrolledActivities", None)
        student.pop("enrolled_activities", None)
    for filename, records in result.items():
        for record in records:
            _normalise_output(record)
    return result


def _normalise_output(record: dict) -> None:
    identifiers = ("code", "student_id", "room_id", "activity_id", "course_code", "building")
    for key in identifiers:
        if isinstance(record.get(key), str):
            record[key] = record[key].strip().upper()
    for key in ("enrolled_courses", "participants"):
        if isinstance(record.get(key), list):
            record[key] = [item.strip().upper() if isinstance(item, str) else item for item in record[key]]
    for key in ("slots", "unavailable_slots"):
        if isinstance(record.get(key), list):
            record[key] = [item.strip().lower() if isinstance(item, str) else item for item in record[key]]
    for key in ("name", "teacher", "dept_year", "organizer", "timestamp", "reason"):
        if isinstance(record.get(key), str):
            record[key] = record[key].strip()


def _stage_bytes(folder: Path, content: bytes, prefix: str) -> Path:
    fd, temporary = tempfile.mkstemp(prefix=prefix, suffix=".json", dir=folder)
    path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        raise
    return path


def _restore_files(committed: list, originals: dict) -> list[str]:
    errors = []
    for target in reversed(committed):
        backup = originals[target]
        try:
            if backup is None:
                target.unlink(missing_ok=True)
            else:
                os.replace(backup, target)
        except OSError as exc:
            errors.append(f"還原 {target.name} 失敗；復原檔 {backup}：{exc}")
    return errors


def _write_transaction(payloads: dict[Path, object]) -> SaveResult:
    stages, originals, committed = {}, {}, []
    rollback_errors = []
    try:
        # 全部序列化成功後才建檔，拒絕 NaN／Infinity 與不可序列化物件。
        encoded = {path: json.dumps(value, ensure_ascii=False, indent=2,
                                   allow_nan=False).encode("utf-8")
                   for path, value in payloads.items()}
        for path, content in encoded.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            originals[path] = (_stage_bytes(path.parent, path.read_bytes(), ".rollback_")
                               if path.exists() else None)
            stages[path] = _stage_bytes(path.parent, content, ".tmp_")
        for path, stage in stages.items():
            os.replace(stage, path)
            committed.append(path)
        return SaveResult(True, "資料儲存成功")
    except (OSError, TypeError, ValueError, OverflowError) as exc:
        rollback_errors = _restore_files(committed, originals)
        message = f"儲存失敗：{exc}"
        if rollback_errors:
            message += "；" + "；".join(rollback_errors)
        return SaveResult(False, errors=[ErrorItem("SAVE_FAILED", message)])
    finally:
        temporary_paths = list(stages.values())
        if not rollback_errors:
            temporary_paths += [path for path in originals.values() if path]
        for path in temporary_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # 清理失敗不把已成功取代的檔案誤報成儲存失敗。


def save_all(data: SystemData, data_dir: str = "data") -> SaveResult:
    """以 UTF-8／indent=2 儲存五個 v1 JSON，回傳 Result。

    全部暫存檔完成後才 os.replace；可捕捉的取代失敗會還原已取代檔案。
    不修改 data；序列化或檔案錯誤回傳 SAVE_FAILED，不拋出到 CLI。
    支援 models.SystemData 與舊 StorageSystemData 名稱、dict／dataclass 紀錄。
    """
    try:
        folder = Path(data_dir)
        records_by_file = _file_records(data)
        _check_history(data, folder, records_by_file["enrollments.json"])
        payloads = {folder / name: {"schema_version": 1, "records": records}
                    for name, records in records_by_file.items()}
    except (OSError, TypeError, ValueError, AttributeError) as exc:
        return SaveResult(False, errors=[ErrorItem("SAVE_FAILED", str(exc))])
    return _write_transaction(payloads)


def _check_history(data: SystemData, folder: Path, incoming: list[dict]) -> None:
    path = folder / "enrollments.json"
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle, parse_constant=_reject_constant)
    if (not isinstance(payload, dict) or type(payload.get("schema_version")) is not int
            or payload.get("schema_version") != 1 or not isinstance(payload.get("records"), list)):
        raise ValueError("既有選課紀錄格式錯誤，拒絕覆寫")
    previous = []
    for record in payload["records"]:
        ok, _, _, clean = _safe_validate(_validate_enrollment, record, data.students, data.courses)
        if ok:
            previous.append(clean)
    if incoming[:len(previous)] != previous:
        raise ValueError("有效選課紀錄只允許追加，不得修改或刪除既有歷程")


class LegacyRecords(list):
    """舊清單加上載入錯誤，讓舊選單能在資料不完整時拒絕修改。"""
    def __init__(self, records=(), errors=()):
        super().__init__(records)
        self.load_errors = list(errors)


def load_legacy_file(filename: str) -> LegacyRecords:
    """讀取舊清單；缺檔回傳空清單，損壞檔備份且標記阻止自動儲存。"""
    path = Path(filename)
    if not path.exists():
        return LegacyRecords()
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            return LegacyRecords(errors=["[RECORD_INVALID] 舊選單只接受物件清單；v1 資料請使用 main.py"])
        return LegacyRecords(value)
    except (ValueError, UnicodeDecodeError) as exc:
        errors = [f"[JSON_SYNTAX] {path.name}：{exc}"]
        try:
            backup = path.with_name(path.name + ".corrupt-" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "-" + uuid4().hex[:8])
            os.replace(path, backup)
            errors.append(f"已保留原檔：{backup.name}")
        except OSError as backup_error:
            errors.append(f"無法備份，原檔保留：{backup_error}")
        return LegacyRecords(errors=errors)
    except OSError as exc:
        return LegacyRecords(errors=[f"[RECORD_INVALID] {path.name}：{exc}"])


def save_legacy_file(filename: str, records: list) -> SaveResult:
    """舊版清單以暫存檔原子取代；保留舊格式，不轉換識別碼。"""
    return _write_transaction({Path(filename): records})


def initialize_demo(data_dir: str) -> SaveResult:
    """只在五個目標檔皆不存在時建立示範資料，避免覆寫既有資料。"""
    from .sample_data import create_sample_data

    folder = Path(data_dir)
    names = ("courses.json", "students.json", "classrooms.json", "activities.json", "enrollments.json")
    if any((folder / name).exists() for name in names):
        return SaveResult(False, errors=[ErrorItem("SAVE_FAILED", "資料夾已有資料檔，拒絕覆寫示範資料")])
    return save_all(create_sample_data(), data_dir)
