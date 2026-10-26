"""F4：校園活動與教室配置（需求規格 FR-4.1～4.8）。

教室時段衝突沿用 F2 的 checkClassroomConflicts、報名衝突沿用 F2 的
checkActivityParticipation；本檔只補上需求規格 3.5 的日期規則（單次／每週）。
所有函式不呼叫 input()／print()；format 開頭的函式回傳要顯示的字串。
"""

import copy
import datetime
import re

from f2_system import DAYS, PERIODS, checkActivityParticipation, checkClassroomConflicts
from f3_system import PERIOD_TIMES


ACTIVITY_TYPES = ["lecture", "club", "study_group", "competition", "other"]
RECURRENCES = ["once", "weekly"]
EQUIPMENT_CODES = ["projector", "microphone", "computer", "whiteboard", "speaker", "video_conf"]
EARLIEST_TIME = "08:10"
LATEST_TIME = "20:00"


# 將時段集合格式化整理為中文顯示字串
def describeSlots(slots):
    byDay = {}
    for day, period in sorted(slots, key=lambda slot: (slot[0], PERIODS.index(slot[1]))):
        byDay.setdefault(day, []).append(period)
    return "；".join(
        f"星期{DAYS[day - 1]}第 {'、'.join(periods)} 節" for day, periods in byDay.items()
    )


# 判斷兩個項目是否可能發生日期與時間交集
def canOverlap(itemA, itemB):
    if itemA.get("recurrence", "weekly") == "weekly":
        return True
    if itemB.get("recurrence", "weekly") == "weekly":
        return True
    return itemA.get("date") == itemB.get("date")


# 將日期與具體時間轉換對齊為課表節次與星期
def timeToSchedules(date, startTime, endTime):
    try:
        day = datetime.date.fromisoformat(date).isoweekday()
    except (TypeError, ValueError):
        return [], [f"[INVALID_DATE] 日期 {date} 不合法：須為存在的 YYYY-MM-DD"]

    timePattern = re.compile(r"^\d{2}:\d{2}$")
    try:
        if not timePattern.match(startTime) or not timePattern.match(endTime):
            raise ValueError
        start = datetime.time.fromisoformat(startTime)
        end = datetime.time.fromisoformat(endTime)
    except (TypeError, ValueError):
        return [], [f"[INVALID_TIME_RANGE] 時間 {startTime}–{endTime} 不合法：須為 HH:MM"]

    errors = []
    if start < datetime.time.fromisoformat(EARLIEST_TIME):
        errors.append(f"[INVALID_TIME_RANGE] 開始時間 {startTime} 早於 {EARLIEST_TIME}")
    if end > datetime.time.fromisoformat(LATEST_TIME):
        errors.append(f"[INVALID_TIME_RANGE] 結束時間 {endTime} 晚於 {LATEST_TIME}")
    if end <= start:
        errors.append(f"[INVALID_TIME_RANGE] 結束時間 {endTime} 必須晚於開始時間 {startTime}")
    if errors:
        return [], errors

    schedules = []
    for period in PERIODS:
        periodStart = datetime.time.fromisoformat(PERIOD_TIMES[period][0])
        periodEnd = datetime.time.fromisoformat(PERIOD_TIMES[period][1])
        if start < periodEnd and periodStart < end:
            schedules.append({"day": day, "period": period})

    if not schedules:
        return [], [f"[INVALID_TIME_RANGE] {startTime}–{endTime} 只落在下課時間，沒有對應節次"]
    return schedules, []


# 計算特定活動目前已報名的學生總人數
def getParticipantCount(activityId, studentsList):
    return sum(
        1
        for student in studentsList
        if activityId in student.get("enrolledActivities", [])
    )


