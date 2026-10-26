"""F2：完整收集選課、活動及教室衝突；檢查函式不修改輸入資料"""

from f1_system import getEnrolledCount, validateSchedule


PERIODS = [str(number) for number in range(1, 10)] + ["a", "b", "c"]
DAYS = "一二三四五六日"


# 計算時段排序鍵值，依星期與節次索引進行排序
def _slotKey(slot):
    return slot[0], PERIODS.index(slot[1])


# 解析並驗證項目的時段設定，回傳時段集合並收集格式錯誤
def _slots(item, errors):
    slots = set()
    for schedule in item.get("schedules", []):
        day, period = schedule.get("day"), schedule.get("period")
        valid, message = validateSchedule(day, period)
        if not valid or isinstance(day, bool):
            errors.append(f"{item.get('name', '未命名項目')}：{message or '星期格式錯誤'}")
        else:
            slots.add((day, str(period).lower()))
    if not item.get("schedules"):
        errors.append(f"{item.get('name', '未命名項目')}：未設定上課或活動時段。")
    return slots


# 將課程與活動整合為包含類型標籤的統一實體清單
def _entities(courses, activities):
    return [("course", item) for item in courses] + [
        ("activity", item) for item in activities
    ]


# 依據項目種類動態讀取對應識別碼
def _entityId(kind, item):
    return item["courseId" if kind == "course" else "activityId"]


# 建立統一格式的衝突詳細資訊字典
def _conflict(kind, day, period, otherKind, other, roomId=None):
    return {
        "type": kind, "day": day, "period": period,
        "otherType": otherKind, "otherId": _entityId(otherKind, other),
        "otherName": other["name"], "roomId": roomId,
    }


# 將衝突清單依據 星期 、節次 、類型 、ID 進行排序
def _sortConflicts(conflicts):
    conflicts.sort(key=lambda item: (
        item["day"], PERIODS.index(item["period"]), item["type"], item["otherId"]
    ))


# 核心檢測引擎、檢查學生加選/報名的學分、人數限制與時空衝突
def _check(studentId, targetId, targetKind, courses, students, activities, classrooms):
    result = {
        "success": False, "studentId": studentId, "targetId": targetId,
        "targetKind": targetKind, "targetName": "", "conflicts": [], "errors": [],
        "currentCredits": None, "afterCredits": None, "maxCredits": None,
        "enrolledCount": None, "maxStudents": None,
    }
    errors, conflicts = result["errors"], result["conflicts"]
    student = next((s for s in students if s["studentId"] == studentId), None)
    targetList = courses if targetKind == "course" else activities
    target = next((item for item in targetList
                   if _entityId(targetKind, item) == targetId), None)
    if student is None:
        errors.append(f"找不到學生：{studentId}")
    if target is None:
        errors.append(f"找不到{'課程' if targetKind == 'course' else '活動'}：{targetId}")
    # 無法識別輸入時沒有可比較的對象，其餘限制一律獨立檢查
    if student is None or target is None:
        return result

    result["targetName"] = target["name"]
    courseIndex = {c["courseId"]: c for c in courses}
    activityIndex = {a["activityId"]: a for a in activities}
    enrolled = set(student.get("enrolledCourses", []))
    attending = set(student.get("enrolledActivities", []))
    for courseId in sorted(enrolled - courseIndex.keys()):
        errors.append(f"已選課程資料不存在：{courseId}")
    for activityId in sorted(attending - activityIndex.keys()):
        errors.append(f"已參加活動資料不存在：{activityId}")
    current = sum(courseIndex[cid]["credits"] for cid in enrolled & courseIndex.keys())
    after = current + (target["credits"] if targetKind == "course" and targetId not in enrolled else 0)
    result.update(currentCredits=current, afterCredits=after, maxCredits=student["maxCredits"])
    if after > student["maxCredits"]:
        errors.append(f"學分超過上限：加選後 {after}，上限 {student['maxCredits']}。")
    if targetKind == "course":
        count = getEnrolledCount(targetId, students)
        result.update(enrolledCount=count, maxStudents=target["maxStudents"])
        if targetId in enrolled:
            errors.append("已選修此課程，不得重複加選。")
        if count >= target["maxStudents"]:
            errors.append(f"課程已額滿：{count}/{target['maxStudents']} 人。")
    elif targetId in attending:
        errors.append("已參加此活動，不得重複報名。")

    targetSlots = _slots(target, errors)
    roomId = target.get("roomId")
    if not roomId or roomId not in {room["roomId"] for room in classrooms}:
        errors.append(f"教室代號不存在：{roomId}")
    for otherKind, other in _entities(courses, activities):
        otherId = _entityId(otherKind, other)
        if otherKind == targetKind and otherId == targetId:
            continue
        isAttending = (otherId in enrolled if otherKind == "course" else otherId in attending)
        sameRoom = bool(roomId) and other.get("roomId") == roomId
        if not isAttending and not sameRoom:
            continue
        overlap = targetSlots & _slots(other, errors)
        for day, period in sorted(overlap, key=_slotKey):
            if isAttending:
                conflicts.append(_conflict("student", day, period, otherKind, other))
            if sameRoom:
                conflicts.append(_conflict("room", day, period, otherKind, other, roomId))
    _sortConflicts(conflicts)
    result["success"] = not errors and not conflicts
    return result


