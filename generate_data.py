import json
import random

def generate_classrooms():
    # 建立5間教室
    classrooms = [{"room_id": f"R{100+i}", "capacity": random.choice([40, 50, 60, 80])} for i in range(1, 6)]
    with open('classrooms.json', 'w', encoding='utf-8') as f:
        json.dump(classrooms, f, ensure_ascii=False, indent=4)
    return classrooms

def generate_ntut_students():
    dept_codes = {"310": "電機工程系", "360": "電子工程系", "590": "資訊工程系", "AC1": "互動式多媒體設計系"}
    students = []
    # 建立15名學生
    for i in range(1, 16):
        code = random.choice(list(dept_codes.keys()))
        student_id = f"115{code}{i:03d}"
        students.append({
            "student_id": student_id,
            "name": f"學生{i:02d}",
            "department": dept_codes[code],
            "max_credits": random.choice([20, 25, 30]),
            "enrolled_courses": []
        })
    with open('students.json', 'w', encoding='utf-8') as f:
        json.dump(students, f, ensure_ascii=False, indent=4)
    return students

def generate_courses(classrooms):
    courses = []
    periods = [str(i) for i in range(1, 10)] + ['a', 'b', 'c']
    # 建立 20 門課程[cite: 2]
    for i in range(1, 21):
        day = random.randint(1, 5)
        start_p_idx = random.randint(0, 7)
        duration = random.randint(2, 3)
        schedules = [{"day": day, "period": periods[start_p_idx + j]} for j in range(duration)]
        
        courses.append({
            "course_id": f"C{i:03d}",
            "name": f"測試課程{i:02d}",
            "credits": duration,
            "is_required": random.choice([True, False]),
            "teacher": f"教師{random.randint(1, 10):02d}",
            "max_students": random.randint(30, 60),
            "room_id": random.choice(classrooms)["room_id"],
            "schedules": schedules
        })
    with open('courses.json', 'w', encoding='utf-8') as f:
        json.dump(courses, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    rooms = generate_classrooms()
    generate_ntut_students()
    generate_courses(rooms)
    print("成功建立 classrooms.json, students.json, courses.json")