# 驗證活動輸入資料合法性、清洗格式並計算對應時段
def prepareActivity(activityData, existingActivities):
    errors = []
    requiredFields = [
        "activityId", "name", "activityType", "date", "startTime", "endTime",
        "recurrence", "expectedAttendees", "requiredEquipment", "organizer",
    ]
    for field in requiredFields:
        value = activityData.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"[MISSING_FIELD] 缺少欄位：{field}")
    if errors:
        return None, errors

    activity = copy.deepcopy(activityData)
    activity["activityId"] = activity["activityId"].strip().upper()
    for field in ["name", "activityType", "date", "startTime", "endTime", "recurrence", "organizer"]:
        activity[field] = str(activity[field]).strip()
    if activity.get("roomId"):
        activity["roomId"] = activity["roomId"].strip().upper()
    else:
        activity["roomId"] = None
    activity.setdefault("status", "scheduled")

    if not re.match(r"^EV[0-9]{3}$", activity["activityId"]):
        errors.append(f"[INVALID_ID_FORMAT] 活動代號 {activity['activityId']} 不合法：須為 EV + 3 位數字")
    for other in existingActivities:
        if other["activityId"].upper() == activity["activityId"]:
            errors.append(f"[DUPLICATE_ID] 活動代號 {activity['activityId']} 已存在")
    if not 1 <= len(activity["name"]) <= 50:
        errors.append("[INVALID_VALUE] 活動名稱須為 1–50 字")
    if not 1 <= len(activity["organizer"]) <= 50:
        errors.append("[INVALID_VALUE] 主辦人須為 1–50 字")
    if activity["activityType"] not in ACTIVITY_TYPES:
        errors.append(f"[INVALID_VALUE] 活動類型 {activity['activityType']} 不合法：須為 {'、'.join(ACTIVITY_TYPES)}")
    if activity["recurrence"] not in RECURRENCES:
        errors.append(f"[INVALID_VALUE] 重複方式 {activity['recurrence']} 不合法：須為 once 或 weekly")

    expected = activity["expectedAttendees"]
    if not isinstance(expected, int) or isinstance(expected, bool) or expected < 1:
        errors.append(f"[INVALID_CAPACITY] 預計人數 {expected} 不合法：須為 ≥ 1 的整數")

    equipment = activity["requiredEquipment"]
    if not isinstance(equipment, list):
        errors.append("[INVALID_VALUE] 設備需求須為清單")
    else:
        for item in equipment:
            if item not in EQUIPMENT_CODES:
                errors.append(f"[INVALID_VALUE] 設備代碼 {item} 不合法：須為 {'、'.join(EQUIPMENT_CODES)}")

    schedules, timeErrors = timeToSchedules(activity["date"], activity["startTime"], activity["endTime"])
    errors.extend(timeErrors)
    activity["schedules"] = schedules

    if errors:
        return None, errors
    return activity, []


# 檢查單一教室是否滿足活動的需求
def checkRoom(activity, room, coursesList, activitiesList):
    reasons = []

    if room.get("status", "active") == "disabled":
        reasons.append(("ROOM_UNAVAILABLE", "教室停用"))

    capacity = room.get("capacity", 0)
    if capacity < activity["expectedAttendees"]:
        reasons.append((
            "ROOM_CAPACITY_INSUFFICIENT",
            f"容量不足（需 {activity['expectedAttendees']}，教室 {capacity}）",
        ))

    missing = [item for item in activity["requiredEquipment"] if item not in room.get("equipment", [])]
    if missing:
        reasons.append(("EQUIPMENT_MISSING", f"缺少設備：{'、'.join(missing)}"))

    activitySlots = {(s["day"], str(s["period"]).lower()) for s in activity["schedules"]}
    unavailable = {
        (s["day"], str(s["period"]).lower()) for s in room.get("unavailableSlots", [])
    }
    if activitySlots & unavailable:
        reasons.append(("ROOM_UNAVAILABLE", f"教室停用時段：{describeSlots(activitySlots & unavailable)}"))

    candidate = copy.deepcopy(activity)
    candidate["roomId"] = room["roomId"]
    otherCourses = [course for course in coursesList if course.get("status") != "cancelled"]
    otherActivities = [
        other for other in activitiesList
        if other["activityId"] != candidate["activityId"]
        and other.get("status") != "cancelled"
        and canOverlap(other, candidate)
    ]
    result = checkClassroomConflicts(otherCourses, otherActivities + [candidate])

    courseIds = {course["courseId"] for course in otherCourses}
    slotsByOther = {}
    for conflict in result["conflicts"]:
        if conflict["otherId"] != candidate["activityId"]:
            continue
        key = (conflict["targetId"], conflict["targetName"])
        slotsByOther.setdefault(key, set()).add((conflict["day"], conflict["period"]))
    for (otherId, otherName), slots in sorted(slotsByOther.items()):
        kindName = "課程" if otherId in courseIds else "活動"
        reasons.append((
            "ROOM_TIME_CONFLICT",
            f"時段衝突：{describeSlots(slots)}已有{kindName} {otherId} {otherName}",
        ))

    return reasons


