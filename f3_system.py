"""F3：個人課表產生與空閒時段查詢（需求規格 FR-3.1～3.7）。

所有函式只讀取資料、不修改輸入，也不呼叫 input()／print()；
format 開頭的函式回傳要顯示的字串，交給選單層印出。
"""

from f2_system import PERIODS, DAYS


# 節次對應時間（需求規格 3.1）
PERIOD_TIMES = {
    "1": ("08:10", "09:00"), "2": ("09:10", "10:00"), "3": ("10:10", "11:00"),
    "4": ("11:10", "12:00"), "5": ("12:10", "13:00"), "6": ("13:10", "14:00"),
    "7": ("14:10", "15:00"), "8": ("15:10", "16:00"), "9": ("16:10", "17:00"),
    "a": ("17:10", "18:00"), "b": ("18:10", "19:00"), "c": ("19:10", "20:00"),
}


# 建立 7 天 × 12 節的空課表，每格是一個占用清單
def createEmptyTimetable():
    return [[[] for _ in PERIODS] for _ in range(7)]


# FR-3.1、3.2：把學生已選課程及已報名活動放進 7 × 12 課表
# 回傳 (timetable, errors)；timetable[day - 1][PERIODS.index(period)] 是該格的占用清單
def buildTimetable(studentId, courses, students, activities):
    timetable = createEmptyTimetable()
    errors = []

    student = next((s for s in students if s["studentId"] == studentId), None)
    if student is None:
        return timetable, [f"[NOT_FOUND] 找不到學生：{studentId}"]

    courseIndex = {course["courseId"]: course for course in courses}
    activityIndex = {activity["activityId"]: activity for activity in activities}

    items = []
    for courseId in student.get("enrolledCourses", []):
        if courseId in courseIndex:
            items.append(("course", courseId, courseIndex[courseId]))
        else:
            errors.append(f"[NOT_FOUND] 已選課程資料不存在：{courseId}")
    for activityId in student.get("enrolledActivities", []):
        if activityId not in activityIndex:
            errors.append(f"[NOT_FOUND] 已報名活動資料不存在：{activityId}")
        elif activityIndex[activityId].get("status") == "cancelled":
            continue
        else:
            items.append(("activity", activityId, activityIndex[activityId]))

    # 同一課程每週上課多次時，每個 schedule 都放進對應的格子
    for kind, itemId, item in items:
        for schedule in item.get("schedules", []):
            day = schedule.get("day")
            period = str(schedule.get("period")).lower()
            if not isinstance(day, int) or not 1 <= day <= 7 or period not in PERIODS:
                errors.append(f"[INVALID_SLOT] {itemId}：時段格式錯誤 {schedule}")
                continue
            timetable[day - 1][PERIODS.index(period)].append({
                "kind": kind,
                "id": itemId,
                "name": item["name"],
                "roomId": item.get("roomId"),
                "recurrence": item.get("recurrence", "weekly"),
                "date": item.get("date"),
            })

    return timetable, errors


# FR-3.3：依星期、節次、課程／活動代號查詢；條件給 None 代表不篩選
# 回傳 [(day, period, entry), ...]，依星期、節次排序
def queryTimetable(timetable, day=None, period=None, itemId=None):
    results = []
    for dayIndex in range(7):
        if day is not None and dayIndex + 1 != day:
            continue
        for periodIndex, periodName in enumerate(PERIODS):
            if period is not None and periodName != str(period).lower():
                continue
            for entry in timetable[dayIndex][periodIndex]:
                if itemId is not None and entry["id"].upper() != itemId.upper():
                    continue
                results.append((dayIndex + 1, periodName, entry))
    return results


# 檢查空閒時段查詢的輸入，回傳錯誤訊息清單（空清單代表合法）
def validateFreeBlockQuery(dayFrom, dayTo, periodFrom, periodTo, minLength):
    errors = []
    for label, day in [("起始星期", dayFrom), ("結束星期", dayTo)]:
        if not isinstance(day, int) or isinstance(day, bool) or not 1 <= day <= 7:
            errors.append(f"[INVALID_SLOT] {label} {day} 不合法：須為 1–7")
    for label, period in [("起始節次", periodFrom), ("結束節次", periodTo)]:
        if str(period).lower() not in PERIODS:
            errors.append(f"[INVALID_SLOT] {label} {period} 不合法：須為 1–9、a、b、c")
    if not isinstance(minLength, int) or isinstance(minLength, bool) or minLength < 1:
        errors.append(f"[INVALID_VALUE] 最少連續節數 {minLength} 不合法：須為 ≥ 1 的整數")
    if errors:
        return errors

    if dayFrom > dayTo:
        errors.append(f"[INVALID_TIME_RANGE] 起始星期{DAYS[dayFrom - 1]}晚於結束星期{DAYS[dayTo - 1]}")
    if PERIODS.index(str(periodFrom).lower()) > PERIODS.index(str(periodTo).lower()):
        errors.append(f"[INVALID_TIME_RANGE] 起始節次 {periodFrom} 晚於結束節次 {periodTo}")
    return errors


# FR-3.4：在「星期 dayFrom～dayTo、每天第 periodFrom～periodTo 節」內找連續空閒區段
# 區段不跨日；回傳 (blocks, errors)，blocks 依星期、起始節次排序
# 最少連續節數大於查詢範圍長度時，回傳空結果而非錯誤
def findFreeBlocks(timetable, dayFrom, dayTo, periodFrom, periodTo, minLength=1):
    errors = validateFreeBlockQuery(dayFrom, dayTo, periodFrom, periodTo, minLength)
    if errors:
        return [], errors

    firstIndex = PERIODS.index(str(periodFrom).lower())
    lastIndex = PERIODS.index(str(periodTo).lower())

    blocks = []
    for day in range(dayFrom, dayTo + 1):
        runStart = None
        for periodIndex in range(firstIndex, lastIndex + 2):
            isFree = periodIndex <= lastIndex and not timetable[day - 1][periodIndex]
            if isFree and runStart is None:
                runStart = periodIndex
            elif not isFree and runStart is not None:
                length = periodIndex - runStart
                if length >= minLength:
                    blocks.append({
                        "day": day,
                        "startPeriod": PERIODS[runStart],
                        "endPeriod": PERIODS[periodIndex - 1],
                        "length": length,
                    })
                runStart = None
    return blocks, []


