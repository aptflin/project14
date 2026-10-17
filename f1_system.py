import json
import os

# 把 JSON 檔案讀進來；找不到檔案或內容格式不對時，就先回傳空清單。
def loadData(fileName):
    if not os.path.exists(fileName):
        return []
    try:
        with open(fileName, 'r', encoding='utf-8') as fileHandle:
            return json.load(fileHandle)
    except json.JSONDecodeError:
        print(f"錯誤：{fileName} 格式異常。")
        return []

# 把資料存回指定的 JSON 檔案
def saveData(fileName, data):  
    with open(fileName, 'w', encoding='utf-8') as fileHandle:
        json.dump(data, fileHandle, ensure_ascii=False, indent=4)

# 檢查代號是否被用過，回傳檢查結果和錯誤訊息。
def validateUniqueId(newId, existingData, idKey):
    for item in existingData:
        if item.get(idKey) == newId:
            return False, f"錯誤：代號 '{newId}' 已存在，不得重複。" 
    return True, ""

# 檢查學分和修課人數上限是否合理。
def validateCourseParams(credits, maxStudents):
    if not isinstance(credits, int) or credits <= 0:
        return False, "錯誤：學分必須為正整數。" 
    if not isinstance(maxStudents, int) or maxStudents < 1:
        return False, "錯誤：課程人數上限不得小於 1。" 
    return True, ""

# 確認星期與節次是否合理。
def validateSchedule(day, period):
    if not isinstance(day, int) or not (1 <= day <= 7):
        return False, "錯誤：星期僅限 1-7。" 
    validPeriods = [str(periodNumber) for periodNumber in range(1, 10)] + ['a', 'b', 'c', 'A', 'B', 'C']
    if str(period) not in validPeriods:
        return False, "錯誤：節次僅限 1-9、a、b、c。" 
    return True, ""

# 檢查是否有學生已選修該課程，若有則拒絕刪除。
def validateCourseDeletion(courseId, studentsData):
    for student in studentsData:
        if courseId in student.get("enrolled_courses", []):
            return False, f"錯誤：學生 {student['student_id']} 已選修，拒絕刪除。" 
    return True, ""

# 檢查新課程資料和教室代號；若有錯誤回傳 False，否則把課程加入清單並回傳 True。
def addCourse(courseData, coursesList, classroomsList):
    isValid, msg = validateUniqueId(courseData['course_id'], coursesList, 'course_id')
    if not isValid: return False, msg
    
    isValid, msg = validateCourseParams(courseData['credits'], courseData['max_students'])
    if not isValid: return False, msg
    
    for schedule in courseData.get('schedules', []):
        isValid, msg = validateSchedule(schedule['day'], schedule['period'])
        if not isValid: return False, msg

    validRooms = [room['room_id'] for room in classroomsList]
    if courseData['room_id'] not in validRooms:
        return False, "錯誤：教室代號不存在。"

    coursesList.append(courseData)
    return True, "新增成功"

# 刪除指定課程，假如有人選修就不刪除。
def deleteCourse(courseId, coursesList, studentsList):
    isValid, msg = validateCourseDeletion(courseId, studentsList)
    if not isValid: return False, msg
    
    for index, course in enumerate(coursesList):
        if course['course_id'] == courseId:
            del coursesList[index]
            return True, "刪除成功"
    return False, "找不到該課程"

# 計算目前幾位學生選了這門課。
def getEnrolledCount(courseId, studentsList):
    count = 0
    for student in studentsList:
        if courseId in student.get("enrolled_courses", []):
            count += 1
    return count

# 查詢課程，依條件回傳符合的課程清單。
def queryCourses(coursesList, studentsList, qId=None, qTeacher=None, qDay=None, qReq=None, qVacancy=None):
    results = []
    for course in coursesList:
        if qId and qId not in course['course_id']: continue
        if qTeacher and qTeacher not in course['teacher']: continue
        if qReq is not None and course['is_required'] != qReq: continue
        
        if qDay:
            days = [str(schedule['day']) for schedule in course.get('schedules', [])]
            if str(qDay) not in days: continue
            
        if qVacancy:
            enrolled = getEnrolledCount(course['course_id'], studentsList)
            if course['max_students'] - enrolled <= 0: continue
            
        results.append(course)
    return results

# 主程，啟動課程管理選單，使用者能新增、刪除、查詢課程或查看學生。
def main():
    courses = loadData('courses.json')
    students = loadData('students.json')
    classrooms = loadData('classrooms.json')

    while True:
        print("\n--- 課程與學生資料管理 (F1) ---")
        print("1. 新增課程")
        print("2. 刪除課程")
        print("3. 查詢課程")
        print("4. 列出所有學生")
        print("0. 離開系統")
        choice = input("請選擇操作: ")

        if choice == '1':
            courseId = input("課程代號: ")
            name = input("課程名稱: ")
            credits = int(input("學分: "))
            isReq = input("是否必修 (y/n): ").lower() == 'y'
            teacher = input("授課教師: ")
            maxStudents = int(input("人數上限: "))
            room = input("教室代號: ")
            
            day = int(input("星期 (1-7): "))
            period = input("節次 (1-9,a,b,c): ")
            
            newCourse = {
                "course_id": courseId, "name": name, "credits": credits,
                "is_required": isReq, "teacher": teacher,
                "max_students": maxStudents, "room_id": room,
                "schedules": [{"day": day, "period": period.lower()}]
            }
            success, msg = addCourse(newCourse, courses, classrooms)
            print(msg)
            if success: saveData('courses.json', courses)

        elif choice == '2':
            courseId = input("輸入欲刪除的課程代號: ")
            success, msg = deleteCourse(courseId, courses, students)
            print(msg)
            if success: saveData('courses.json', courses)

        elif choice == '3':
            print("直接按 Enter 略過該條件")
            qId = input("課程代號: ") or None
            qTeacher = input("教師名稱: ") or None
            qDay = input("星期: ") or None
            qReqStr = input("是否必修 (y/n): ")
            qReq = True if qReqStr.lower() == 'y' else (False if qReqStr.lower() == 'n' else None)
            qVacStr = input("是否須有剩餘名額 (y/n): ")
            qVac = True if qVacStr.lower() == 'y' else None

            results = queryCourses(courses, students, qId, qTeacher, qDay, qReq, qVac)
            print(f"\n--- 查詢結果 (共 {len(results)} 筆) ---")
            for result in results:
                # 修正跨行字串語法錯誤
                print(f"[{result['course_id']}] {result['name']} \n{result['teacher']} (學分:{result['credits']}, 上限:{result['max_students']})")

        elif choice == '4':
            print(f"\n--- 學生列表 (共 {len(students)} 筆) ---")
            for student in students:
                # 修正跨行字串語法錯誤
                print(f"{student['student_id']} \n{student['name']} ({student['department']})")

        elif choice == '0':
            print("系統結束。")
            break
        else:
            print("無效的選項。")

if __name__ == "__main__":
    main()