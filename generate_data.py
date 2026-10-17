import json
import random



def generateClassrooms(): #自動生成5間教室的測試資料
    classrooms = [{"roomId": f"R{100 + roomOffset}", "capacity": random.choice([40, 50, 60, 80])} for roomOffset in range(1, 6)]
    with open('classrooms.json', 'w', encoding='utf-8') as fileHandle:
        json.dump(classrooms, fileHandle, ensure_ascii=False, indent=4)
    return classrooms

def generateNtutStudents(): #自動生成15位學生
    deptCodes = {"310": "電機工程系", "360": "電子工程系", "590": "資訊工程系", "AC1": "互動式多媒體設計系"}
    
    # 打亂姓名，讓每次產生的學生名單都有不同組合
    studentNames = [
        "蔡徐坤", "林信宏", "張家瑋", "王柏翰", "李俊傑", 
        "黃建宏", "吳宗翰", "鄭吉棠", "蔡明軒", "楊哲維", 
        "許家銘", "鄭宇翔", "謝承翰", "郭宇軒", "洪偉哲"
    ]
    random.shuffle(studentNames)

    students = []
    for studentIndex in range(1, 16):
        code = random.choice(list(deptCodes.keys()))
        studentId = f"115{code}{studentIndex:03d}"
        students.append({
            "studentId": studentId,
            "name": studentNames[studentIndex-1],
            "department": deptCodes[code],
            "maxCredits": random.choice([20, 25, 30]),
            "enrolledCourses": []
        })
    with open('students.json', 'w', encoding='utf-8') as fileHandle:
        json.dump(students, fileHandle, ensure_ascii=False, indent=4)
    return students

def generateCourses(classrooms): #自動生成20個課程的詳細資料
    courses = []
    periods = [str(i) for i in range(1, 10)] + ['a', 'b', 'c']
    
    courseNames = [
        "計算機程式設計", "微積分", "線性代數", "資料結構", "演算法",
        "作業系統", "計算機組織", "計算機網路", "資料庫系統", "軟體工程",
        "物件導向程式設計", "離散數學", "人工智慧", "機器學習", "編譯器設計",
        "網路安全", "分散式系統", "嵌入式系統", "人機介面", "設計管理", "專案管理"
    ]
    random.shuffle(courseNames)
    
    teacherNames = [
        "李大明", "王建民", "林雅婷", "陳文印", "張志宏",
        "吳明慧", "劉建國", "郭俊傑", "蔡佳玲", "黃信宏"
    ]
    
    # 每門課隨機安排星期、連續節次和教室
    for courseIndex in range(1, 21):
        day = random.randint(1, 5)
        startPeriodIndex = random.randint(0, 7)
        duration = random.randint(2, 3)
        schedules = [{"day": day, "period": periods[startPeriodIndex + periodOffset]} for periodOffset in range(duration)]
        
        courses.append({
            "courseId": f"C{courseIndex:03d}",
            "name": courseNames[courseIndex-1],
            "credits": duration,
            "isRequired": random.choice([True, False]),
            "teacher": random.choice(teacherNames),
            "maxStudents": random.randint(30, 60),
            "roomId": random.choice(classrooms)["roomId"],
            "schedules": schedules
        })
        
    with open('courses.json', 'w', encoding='utf-8') as fileHandle:
        json.dump(courses, fileHandle, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    # 產生教室、學生和課程資料。
    rooms = generateClassrooms()
    generateNtutStudents()
    generateCourses(rooms)
    print("成功建立 classrooms.json, students.json, courses.json")