# FR-3.5：統計每日上課節數、每週總學分（只算課程）及每週空堂數
# 空堂：同一天第一節有課與最後一節有課之間沒有任何占用的節次（需求規格第 2 節）
def summarizeTimetable(timetable, studentId, courses, students):
    student = next((s for s in students if s["studentId"] == studentId), None)
    courseIndex = {course["courseId"]: course for course in courses}

    totalCredits = 0
    if student is not None:
        for courseId in student.get("enrolledCourses", []):
            if courseId in courseIndex:
                totalCredits += courseIndex[courseId]["credits"]

    periodsPerDay = []
    gapsPerDay = []
    for dayIndex in range(7):
        busy = [index for index, cell in enumerate(timetable[dayIndex]) if cell]
        periodsPerDay.append(len(busy))
        if busy:
            gapsPerDay.append(busy[-1] - busy[0] + 1 - len(busy))
        else:
            gapsPerDay.append(0)

    return {
        "periodsPerDay": periodsPerDay,
        "totalPeriods": sum(periodsPerDay),
        "totalCredits": totalCredits,
        "gapsPerDay": gapsPerDay,
        "totalGaps": sum(gapsPerDay),
    }


# 單一格子的顯示文字：空格為「.」、活動前加「*」、兩個以上占用顯示「!衝突」（FR-3.6）
def formatCell(cell):
    if not cell:
        return "."
    if len(cell) >= 2:
        return "!衝突"
    entry = cell[0]
    if entry["kind"] == "activity":
        return "*" + entry["id"]
    return entry["id"]


# 課表畫面：標題、7 × 12 表格、活動說明與單次活動日期（FR-3.6、3.7）
def formatTimetable(timetable, studentId, students, totalCredits):
    student = next((s for s in students if s["studentId"] == studentId), {})
    lines = [f"學生：{studentId} {student.get('name', '')} 本週總學分：{totalCredits}"]
    lines.append(f"{'節次':<4}{'時間':<13}" + "".join(f"{name:<10}" for name in DAYS))

    for periodIndex, periodName in enumerate(PERIODS):
        start, end = PERIOD_TIMES[periodName]
        cells = "".join(
            f"{formatCell(timetable[dayIndex][periodIndex]):<10}" for dayIndex in range(7)
        )
        lines.append(f"{periodName:<4}{start}-{end}  " + cells)

    entries = [entry for day in timetable for cell in day for entry in cell]
    if not entries:
        lines.append("目前沒有已選課程")
        return "\n".join(lines)

    lines.append("（* 表示活動，!衝突 表示同一格有兩個以上占用）")

    onceActivities = {}
    for entry in entries:
        if entry["kind"] == "activity" and entry["recurrence"] == "once":
            onceActivities[entry["id"]] = entry
    for activityId in sorted(onceActivities):
        entry = onceActivities[activityId]
        lines.append(f"*{activityId} {entry['name']}：{entry['date']}（單次活動）")

    conflictCells = queryConflictCells(timetable)
    for day, period, cell in conflictCells:
        names = "、".join(entry["id"] for entry in cell)
        lines.append(f"!衝突：星期{DAYS[day - 1]}第{period}節 {names}")

    return "\n".join(lines)


# 找出有兩個以上占用的格子，回傳 [(day, period, cell), ...]
def queryConflictCells(timetable):
    results = []
    for dayIndex in range(7):
        for periodIndex, periodName in enumerate(PERIODS):
            cell = timetable[dayIndex][periodIndex]
            if len(cell) >= 2:
                results.append((dayIndex + 1, periodName, cell))
    return results


# 統計畫面：「每日節數：一 0｜二 2｜…」與「空堂數：N」
def formatSummary(summary):
    dailyText = "｜".join(
        f"{DAYS[dayIndex]} {summary['periodsPerDay'][dayIndex]}" for dayIndex in range(7)
    )
    return f"每日節數：{dailyText}\n空堂數：{summary['totalGaps']}"


# 課表查詢結果畫面
def formatQueryResults(results):
    if not results:
        return "沒有符合條件的課表項目"
    lines = []
    for day, period, entry in results:
        kindName = "課程" if entry["kind"] == "course" else "活動"
        lines.append(
            f"星期{DAYS[day - 1]}第{period}節：[{kindName}] {entry['id']} {entry['name']}"
            f"（教室 {entry['roomId']}）"
        )
    return "\n".join(lines)


# 空閒時段查詢畫面
def formatFreeBlocks(blocks, dayFrom, dayTo, periodFrom, periodTo, minLength):
    lines = [
        f"空閒時段查詢：星期{DAYS[dayFrom - 1]}～星期{DAYS[dayTo - 1]}，"
        f"第 {periodFrom}～{periodTo} 節，至少連續 {minLength} 節"
    ]
    if not blocks:
        lines.append("此範圍內沒有符合條件的空閒時段")
    for block in blocks:
        lines.append(
            f"星期{DAYS[block['day'] - 1]} 第 {block['startPeriod']}～{block['endPeriod']} 節"
            f"（{block['length']} 節）"
        )
    return "\n".join(lines)
