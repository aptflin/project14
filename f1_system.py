import json
import os


# 把 JSON 檔案讀進來，找不到檔案或內容格式不對時，回傳空清單
def loadData(fileName):
    if not os.path.exists(fileName):
        return []

    try:
        with open(fileName, "r", encoding="utf-8") as fileHandle:
            return json.load(fileHandle)
    except json.JSONDecodeError:
        print(f"錯誤：{fileName} 格式異常")
        return []


# 把資料存回指定的 JSON 檔案
def saveData(fileName, data):
    with open(fileName, "w", encoding="utf-8") as fileHandle:
        json.dump(data, fileHandle, ensure_ascii=False, indent=4)


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
    from f2_system import (
        checkEnrollment, enrollCourse, checkActivityParticipation, joinActivity,
        checkClassroomConflicts, formatResult, DAYS,
    )

    courses = loadData("courses.json")
    students = loadData("students.json")
    classrooms = loadData("classrooms.json")
    activities = loadData("activities.json")

    while True:
        print("\n--- 課程與學生資料管理 (F1)／多層次衝堂與選課檢查 (F2) ---")
        print("1. 新增課程")
        print("2. 刪除課程")
        print("3. 查詢課程")
        print("4. 列出所有學生")
        print("5. 檢查加選（不儲存）")
        print("6. 加選課程")
        print("7. 檢查活動（不儲存）")
        print("8. 參加活動")
        print("9. 檢查所有教室衝堂")
        print("10. 列出活動")
        print("0. 離開系統")

        choice = input("請選擇操作: ").strip()

        if choice == "1":
            courseId = input("課程代號: ").strip()
            name = input("課程名稱: ").strip()

            # 防止學分輸入非數字時造成程式中斷。
            try:
                credits = int(input("學分: "))
                maxStudents = int(input("人數上限: "))
                day = int(input("星期 (1-7): "))
            except ValueError:
                print("錯誤：學分、人數上限及星期必須輸入整數。")
                continue

            isReqStr = input("是否必修 (y/n): ").strip().lower()
            if isReqStr not in ("y", "n"):
                print("錯誤：請輸入 y 或 n。")
                continue

            isReq = isReqStr == "y"
            teacher = input("授課教師: ").strip()
            room = input("教室代號: ").strip()
            period = input("節次 (1-9,a,b,c): ").strip().lower()

            newCourse = {
                "courseId": courseId,
                "name": name,
                "credits": credits,
                "isRequired": isReq,
                "teacher": teacher,
                "maxStudents": maxStudents,
                "roomId": room,
                "schedules": [{"day": day, "period": period}],
            }

            success, msg = addCourse(newCourse, courses, classrooms)
            print(msg)

            if success:
                saveData("courses.json", courses)

        elif choice == "2":
            courseId = input("輸入欲刪除的課程代號: ").strip()

            success, msg = deleteCourse(courseId, courses, students)
            print(msg)

            if success:
                saveData("courses.json", courses)

        elif choice == "3":
            print("直接按 Enter 略過該條件")

            qId = input("課程代號: ").strip() or None
            qTeacher = input("教師名稱: ").strip() or None
            qDay = input("星期: ").strip() or None

            qReqStr = input("是否必修 (y/n): ").strip().lower()

            if qReqStr == "y":
                qReq = True
            elif qReqStr == "n":
                qReq = False
            else:
                qReq = None

            qVacStr = (
                input("是否須有剩餘名額 (y/n，Enter 略過): ").strip().lower()
            )

            # 修正：n 代表只查詢額滿課程；Enter 才是不篩選。
            if qVacStr == "y":
                qVac = True
            elif qVacStr == "n":
                qVac = False
            else:
                qVac = None

            results = queryCourses(
                courses, students, qId, qTeacher, qDay, qReq, qVac
            )

            print(f"\n--- 查詢結果 (共 {len(results)} 筆) ---")

            for result in results:
                print(
                    f"[{result['courseId']}] {result['name']}\n"
                    f"{result['teacher']} "
                    f"(學分:{result['credits']}, "
                    f"上限:{result['maxStudents']})"
                )

                enrolled = getEnrolledCount(result["courseId"], students)
                remaining = result["maxStudents"] - enrolled

                print(
                    f"已選修人數：{enrolled}，"
                    f"剩餘名額：{remaining}"
                )

        elif choice == "4":
            print(f"\n--- 學生列表 (共 {len(students)} 筆) ---")

            for student in students:
                print(
                    f"{student['studentId']}\n"
                    f"{student['name']} "
                    f"({student['department']})"
                )

        elif choice in ("5", "6", "7", "8"):
            studentId = input("學號: ").strip()
            isCourse = choice in ("5", "6")
            targetId = input("課程代號: " if isCourse else "活動代號: ").strip()
            operation = {
                "5": checkEnrollment, "6": enrollCourse,
                "7": checkActivityParticipation, "8": joinActivity,
            }[choice]
            result = operation(studentId, targetId, courses, students, activities, classrooms)
            print(formatResult(result))
            if result["success"] and choice in ("6", "8"):
                saveData("students.json", students)
                print("加選成功，已儲存。" if isCourse else "活動報名成功，已儲存。")

        elif choice == "9":
            result = checkClassroomConflicts(courses, activities)
            for number, conflict in enumerate(result["conflicts"], 1):
                print(
                    f"衝突{number}：教室 {conflict['roomId']} "
                    f"星期{DAYS[conflict['day'] - 1]}第{conflict['period']}節\n"
                    f"{conflict['targetId']} {conflict['targetName']}／"
                    f"{conflict['otherId']} {conflict['otherName']}"
                )
            for message in result["errors"]:
                print(f"錯誤：{message}")
            if result["success"]:
                print("所有教室配置檢查通過。")

        elif choice == "10":
            for activity in activities:
                print(f"{activity['activityId']} {activity['name']}（教室 {activity.get('roomId', '未設定')}）")
            if not activities:
                print("尚無活動，請依 README 格式設定 activities.json。")

        elif choice == "0":
            print("系統結束。")
            break

        else:
            print("無效的選項。")


if __name__ == "__main__":
    main()
