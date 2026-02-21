# FF14 市場板查詢工具 (FF14 Market App)

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)

專為 **Final Fantasy XIV (FF14)** 玩家打造的強大市場分析工具。整合了 Universalis API 與 Teamcraft 資料，幫助您精準分析市場趨勢、計算製作利潤，並快速發掘跨服價差與撿漏機會。

資料來源：[Universalis](https://universalis.app/) 與 [Teamcraft](https://ffxivteamcraft.com/)。

## ✨ 核心功能

- **📊 進階市場指標 (Advanced Metrics)**
  - **真實銷售速度 (Velocity)**: 過濾 RMT 與異常交易，計算真實的日均銷量與交易筆數。
  - **有效庫存去化 (True Days-to-Sell)**: 排除天價展示單 (Zombie Listings)，計算「有效價格區間」內的庫存去化壓力。
  - **拆售數據 (Stack Data)**: 分析歷史交易，統計最熱門的前三名堆疊數量 (如 99個、20個)，幫助您決定最佳上架數量。

- **🛠️ 智慧製作計算機 (Crafting Calculator)**
  - 自動拆解配方至基礎素材。
  - 遞迴比較每一個子材料的「購買 vs 製作」成本。
  - 一鍵顯示製作成品的預期利潤率 (ROI)。

- **🔥 市場熱賣 (Market Hot Sellers)**
  - 自動分析當前市場最熱門的 **Top 10** 熱賣品項。
  - **智慧策略**: 透過 Universalis 「最近活躍物品」指標，結合銷售速度分析，僅需 ~5 次 API 呼叫即可完成全市場掃描。
  - 支援 4 種時段選擇（24h / 48h / 72h / 7天）。
  - 內建 5 分鐘快取機制，避免重複 API 請求。
  - 雙擊結果即可跳轉至「市場概況」查看詳細數據。

- **⭐ 我的最愛掃描 (Favorites Scanner)**
  - 針對「我的最愛」清單進行批次掃描。
  - **批次快速掃描**: 預設開啟，一次查詢多個物品，大幅縮短掃描時間。
  - 自定義掃描區間 (1小時 ~ 7天)，找出短線爆發或長線穩定的熱門商品。
  - **智慧單位**: 自動切換「區間銷量」與「日流速」，避免數據誤導。

- **🎯 狙擊與套利 (Sniping & Arbitrage)**
  - **狙擊缺口**: 自動偵測價格設定錯誤的低價單，並智慧過濾「蠅頭小利」的無效機會 (可設定利潤門檻)。
  - **跨服套利**: 比較各伺服器最低價，並具備「動態時效警告」功能 (熱門商品資料超過 30 分鐘即警告)，防止看著舊資料白跑一趟。

- **💡 使用體驗優化**
  - **全域 HQ/NQ 過濾**: 勾選 HQ Only 後，所有分析數據 (包含銷量) 皆嚴格排除 NQ 數據，還原真實行情。
  - **自訂詞彙系統**: 支援自訂搜尋簡稱 (如 "爆發藥" -> "剛力之幻藥G8...").
  - **歷史數據排序**: 可切換「依時間排序」或「依堆疊熱門度排序」。
  - **現代化黑夜模式 UI**: 基於 `customtkinter` 打造的舒適介面。

- **📈 價格走勢圖 (Price Chart)** `[NEW]`
  - 歷史數據分頁內嵌 matplotlib 價格走勢圖。
  - HQ(粉紅)/NQ(青色) 分色散點圖 + 移動平均線，異常值自動過濾。

- **🔔 價格警報系統 (Price Alerts)** `[NEW]`
  - 設定目標價格，當市場價低於/高於目標時自動彈出通知。
  - 背景每 5 分鐘自動監控，不需手動檢查。

- **🔄 自動刷新 + 主題切換** `[NEW]`
  - 勾選「自動刷新」後，當前物品每 5 分鐘自動重新查詢。
  - 支援深色/淺色主題一鍵切換。

- **⚡ 效能優化** `[NEW]`
  - API 記憶體快取 (TTL 3分鐘)，減少重複查詢。
  - 搜尋結果先顯示，製作狀態非同步填充，大幅提升搜尋速度。

- **🗺️ 藏寶圖名稱適配 (Treasure Map Alias)**
  - 支援遊戲改版後的新舊名稱同時搜尋，例如「陳舊的地圖G17」與「陳舊的獰豹革地圖」均可找到同一物品。
  - 內建 G1~G17 完整對映表，DB 支援同 ID 多名稱。

- **🔄 物品快取自動更新工具 (Cache Updater)**
  - 提供 `update_items_cache.py` 工具腳本，可從 Cafemaker API 批量抓取最新物品名稱。
  - 內建簡體→繁體中文自動轉換（700+ 字對照表）。
  - 支援增量更新、完整重建、藏寶圖別名、預覽等多種模式。

## 🚀 安裝與使用

### 方法 A: 直接下載執行檔 (Windows)
1. 從 Release 下載最新的壓縮檔 (`.zip` 或 `.7z`)。
2. 解壓縮資料夾。
3. 執行 `FF14MarketApp.exe` 即可使用。

### 方法 B: 原始碼執行 (Source)
環境需求: Python 3.10+

1. 下載專案:
   ```bash
   git clone https://github.com/yourusername/FF14MarketApp.git
   cd FF14MarketApp
   ```
2. 安裝依賴庫:
   ```bash
   pip install customtkinter requests ijson matplotlib
   ```
3. 執行程式:
   ```bash
   python app.py
   ```

### 方法 C: 自行打包 (Build)
若您想自行產生 `.exe` 執行檔:
1. 確保已安裝 `pyinstaller`。
2. 在 Windows 環境下執行 `build.bat`。
3. 腳本會自動打包程式並將關鍵設定檔 (json/db) 複製到 `dist/FF14MarketApp`。

## 📖 文件說明
詳細的操作教學請參閱軟體包內的 `使用說明.txt` (繁體中文版)。

## ⚙️ 進階設定
程式內建「參數設定」選單，允許您調整演算法細節:
- **市場稅率**: 依據您的雇員城市設定稅率 (預設 5%)。
- **銷售速度天數**: 設定計算日均銷量的時間窗口。
- **狙擊獲利門檻**: 設定最小利潤金額，過濾無效資訊。

## 🔄 物品快取更新工具
如果遊戲更新後有新物品或改名，可使用 `update_items_cache.py` 工具更新本地快取:

```bash
# 增量更新（只抓取新物品）
python update_items_cache.py

# 只更新藏寶圖別名
python update_items_cache.py --maps-only

# 只做簡繁轉換（不抓 API）
python update_items_cache.py --convert-only

# 預覽模式（不寫入檔案）
python update_items_cache.py --dry-run
```

## 🤝 致謝與版權
- **市場數據**: 由 [Universalis](https://universalis.app/) 提供。請大家多多安裝 Universalis 插件貢獻數據！
- **配方資料**: 來自 [FFXIV Teamcraft](https://github.com/ffxiv-teamcraft/ffxiv-teamcraft)。
- **圖示搜尋**: 使用 [Cafemaker](https://cafemaker.wakingsands.com/) API。

## ⚠️ 免責聲明
本工具為第三方應用程式，與 Square Enix 無關。所有數據皆來自社群公開 API，本程式不會直接與遊戲客戶端進行互動。請自行承擔使用風險。

---
*願水晶指引你的交易之路！*
