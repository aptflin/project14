# project14：課程與學生資料管理

使用 Python 3，無額外套件。請先切換到本專案目錄，再執行：

```powershell
python f1_system.py
```

保留 F1 選單 1–4，新增 F2：

| 選項 | 功能 |
| --- | --- |
| 5 | 檢查加選，不修改資料 |
| 6 | 加選課程，全部檢查通過才寫入 students.json |
| 7 | 檢查活動，不修改資料 |
| 8 | 參加活動，全部檢查通過才寫入 students.json |
| 9 | 查詢所有教室的課程／活動衝堂 |
| 10 | 列出活動 |

F2 一次檢查學生課程與活動時段、教室時段、學分上限及課程名額，並拒絕重複加選／報名。時段衝突依星期 1–7、節次 1–9、a、b、c 排序，同一時段若同時發生學生及教室衝突，兩者均列出。學分與名額限制獨立列出，不會因已有衝突而略過。每個重疊節次列為一筆衝突，以免多節或跨日衝突遭遺漏。

選課／參加活動時，教室檢查涵蓋該目標與所有已配置課程及活動，即使學生未參加對方，也會檢查。其他教室的既有衝突可透過選項 9 全面查詢。每門課／活動沿用 F1 的單一 `roomId`，所有 `schedules` 皆在該教室；活動不計學分，亦未設定活動人數上限。

活動資料預設為空。可編輯 `activities.json`，例如：

```json
[
    {
        "activityId": "A001",
        "name": "程式設計讀書會",
        "roomId": "R101",
        "schedules": [
            {"day": 4, "period": "5"},
            {"day": 4, "period": "6"}
        ]
    }
]
```

學生參加活動後，在 `students.json` 的該筆學生新增 `enrolledActivities`，例如 `["A001"]`。原 F1 學生沒有這個欄位時視為尚未參加任何活動。教室必須存在於 `classrooms.json`。活動代號須唯一，星期／節次格式與 F1 相同。

名額依 `students.json` 中實際已選該課的學生數計算，學分依已選課程加總。找不到學生、課程、已選資料，或相關時段格式不合法時，檢查會失敗；檢查失敗不會改寫學生資料。

執行驗收測試（測試使用獨立資料，不修改現有 JSON）：

```powershell
python -m unittest -v
```

測試涵蓋多日衝突、課程與活動、三種教室配對、夜間節次排序、同時超學分及額滿、學分恰好達上限、重複加選、未知代號，以及命令列的成功儲存／失敗不儲存。

## F3：個人課表與空閒時段（`f3_system.py`，需求規格 FR-3.1～3.7）

F3 只提供函式，不修改 `f1_system.py` 的選單；選單整合由組長負責（WBS 3.18），呼叫方式如下：

| 函式 | 用途 | 回傳 |
| --- | --- | --- |
| `buildTimetable(studentId, courses, students, activities)` | 已選課程＋已報名活動轉為 7 × 12 課表，每格是占用清單 | `(timetable, errors)` |
| `queryTimetable(timetable, day, period, itemId)` | 依星期／節次／代號查詢，`None` 為不篩選 | `[(day, period, entry)]` |
| `findFreeBlocks(timetable, dayFrom, dayTo, periodFrom, periodTo, minLength)` | 每天第 periodFrom～periodTo 節內的連續空閒區段，不跨日 | `(blocks, errors)` |
| `summarizeTimetable(timetable, studentId, courses, students)` | 每日節數、每週總學分（只算課程）、空堂數 | `dict` |
| `formatTimetable`／`formatSummary`／`formatQueryResults`／`formatFreeBlocks` | 產生顯示字串（`.` 空格、`*` 活動、`!衝突`、單次活動日期） | `str` |

起始星期或節次晚於結束、星期／節次不合法時回傳 `[INVALID_TIME_RANGE]`／`[INVALID_SLOT]` 錯誤；最少連續節數大於範圍長度時回傳空結果。已取消的活動不顯示。

## F4：校園活動與教室配置（`f4_system.py`，需求規格 FR-4.1～4.8）

| 函式 | 用途 |
| --- | --- |
| `prepareActivity(data, existingActivities)` | 驗證欄位（一次列出所有錯誤）並把日期、時間換算成 `schedules` |
| `findSuitableRooms(activity, courses, activities, classrooms)` | 合適教室（容量由小到大）及每間教室未滿足的條件 |
| `addActivity(data, activities, courses, classrooms)` | 新增；`roomId` 為 `None` 時以「未配置教室」建立 |
| `updateActivity(activityId, changes, ...)` | 修改後重新驗證與檢查教室；預計人數不得低於已報名人數 |
| `cancelActivity(activityId, activities, students)` | 狀態改為 `cancelled`、釋放教室、回傳受影響學號 |
| `queryActivities(activities, qDate, qType, qRoom, qStatus)` | 依日期、類型、教室、狀態查詢 |
| `registerActivity(studentId, activityId, ...)` | 報名；上限 = min(預計人數, 教室容量)，時段衝突沿用 F2 |
| `formatActivity`／`formatAllocation` | 產生需求規格 F4 輸出範例格式的字串 |

活動欄位（沿用 F1／F2 的 camelCase；`schedules` 由日期與時間換算，供 F2 使用）：

```json
{
    "activityId": "EV005",
    "name": "AI 講座",
    "activityType": "lecture",
    "date": "2026-10-15",
    "startTime": "13:30",
    "endTime": "15:30",
    "recurrence": "once",
    "expectedAttendees": 80,
    "requiredEquipment": ["projector", "microphone"],
    "roomId": "ADM-301",
    "organizer": "資工系學會",
    "status": "scheduled",
    "schedules": [{"day": 4, "period": "6"}, {"day": 4, "period": "7"}, {"day": 4, "period": "8"}]
}
```

- 節次時間依需求規格 3.1（第 5 節 12:10–13:00 … 第 c 節 19:10–20:00），活動時間須在 08:10–20:00。
- 衝突的日期規則依需求規格 3.5：至少一方每週重複，或兩者都是單次且同一天才算衝突；課程一律視為每週。
- 教室可選欄位：`equipment`（設備代碼清單）、`status`（`active`／`disabled`）、`unavailableSlots`（格式同 `schedules`）；未填時視為無設備、啟用、無停用時段。

執行 F3／F4 測試：

```powershell
python -m unittest -v test_f3_system test_f4_system
```
