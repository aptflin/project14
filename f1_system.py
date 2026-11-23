# 把 JSON 檔案讀進來，找不到檔案或內容格式不對時，回傳空清單
def loadData(fileName):
    from scheduler.storage import load_legacy_file
    return load_legacy_file(fileName)


def saveData(fileName, data):
    from scheduler.storage import save_legacy_file
    return save_legacy_file(fileName, data)


# 檢查代號是否重複
def validateUniqueId(newId, existingData, idKey):
    for item in existingData:
        if item.get(idKey) == newId:
            return False, f"錯誤：代號 '{newId}' 已存在，不得重複。"

    return True, ""


# 檢查學分和修課人數上限是否合理
def validateCourseParams(credits, maxStudents):
    if not isinstance(credits, int) or credits <= 0:
        return False, "錯誤：學分必須為正整數。"

    if not isinstance(maxStudents, int) or maxStudents < 1:
        return False, "錯誤：課程人數上限不得小於 1。"

    return True, ""


# 確認星期與節次是否合理
def validateSchedule(day, period):
    if not isinstance(day, int) or not (1 <= day <= 7):
        return False, "錯誤：星期僅限 1-7。"

    validPeriods = [
        str(periodNumber) for periodNumber in range(1, 10)
    ] + ["a", "b", "c"]

    if str(period).lower() not in validPeriods:
        return False, "錯誤：節次僅限 1-9、a、b、c。"

    return True, ""


# 檢查是否有學生已選修該課程，若有則拒絕刪除
def validateCourseDeletion(courseId, studentsData):
    for student in studentsData:
        if courseId in student.get("enrolledCourses", []):
            studentId = student.get("studentId", "未知")
            return False, f"錯誤：學生 {studentId} 已選修，拒絕刪除。"

    return True, ""


# 檢查新課程資料；若無錯誤，便加入課程清單
def addCourse(courseData, coursesList, classroomsList):
    isValid, msg = validateUniqueId(
        courseData["courseId"], coursesList, "courseId"
    )
    if not isValid:
        return False, msg

    isValid, msg = validateCourseParams(
        courseData["credits"], courseData["maxStudents"]
    )
    if not isValid:
        return False, msg

    for schedule in courseData.get("schedules", []):
        isValid, msg = validateSchedule(
            schedule["day"], schedule["period"]
        )
        if not isValid:
            return False, msg

    validRooms = [room["roomId"] for room in classroomsList]

    if courseData["roomId"] not in validRooms:
        return False, "錯誤：教室代號不存在。"

    coursesList.append(courseData)
    return True, "新增成功"


# 刪除指定課程，假如有人選修，就不刪除
def deleteCourse(courseId, coursesList, studentsList):
    courseExists = any(
        course["courseId"] == courseId for course in coursesList
    )

    if not courseExists:
        return False, "找不到該課程"

    isValid, msg = validateCourseDeletion(courseId, studentsList)
    if not isValid:
        return False, msg

    for index, course in enumerate(coursesList):
        if course["courseId"] == courseId:
            del coursesList[index]
            return True, "刪除成功"

    return False, "找不到該課程"


# 計算目前有幾位學生選修該課程
def getEnrolledCount(courseId, studentsList):
    return sum(
        1
        for student in studentsList
        if courseId in student.get("enrolledCourses", [])
    )


# 查詢課程，依照指定條件回傳符合的課程清單
def queryCourses(
    coursesList,
    studentsList,
    qId=None,
    qTeacher=None,
    qDay=None,
    qReq=None,
    qVacancy=None,
):
    results = []

    for course in coursesList:
        # 依課程代號篩選
        if qId and qId not in course["courseId"]:
            continue

        # 依授課教師篩選
        if qTeacher and qTeacher not in course["teacher"]:
            continue

        # 依必修或選修篩選
        if qReq is not None:
            if course["isRequired"] != qReq:
                continue

        # 依星期篩選
        if qDay:
            days = [
                str(schedule["day"])
                for schedule in course.get("schedules", [])
            ]

            if str(qDay) not in days:
                continue

        # 修正：明確區分有名額、額滿及不篩選三種情況
        if qVacancy is not None:
            enrolled = getEnrolledCount(course["courseId"], studentsList)

            hasVacancy = course["maxStudents"] - enrolled > 0

            if hasVacancy != qVacancy:
                continue

        results.append(course)

    return results


# 主程式，啟動課程與學生資料管理選單
def main():
    from scheduler.cli import run_legacy
    run_legacy()


if __name__ == "__main__":
    main()
