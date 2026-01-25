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
  - **智慧均價回退 (Smart Fallback)**: 針對冷門商品，自動採用三階段均價計算 (近期成交 -> 歷史成交 -> 目前掛單)，避免顯示 0 元的困擾。

- **🛠️ 智慧製作計算機 (Crafting Calculator)**
  - 自動拆解配方至基礎素材。
  - 遞迴比較每一個子材料的「購買 vs 製作」成本。
  - 一鍵顯示製作成品的預期利潤率 (ROI)。

- **⭐ 我的最愛掃描器 (My Favorites Scanner)**
  - **個人儀表板**: 專注分析您的「我的最愛」清單，不再被茫茫大海的物品淹沒。
  - **分類管理**: 支援自訂分類功能 (如「料理」、「爆發藥」)，可針對特定分類進行精準掃描。
  - **雙模式掃描**:
    - **循序模式 (預設)**: 逐一查詢，進度清晰，穩定性最高。
    - **批次模式 (快速)**: 一鍵查詢所有資料，適合快速概覽大量物品。
  - **全數據顯示**: 針對關注物品，系統會顯示所有價格區間的商品，不進行低價過濾。

- **🎯 狙擊與套利 (Sniping & Arbitrage)**
  - **狙擊缺口**: 自動偵測價格設定錯誤的低價單，並智慧過濾「蠅頭小利」的無效機會 (可設定利潤門檻)。
  - **跨服套利**: 比較各伺服器最低價，並具備「動態時效警告」功能 (熱門商品資料超過 30 分鐘即警告)，防止看著舊資料白跑一趟。

- **💎 使用體驗優化**
  - **全域 HQ/NQ 過濾**: 勾選 HQ Only 後，所有分析數據 (包含銷量) 皆嚴格排除 NQ 數據，還原真實行情。
  - **自訂詞彙系統**: 支援自訂搜尋簡稱 (如 "爆發藥" -> "剛力之幻藥G8...")。
  - **現代化黑夜模式 UI**: 基於 `customtkinter` 打造的舒適介面。

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
   pip install -r requirements.txt
   ```
3. 執行程式:
   ```bash
   python app.py
   ```

### 方法 C: 自行打包 (Build)
若您想自行產生 `.exe` 執行檔:
1. 確保已安裝 `pyinstaller`。
2. 在 Windows 環境下執行 `build.bat`。
3. 完成後，程式會位於 `dist/FF14MarketApp` (腳本會自動壓縮為 `.7z`)。

## 📖 文件說明
詳細的操作教學請參閱軟體包內的 `使用說明.txt` (繁體中文版)。

## ⚙️ 進階設定
程式內建「參數設定」選單，允許您調整演算法細節:
- **市場稅率**: 依據您的雇員城市設定稅率 (預設 5%)。
- **銷售速度天數**: 設定計算日均銷量的時間窗口。
- **狙擊獲利門檻**: 設定最小利潤金額，過濾無效資訊。

## 🤝 致謝與版權
- **市場數據**: 由 [Universalis](https://universalis.app/) 提供。請大家多多安裝 Universalis 插件貢獻數據！
- **配方資料**: 來自 [FFXIV Teamcraft](https://github.com/ffxiv-teamcraft/ffxiv-teamcraft)。
- **圖示搜尋**: 使用 [Cafemaker](https://cafemaker.wakingsands.com/) API。

## ⚠️ 免責聲明
本工具為第三方應用程式，與 Square Enix 無關。所有數據皆來自社群公開 API，本程式不會直接與遊戲客戶端進行互動。請自行承擔使用風險。

---
*願水晶指引你的交易之路！*