# 遍歷所有教室，篩選出符合活動條件的可用教室清單及不合適原因
def findSuitableRooms(activity, coursesList, activitiesList, classroomsList):
    suitable = []
    unmet = {}
    for room in sorted(classroomsList, key=lambda item: (item.get("capacity", 0), item["roomId"])):
        reasons = checkRoom(activity, room, coursesList, activitiesList)
        if reasons:
            unmet[room["roomId"]] = reasons
        else:
            suitable.append(room["roomId"])
    return suitable, unmet


# 新增活動 API，驗證活動格式與指定教室，合規後加入活動清單
def addActivity(activityData, activitiesList, coursesList, classroomsList):
    activity, errors = prepareActivity(activityData, activitiesList)
    if errors:
        return False, errors, {}

    if activity["roomId"] is not None:
        room = next((r for r in classroomsList if r["roomId"].upper() == activity["roomId"]), None)
        if room is None:
            return False, [f"[NOT_FOUND] 教室 {activity['roomId']} 不存在"], {}
        reasons = checkRoom(activity, room, coursesList, activitiesList)
        if reasons:
            return False, [f"[NO_SUITABLE_ROOM] 教室 {room['roomId']} 不符合條件"], {room["roomId"]: reasons}

    activitiesList.append(activity)
    if activity["roomId"] is None:
        return True, [f"已建立活動 {activity['activityId']}，尚未配置教室"], {}
    return True, [f"已建立活動 {activity['activityId']}，配置教室 {activity['roomId']}"], {}


# 修改活動 API，更新已存在活動資訊，並重新驗證人數與教室衝突
def updateActivity(activityId, changes, activitiesList, coursesList, classroomsList, studentsList):
    activityId = activityId.strip().upper()
    index = next(
        (i for i, a in enumerate(activitiesList) if a["activityId"].upper() == activityId), None
    )
    if index is None:
        return False, [f"[NOT_FOUND] 找不到活動：{activityId}"], {}
    if activitiesList[index].get("status") == "cancelled":
        return False, [f"[ACTIVITY_CANCELLED] 活動 {activityId} 已取消，不可修改"], {}
    if "activityId" in changes and changes["activityId"].strip().upper() != activityId:
        return False, ["[INVALID_VALUE] 不得修改活動代號"], {}

    merged = copy.deepcopy(activitiesList[index])
    merged.update(copy.deepcopy(changes))
    others = activitiesList[:index] + activitiesList[index + 1:]
    activity, errors = prepareActivity(merged, others)
    if errors:
        return False, errors, {}

    registered = getParticipantCount(activityId, studentsList)
    if activity["expectedAttendees"] < registered:
        return False, [
            f"[CAPACITY_BELOW_ENROLLED] 已有 {registered} 人報名，預計人數不得低於此數"
        ], {}

    if activity["roomId"] is not None:
        room = next((r for r in classroomsList if r["roomId"].upper() == activity["roomId"]), None)
        if room is None:
            return False, [f"[NOT_FOUND] 教室 {activity['roomId']} 不存在"], {}
        reasons = checkRoom(activity, room, coursesList, activitiesList)
        if not reasons and room.get("capacity", 0) < registered:
            reasons.append((
                "ROOM_CAPACITY_INSUFFICIENT",
                f"容量不足（已報名 {registered}，教室 {room.get('capacity', 0)}）",
            ))
        if reasons:
            return False, [f"[NO_SUITABLE_ROOM] 教室 {room['roomId']} 不符合條件"], {room["roomId"]: reasons}

    activitiesList[index] = activity
    return True, [f"已修改活動 {activityId}"], {}


