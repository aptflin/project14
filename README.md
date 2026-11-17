# project14：課程與學生資料管理

## 一鍵自動化測試

在本專案目錄先安裝測試依賴，再執行：

```powershell
python -m pip install -r requirements.txt
python -B -X utf8 run_tests.py
```

程式會執行根目錄的 unittest 與 `tests/` 中的 pytest 測試，輸出逐項結果，並產生：

- `test-results/report.html`：可直接用瀏覽器開啟的報告。
- `test-results/results.json`：包含統計、各案例結果與錯誤詳情。
- `test-results/results.txt`：完整測試輸出。

全部通過回傳結束碼 0；失敗、執行錯誤或沒有找到測試則回傳 1。可用 `--pattern test_f2_system.py` 單獨執行 F2，或用 `--report-dir` 指定報告目錄。

| 測試檔案 | 範圍 |
| --- | --- |
| `test_f1_system.py` | 課程新增、重複代號、學生代號驗證、非法輸入、刪除保護、組合查詢及 JSON 儲存 |
| `test_f2_system.py` | 學生／教室／活動衝堂、學分、名額、排序及命令列儲存 |
| `test_f3_system.py` | 課表、查詢、連續空閒時段與學分統計 |
| `test_f4_system.py` | 活動資料、教室配置、設備、容量、日期、報名與取消 |
| `test_integration.py` | 建課→加選→課表，以及活動建立→報名→取消→課表 |
| `test_review_regressions.py` | Code Review 發現的取消活動、單次日期及損壞活動檔案問題 |
| `tests/test_f5_filter.py` | F5 條件聯集、全部排除原因、可行性、規格格式與選單整合 |
| `tests/test_f6_storage_and_system.py` | F6 v1 JSON 儲存、逐筆容錯、損壞檔案備份、參照檢查及儲存錯誤 |

所有測試使用記憶體或暫存資料，不會覆寫專案現有的課程、學生與活動 JSON。F1 僅測試目前已實作 API，未將尚未提供的學生 CRUD 或課程修改功能視為已完成。

**既有問題狀態：**GitHub `d2a837f` 的 5 個回歸案例中，取消活動與單次日期的 4 個案例已由 F5 導入的共用衝突函式修正。目前仍有 1 項既有問題：`f1_system.py` 的 `loadData()` 遇到格式錯誤的 `activities.json` 會回傳空清單，舊選單仍可能因此判定加選成功並儲存 `students.json`。此問題與 F5 篩選功能無關，屬後續 F6 整合範圍。

**失敗案例詳情：**`test_review_regressions.py::ReviewRegressionTests::test_corrupt_activity_file_cannot_persist_enrollment` 預期活動檔案損壞時不得寫入學生資料；目前實際仍會儲存，因此此案例保持失敗，不略過。最近一次本機完整測試共 94 項，93 項通過、1 項失敗；F5 的 34 項 pytest 案例全部通過。HTML、JSON 與文字報告位於 `test-results/`。

已加入 `.github/workflows/tests.yml`。將測試檔與 workflow 提交並推送至 GitHub 後，每次 push、pull request 或手動執行 Actions，都會在 Ubuntu／Windows、Python 3.11／3.12 上安裝依賴並執行全套測試，即使失敗也會上傳報告。既有檔案問題未修正前 Actions 會顯示失敗。

本機報告與 Python 快取已加入 `.gitignore`，不需提交。

## F5 多條件課程篩選與可行性檢查

F5 新增選單第 11 項，提供唯讀的多條件課程篩選與可行性檢查；不會直接加選或修改課程、學生及活動資料。

執行 `python f1_system.py`，選擇 **11**，依序輸入學號、希望課程、必修課程、最低／最高學分、不可上課時段及偏好星期。多項條件用逗號或空白分隔；例如 `2-3,5-a`，星期五全天可輸入 `5-*`。留空偏好星期代表不限。

依三份 v1 PDF 實作 FR-5.1～5.6：候選取希望與必修聯集；列出不存在、取消、額滿、禁課時段、已選課程及活動衝突等全部排除原因；偏好星期只標記；收集全部不可行原因。可選及排除清單都採必修優先、課程代號排序。

F5 為唯讀檢查，回報「可能可行」不代表已找到可同時加選的組合，最佳課表搜尋留待 F7。已選課程不重複加入候選或計分；已選必修視為已滿足，學分範圍包含目前學分。新必修加上既有學分超過最高學分時，也會回報不可行。

正式服務為 `scheduler.course_filter.filter_courses(data, sid, criteria)`，回傳 `Result(data=FilterReport)`；`f5_system.filterCourses(...)` 相容目前 camelCase 清單與 PDF 的 snake_case／`schema_version=1` 包裝。活動報名使用 v1 的 `participants`，舊 `enrolledActivities` 則經轉接，不修改原 JSON。共用時間規則集中於 `scheduler/conflict.py`，F2／F4／F5 均使用。

F5 專用驗收：

```powershell
python -m pip install -r requirements.txt
python -m pytest -v tests/test_f5_filter.py
python -m pytest tests/test_f5_filter.py -m boundary
```

目前新增 34 個 F5 案例；完整一鍵報告可用原本的 `python run_tests.py`，會合併 F1–F5 結果。詳細介面、需求對照與範例見 [F5 說明](docs/f5.md)。

## F6：系統資料儲存與載入

F6 的儲存模組位於 `scheduler/storage.py`，提供 `StorageSystemData`、`load_all(data_dir)` 與 `save_all(data, data_dir)`。資料採 `schema_version: 1` 搭配 `records` 清單格式，分別處理 `classrooms.json`、`courses.json`、`students.json`、`activities.json` 和 `enrollments.json`。

載入時會逐筆驗證資料、略過無效紀錄並產生 `LoadReport`；JSON 損壞時會先備份原檔。儲存時使用暫存檔與 `os.replace`，避免單一檔案寫入中途留下不完整內容。

F6 測試位於 `tests/test_f6_storage_and_system.py`，涵蓋正常儲存載入、邊界值、無效資料、參照檢查及儲存失敗等情境。混合有效與錯誤課程資料的 fixture 位於 `tests/fixtures/broken/courses.json`。可單獨執行 F6 測試：

```powershell
python -m pytest -v tests/test_f6_storage_and_system.py
```

或透過專案測試 runner 執行並產生報告：

```powershell
python run_tests.py --pattern test_f6_storage_and_system.py
```

目前 F6 儲存模組尚未取代 `f1_system.py` 的既有資料讀寫流程；兩者的資料欄位與格式不同，正式串接前仍需完成相容轉換。

執行系統本身使用 Python 3 標準函式庫；執行完整測試需另外安裝 `requirements.txt` 中的 pytest。請先切換到本專案目錄，再執行：

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
