import json
import random

def generate_classrooms():
    classrooms = [{"room_id": f"R{100+i}", "capacity": random.choice([40, 50, 60, 80])} for i in range(1, 6)]
    with open('classrooms.json', 'w', encoding='utf-8') as fileHandle:
        json.dump(classrooms, fileHandle, ensure_ascii=False, indent=4)
    return classrooms

def generate_ntut_students():
    deptCodes = {"310": "電機工程系", "360": "電子工程系", "590": "資訊工程系", "AC1": "互動式多媒體設計系"}
    
    # 打亂姓名，讓每次產生的學生名單都有不同組合。
    student_names = [
        "陳冠宇", "林信宏", "張家瑋", "王柏翰", "李俊傑", 
        "黃建宏", "吳宗翰", "劉致遠", "蔡明軒", "楊哲維", 
        "許家銘", "鄭宇翔", "謝承翰", "郭宇軒", "洪偉哲"
    ]
    random.shuffle(student_names)

    students = []
    for i in range(1, 16):
        code = random.choice(list(deptCodes.keys()))
        studentId = f"115{code}{i:03d}"
        students.append({
            "student_id": studentId,
            "name": student_names[i-1],
            "department": deptCodes[code],
            "max_credits": random.choice([20, 25, 30]),
            "enrolled_courses": []
        })
    with open('students.json', 'w', encoding='utf-8') as fileHandle:
        json.dump(students, fileHandle, ensure_ascii=False, indent=4)
    return students

def generate_courses(classrooms):
    courses = []
    periods = [str(i) for i in range(1, 10)] + ['a', 'b', 'c']
    
    course_names = [
        "計算機程式設計", "微積分", "線性代數", "資料結構", "演算法",
        "作業系統", "計算機組織", "計算機網路", "資料庫系統", "軟體工程",
        "物件導向程式設計", "離散數學", "人工智慧", "機器學習", "編譯器設計",
        "網路安全", "分散式系統", "嵌入式系統", "人機介面", "設計管理", "專案管理"
    ]
    random.shuffle(course_names)
    
    teacher_names = [
        "李大明", "王建民", "林雅婷", "陳文印", "張志宏",
        "吳明慧", "劉建國", "郭俊傑", "蔡佳玲", "黃信宏"
    ]
    
    # 每門課隨機安排星期、連續節次和教室。
    for i in range(1, 21):
        day = random.randint(1, 5)
        startPeriodIndex = random.randint(0, 7)
        duration = random.randint(2, 3)
        schedules = [{"day": day, "period": periods[startPeriodIndex + j]} for j in range(duration)]
        
        courses.append({
            "course_id": f"C{i:03d}",
            "name": course_names[i-1],
            "credits": duration,
            "is_required": random.choice([True, False]),
            "teacher": random.choice(teacher_names),
            "max_students": random.randint(30, 60),
            "room_id": random.choice(classrooms)["room_id"],
            "schedules": schedules
        })
        
    with open('courses.json', 'w', encoding='utf-8') as fileHandle:
        json.dump(courses, fileHandle, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    # 產生教室、學生和課程資料。
    rooms = generate_classrooms()
    generate_ntut_students()
    generate_courses(rooms)
    print("成功建立 classrooms.json, students.json, courses.json")