# 取消活動 API，把活動標記為取消，並從所有已報名學生的紀錄中移除
def cancelActivity(activityId, activitiesList, studentsList):
    activityId = activityId.strip().upper()
    activity = next((a for a in activitiesList if a["activityId"].upper() == activityId), None)
    if activity is None:
        return False, [f"[NOT_FOUND] 找不到活動：{activityId}"], []
    if activity.get("status") == "cancelled":
        return False, [f"[ACTIVITY_CANCELLED] 活動 {activityId} 已取消"], []

    affected = []
    for student in studentsList:
        if activity["activityId"] in student.get("enrolledActivities", []):
            affected.append(student["studentId"])

    activity["status"] = "cancelled"
    for student in studentsList:
        if activity["activityId"] in student.get("enrolledActivities", []):
            student["enrolledActivities"].remove(activity["activityId"])

    return True, [f"已取消活動 {activityId}，通知 {len(affected)} 位已報名學生"], affected


# 查詢活動 API，依日期、類型、教室或狀態進行多條件篩選
def queryActivities(activitiesList, qDate=None, qType=None, qRoom=None, qStatus=None):
    results = []
    for activity in activitiesList:
        if qDate and activity.get("date") != qDate:
            continue
        if qType and activity.get("activityType") != qType:
            continue
        if qRoom and (activity.get("roomId") or "").upper() != qRoom.upper():
            continue
        if qStatus and activity.get("status") != qStatus:
            continue
        results.append(activity)
    return sorted(results, key=lambda activity: activity["activityId"])


# 報名活動 API，整合衝突與額滿檢核，通過後正式為學生完成報名
def registerActivity(studentId, activityId, coursesList, studentsList, activitiesList, classroomsList):
    result = checkActivityParticipation(
        studentId, activityId, coursesList, studentsList, activitiesList, classroomsList
    )
    target = next((a for a in activitiesList if a["activityId"] == activityId), None)
    student = next((s for s in studentsList if s["studentId"] == studentId), None)
    if target is None or student is None:
        return result

    if target.get("status") == "cancelled":
        result["errors"].append(f"[ACTIVITY_CANCELLED] 活動 {activityId} 已取消")

    activityIndex = {activity["activityId"]: activity for activity in activitiesList}
    keptConflicts = []
    for conflict in result["conflicts"]:
        if conflict["otherType"] == "course":
            keptConflicts.append(conflict)
            continue
        other = activityIndex[conflict["otherId"]]
        if other.get("status") != "cancelled" and canOverlap(target, other):
            keptConflicts.append(conflict)
    result["conflicts"] = keptConflicts

    count = getParticipantCount(activityId, studentsList)
    room = next((r for r in classroomsList if r["roomId"] == target.get("roomId")), None)
    limit = target.get("expectedAttendees", 0)
    if room is not None:
        limit = min(limit, room.get("capacity", 0))
    if count >= limit:
        result["errors"].append(f"[ACTIVITY_FULL] 活動報名額滿：{count}/{limit} 人")

    result["success"] = not result["errors"] and not result["conflicts"]
    if result["success"]:
        student.setdefault("enrolledActivities", []).append(activityId)
    return result


# 格式化輸出，將單一活動的資訊、時間、節次與需求排版為文字報告
def formatActivity(activity):
    day = activity["schedules"][0]["day"]
    periods = "、".join(schedule["period"] for schedule in activity["schedules"])
    recurrenceText = "每週" if activity["recurrence"] == "weekly" else ""
    lines = [
        f"活動：{activity['activityId']} {activity['name']}"
        f"（{activity['date']} {recurrenceText}星期{DAYS[day - 1]} "
        f"{activity['startTime']}–{activity['endTime']}，對應第 {periods} 節）"
    ]
    needs = [f"{activity['expectedAttendees']} 人"] + activity["requiredEquipment"]
    lines.append(f"需求：{'、'.join(needs)}")
    return "\n".join(lines)


# 格式化輸出，將教室配置結果或失敗的原因列表排版為文字報告
def formatAllocation(activity, classroomsList, unmet):
    if activity.get("roomId") and not unmet:
        room = next((r for r in classroomsList if r["roomId"] == activity["roomId"]), {})
        return f"配置結果：成功 → {activity['roomId']}（容量 {room.get('capacity', '?')}）"
    lines = ["配置結果：失敗，無合適教室"]
    for roomId, reasons in unmet.items():
        lines.append(f"{roomId} " + "；".join(message for _, message in reasons))
    return "\n".join(lines)