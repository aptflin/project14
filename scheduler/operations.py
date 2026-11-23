"""F6 選單使用的純記憶體操作；成功回傳新 SystemData，核心不儲存檔案。"""
from datetime import datetime, timezone

from .models import SystemData
from .result import ErrorItem, Result
from .storage_bridge import legacy_views, update_from_views


def _errors(report: dict) -> list[ErrorItem]:
    errors = []
    for message in report.get("errors", []):
        code = message.split("]", 1)[0][1:] if message.startswith("[") else "INVALID_VALUE"
        errors.append(ErrorItem(code, message))
    for conflict in report.get("conflicts", []):
        code = ("ROOM_TIME_CONFLICT" if conflict["type"] == "room" else
                "STUDENT_TIME_CONFLICT" if conflict["otherType"] == "course" else "ACTIVITY_TIME_CONFLICT")
        errors.append(ErrorItem(code, f"星期{conflict['day']}第{conflict['period']}節與 {conflict['otherId']} 衝突"))
    return errors


def apply_operation(data: SystemData, action: str, sid: str = "", code: str = "") -> Result:
    """執行 add／drop／register／cancel_activity，回傳新的資料或所有規則錯誤。

    不修改原資料、不讀寫檔案。錯誤代碼含 NOT_FOUND、NOT_ENROLLED、
    活動及選課服務的衝突代碼；成功加退選會追加 ISO 8601 歷程。
    """
    from f2_system import enrollCourse
    from f4_system import cancelActivity, registerActivity

    sid, code = sid.strip().upper(), code.strip().upper()
    views = legacy_views(data)
    if action != "cancel_activity" and sid not in data.students:
        return Result(False, errors=[ErrorItem("NOT_FOUND", f"學生 {sid} 不存在")])
    if action == "drop":
        student = next(s for s in views["students"] if s["studentId"] == sid)
        if code not in student["enrolledCourses"]:
            return Result(False, errors=[ErrorItem("NOT_ENROLLED", f"尚未選修 {code}")])
        student["enrolledCourses"].remove(code)
    elif action in ("add", "register"):
        function = enrollCourse if action == "add" else registerActivity
        report = function(sid, code, views["courses"], views["students"], views["activities"], views["classrooms"])
        if not report["success"]:
            return Result(False, errors=_errors(report))
    elif action == "cancel_activity":
        ok, messages, _ = cancelActivity(code, views["activities"], views["students"])
        if not ok:
            return Result(False, errors=[ErrorItem("INVALID_VALUE", "；".join(messages))])
    else:
        return Result(False, errors=[ErrorItem("INVALID_VALUE", "不支援的操作")])
    candidate = update_from_views(data, views)
    if action in ("add", "drop"):
        candidate.enrollment_log.append({"timestamp": datetime.now(timezone.utc).isoformat(),
                                         "student_id": sid, "course_code": code, "action": action, "reason": ""})
    return Result(True, candidate)
