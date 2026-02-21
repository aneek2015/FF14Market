FF14 Market App - Antigravity SKILL Definitions

本文件定義了 FF14 市場板查詢工具專案中的核心功能技能 (Skills)。每個技能都對應程式碼中的具體邏輯，並標準化了輸入 (Inputs) 與輸出 (Outputs)。

🔧 領域：市場情報 (Market Intelligence)

來源檔案: market_api.py

Skill: fetch_market_prices

功能描述:
從 Universalis API 批量獲取指定伺服器或資料中心的一個或多個物品的市場價格數據。此技能包含網路重試機制 (Retry Policy) 以應對 API 不穩定的情況。

輸入參數 (Inputs):

region_or_server (string): 目標伺服器或資料中心名稱 (例如: "Bahamut", "Gaia", "Japan")。

item_ids (list[int]): 物品 ID 列表。

輸出 (Outputs):

market_data (list[dict]): 包含物品價格列表 (listings)、歷史成交 (history) 的字典列表。

status (int): HTTP 狀態碼。

核心邏輯:

使用 requests.Session 與 HTTPAdapter 處理 502/503 錯誤。

支援將單一 ID 自動轉換為列表處理。

Skill: analyze_sales_velocity

功能描述:
計算物品在過去指定時間內的真實銷售速度，並判斷市場是否不穩定。排除異常數據（如價格為 0 的紀錄）。

輸入參數 (Inputs):

history_data (list[dict]): 來自 Universalis 的歷史成交紀錄。

timeframe_hours (int, default=24): 計算的時間窗口（小時）。

輸出 (Outputs):

sold_count (int): 時間窗口內的成交筆數。

is_unstable (bool): 如果推估的日均銷量與短期銷量差異過大，則標記為不穩定。

實作細節:

market_api.py -> DataAnalyzer.calculate_velocity_in_timeframe

Skill: clean_market_listings

功能描述:
過濾市場上的「垃圾掛單」。排除價格低於特定閾值（例如染料、垃圾單）或無掛單的項目，確保分析數據的有效性。

輸入參數 (Inputs):

raw_data_list (list[dict]): 原始市場數據列表。

min_price_threshold (int, default=300): 最低價格過濾門檻 (Gil)。

輸出 (Outputs):

cleaned_data (list[dict]): 過濾後的有效市場數據。

🛠️ 領域：生產製造 (Manufacturing & Crafting)

來源檔案: crafting_service.py

Skill: calculate_crafting_tree

功能描述:
執行遞迴成本分析 (Recursive Cost Analysis)。計算製作某個物品的成本，並自動判斷每個中間材料應該是「直接購買」還是「自行製作」才最划算。

輸入參數 (Inputs):

target_item_id (int): 目標成品的物品 ID。

server_dc (string): 查詢價格的伺服器區域。

輸出 (Outputs):

crafting_report (dict): 包含總成本、利潤預估、以及詳細的樹狀材料結構。

structure:

{
    "cost": 15000,
    "source": "製作", // 或 "購買"
    "materials": [
        { "name": "木材", "status": "✅ 購買", "price": 500, ... },
        { "name": "金屬", "status": "⚙️ 製作", "sub_materials": [...] }
    ]
}


核心邏輯:

遞迴 (Recursion): 深度優先搜尋 (DFS)，最大深度限制為 10 層。

批次優化: 先解析完整個樹所需的 Item IDs，一次性呼叫 fetch_market_prices，避免 N+1 查詢問題。

決策: 對每個節點執行 min(market_price, crafting_cost) 比較。

📜 領域：配方知識庫 (Recipe Knowledge)

來源檔案: recipe_provider.py

Skill: retrieve_recipe

功能描述:
獲取物品的製作配方。使用本地緩存優先策略，如果緩存不存在，則從 Teamcraft GitHub Raw Data 下載並更新。

輸入參數 (Inputs):

item_id (int): 物品 ID。

輸出 (Outputs):

recipe_data (dict | None): 若無配方則返回 None。

schema:

{
    "recipe_id": 123,
    "result_amount": 1,
    "materials": [{"id": 456, "amount": 2}, ...]
}


依賴: recipes_cache.json (Lazy Loading 機制)。

💾 領域：數據持久化 (Data Persistence)

來源檔案: database.py

Skill: manage_favorites

功能描述:
管理使用者的收藏清單 (Wishlist)。支援新增、刪除、查詢，並使用 SQLite WAL 模式以支援高併發讀取。

操作模式 (Operations):

add: (item_id, item_name, category_id) -> bool

remove: (item_id) -> bool

list: (category_id=None) -> list[tuple]

check: (item_id) -> bool (檢查是否已收藏)

技術規格:

Database: market_app.db

Table: favorites

Concurrency: PRAGMA journal_mode=WAL

Skill: manage_price_alerts

功能描述:
管理使用者的價格警報清單。支援新增警報目標價、查詢啟用中的警報、刪除警報，以及標記警報為已觸發。

操作模式 (Operations):

add: (item_id, item_name, target_price, direction, server) -> bool

list: (enabled_only=True) -> list[dict]

delete: (alert_id) -> void

mark_triggered: (alert_id) -> void

技術規格:

Database: market_app.db

Table: price_alerts

監控邏輯: 獨立背景執行緒每 5 分鐘輪詢一次。

🔍 領域：物品檢索 (Item Retrieval)

來源檔案: database.py 與 update_items_cache.py

Skill: search_local_items

功能描述:
根據中文名稱模糊搜尋物品 ID。使用 SQLite 記憶體快取或實體資料庫進行快速查找，支援同 ID 多重名稱映射（例如藏寶圖新舊名稱「陳舊的地圖G17」與「陳舊的獰豹革地圖」）。

輸入參數 (Inputs):

search_keywords (list[string]): 物品名稱關鍵字列表 (如 ["爆發藥", "智力"])。

輸出 (Outputs):

matches (list[tuple]): (item_id, item_name, category_id) 的列表。

Skill: update_item_cache

功能描述:
從外部 API（Cafemaker）自動抓取最新的物品清單與圖示，並進行簡繁體中文轉換，更新本地的資料庫快取。支援「僅更新藏寶圖別名」、「僅進行簡繁轉換」、「增量更新」等多種操作模式。

執行方式:

外部腳本: `python update_items_cache.py`

依賴: `requests`, `ijson`, 內建 700+ 簡繁對照字典。