# 對外 API，檢查學生是否可以加選特定課程
def checkEnrollment(studentId, courseId, courses, students, activities, classrooms):
    return _check(studentId, courseId, "course", courses, students, activities, classrooms)


# 對外 API，檢查並執行學生加選課程
def enrollCourse(studentId, courseId, courses, students, activities, classrooms):
    result = checkEnrollment(studentId, courseId, courses, students, activities, classrooms)
    if result["success"]:
        student = next(s for s in students if s["studentId"] == studentId)
        student.setdefault("enrolledCourses", []).append(courseId)
    return result


# 對外 API，檢查學生是否可以參加特定活動
def checkActivityParticipation(studentId, activityId, courses, students, activities, classrooms):
    return _check(studentId, activityId, "activity", courses, students, activities, classrooms)


# 對外 API，檢查並執行學生報名活動
def joinActivity(studentId, activityId, courses, students, activities, classrooms):
    result = checkActivityParticipation(studentId, activityId, courses, students, activities, classrooms)
    if result["success"]:
        student = next(s for s in students if s["studentId"] == studentId)
        student.setdefault("enrolledActivities", []).append(activityId)
    return result


# 對外 API，全局檢查所有課程與活動之間的教室調度排課衝突
def checkClassroomConflicts(courses, activities):
    """檢查全部課程／活動的教室配置，不受學生是否參加影響。"""
    conflicts, errors = [], []
    entities = [(kind, item, _slots(item, errors)) for kind, item in _entities(courses, activities)]
    for index, (kind, item, slots) in enumerate(entities):
        if not item.get("roomId"):
            errors.append(f"{item['name']}：未設定教室。")
            continue
        for otherKind, other, otherSlots in entities[index + 1:]:
            if item["roomId"] != other.get("roomId"):
                continue
            for day, period in sorted(slots & otherSlots, key=_slotKey):
                conflict = _conflict("room", day, period, otherKind, other, item["roomId"])
                conflict.update(targetId=_entityId(kind, item), targetName=item["name"])
                conflicts.append(conflict)
    _sortConflicts(conflicts)
    return {"success": not conflicts and not errors, "conflicts": conflicts, "errors": errors}


# 格式化工具，將檢測結果字典轉譯排版為人類易讀的中文純文字報告
def formatResult(result):
    lines = [f"學生：{result['studentId']}"]
    label = "欲加選" if result["targetKind"] == "course" else "欲參加活動"
    lines.append(f"{label}：{result['targetId']} {result['targetName']}")
    lines.append(f"檢查結果：{'通過' if result['success'] else '失敗'}")
    for number, item in enumerate(result["conflicts"], 1):
        lines.append(f"衝突{number}：星期{DAYS[item['day'] - 1]}第{item['period']}節")
        if item["type"] == "room":
            label = f"教室 {item['roomId']} 已安排"
        else:
            label = "已選課程" if item["otherType"] == "course" else "已參加活動"
        lines.append(f"{label}：{item['otherId']} {item['otherName']}")
    lines.extend(f"限制：{message}" for message in result["errors"])
    if result["currentCredits"] is not None:
        lines.extend([
            f"目前學分：{result['currentCredits']}",
            f"加選後學分：{result['afterCredits']}",
            f"學分上限：{result['maxCredits']}",
        ])
    if result["enrolledCount"] is not None:
        lines.append(f"修課人數：{result['enrolledCount']}/{result['maxStudents']}")
    return "\n".join(lines)