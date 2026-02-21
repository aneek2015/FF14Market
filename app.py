import customtkinter as ctk
import threading
import webbrowser
import gc # [Optimization] For manual garbage collection
from datetime import datetime
import logging
import time 
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk, filedialog

# Import new modules
from database import DatabaseManager
from market_api import MarketAPI, DataAnalyzer
from crafting_service import CraftingService

from recipe_provider import RecipeProvider

# 設定外觀模式
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# 定義一個自訂的 Log Handler，將日誌導向到 GUI
class GuiHandler(logging.Handler):
    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance

    def emit(self, record):
        msg = self.format(record)
        # 呼叫主程式的方法來處理訊息 (Thread-Safe)
        try:
            self.app.append_log(msg)
        except RuntimeError:
            # 背景執行緒在 mainloop 啟動前呼叫時可能觸發此錯誤，安全忽略
            pass

# 設定基礎 logging
logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

class FF14MarketApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("FF14 市場板查詢工具 (Refactored)")
        self.geometry("1200x900") 

        # 初始化模組
        self.db = DatabaseManager()
        self.api = MarketAPI()
        self.recipe_provider = RecipeProvider()
        self.crafting_service = CraftingService(self.api, self.recipe_provider, self.db)

        # 儲存所有日誌的列表 (用於 Debug 視窗回溯)
        self.log_history = []
        self.debug_window = None 
        self.debug_textbox = None

        # 將 Log 導向到 GUI
        gui_handler = GuiHandler(self)
        gui_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S'))
        logging.getLogger().addHandler(gui_handler)

        logging.info("應用程式啟動...")

        # 預設設定值
        self.default_config = {
            "velocity_days": 7,
            "avg_price_entries": 20,
            "dts_good_threshold": 2,
            "dts_bad_threshold": 30,
            "avg_price_days_limit": 30,
            "market_tax_rate": 5,
            "sniping_min_profit": 2000
        }
        self.config = self.db.load_settings(self.default_config)
        self.custom_servers = self.db.get_custom_servers()
        
        # [New] Load user vocabulary
        self.vocabulary_map = self.db.get_all_vocabulary()
        self.vocabulary_reverse_map = {v: k for k, v in self.vocabulary_map.items()} 
        logging.info(f"載入 {len(self.vocabulary_map)} 條自訂詞彙")
        
        # 啟動背景執行緒匯入 items_cache_tw.json
        threading.Thread(target=self.db.import_json_cache, daemon=True).start()

        # 資料變數
        self.current_item_id = None
        self.current_item_name = ""
        self.is_loading = False 
        self.progress_val = 0.0 
        
        # 暫存數據 (用於匯出)
        self.current_data = None
        self.current_analysis = None
        
        # [預設] 選取第一個自訂伺服器
        if self.custom_servers:
            self.selected_dc = self.custom_servers[0]
        else:
            self.selected_dc = "尚未設定伺服器"
            
        self.recent_history = []
        
        # [Hot Items] 快取變數
        self.hot_items_cache = []        # 快取的掃描結果
        self.hot_items_cache_time = 0    # 快取時間戳
        self.hot_items_cache_ttl = 300   # 快取有效期（秒）= 5 分鐘
        self.hot_items_cache_params = {} # 快取時的參數 (hours, sample_size)

        # 設定表格樣式
        self.setup_treeview_style()

        # 介面佈局
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 建立側邊欄
        self.create_sidebar()
        
        # 建立主內容區 (包含多個分頁: 市場/製作/歷史)
        self.create_main_content()

    # [New] Helper for translation
    def translate_term(self, term):
        """Applies user-defined vocabulary to a term."""
        return self.vocabulary_map.get(term, term)

    def create_main_content(self):
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_rowconfigure(2, weight=1) 
        self.main_frame.grid_columnconfigure(0, weight=1)

        # 1. 頂部標題區
        self.header_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        self.item_title_label = ctk.CTkLabel(self.header_frame, text="請輸入關鍵字搜尋...", font=ctk.CTkFont(size=28, weight="bold"))
        self.item_title_label.pack(side="left")
        
        self.item_id_label = ctk.CTkLabel(self.header_frame, text="", font=ctk.CTkFont(size=16), text_color="gray")
        self.item_id_label.pack(side="left", padx=(10, 0), pady=(10, 0))

        # 進度條
        self.progress_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, width=300, height=15, corner_radius=10)
        self.progress_bar.set(0)
        self.progress_bar.pack(side="left", padx=10)
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="0%", font=ctk.CTkFont(size=14, weight="bold"), text_color="#4da6ff")
        self.progress_label.pack(side="left")

        # 收藏按鈕
        self.toggle_fav_button = ctk.CTkButton(self.header_frame, text="☆ 加入最愛", command=self.toggle_favorite, width=100, fg_color="transparent", border_width=1)

        # 刷新按鈕 (新功能)
        self.refresh_button = ctk.CTkButton(self.header_frame, text="🔄 刷新", command=lambda: self.start_search(use_current_id=True), width=80)

        # 2. 分頁控制器
        self.tabview = ctk.CTkTabview(self.main_frame)
        self.tabview.grid(row=2, column=0, sticky="nsew")
        
        # Order: Overview, Crafting, History, Scanner
        self.tabview.add("市場概況")
        self.tabview.add("製作計算") 
        self.tabview.add("歷史數據")
        self.tabview.add("🔥 市場熱賣")
        self.tabview.add("⭐ 我的最愛掃描")
        
        # Setup Tabs
        self.setup_tab_overview()
        self.setup_tab_crafting()
        self.setup_tab_history()
        self.setup_tab_hot_items()  # [New] 市場熱賣
        self.setup_tab_scanner()

        # 底部狀態列
        self.status_bar = ctk.CTkLabel(self.main_frame, text="系統就緒 | 資料庫已連接", anchor="w", text_color="gray")
        self.status_bar.grid(row=3, column=0, sticky="ew", pady=(5,0))

    def setup_tab_crafting(self):
        """初始化製作價格樹 (集成於 Tab)"""
        tab = self.tabview.tab("製作計算")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        
        # Container
        self.crafting_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self.crafting_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.crafting_frame.grid_columnconfigure(0, weight=1)
        self.crafting_frame.grid_rowconfigure(0, weight=1)
        
        # Treeview Area
        cols = ("材料名稱", "需求數量", "市場單價 (Min)", "材料總價", "狀態")
        self.craft_tree = ttk.Treeview(self.crafting_frame, columns=cols, show="headings", selectmode="browse")
        
        self.craft_tree.heading("材料名稱", text="材料名稱")
        self.craft_tree.heading("需求數量", text="需求數量")
        self.craft_tree.heading("市場單價 (Min)", text="市場單價 (Min)")
        self.craft_tree.heading("材料總價", text="材料總價")
        self.craft_tree.heading("狀態", text="狀態")
        
        self.craft_tree.column("材料名稱", width=350)
        self.craft_tree.column("需求數量", width=100, anchor="center")
        self.craft_tree.column("市場單價 (Min)", width=150, anchor="e")
        self.craft_tree.column("材料總價", width=150, anchor="e")
        self.craft_tree.column("狀態", width=100, anchor="center")
        
        scroll = ctk.CTkScrollbar(self.crafting_frame, command=self.craft_tree.yview)
        scroll.pack(side="right", fill="y")
        self.craft_tree.configure(yscrollcommand=scroll.set)
        self.craft_tree.pack(fill="both", expand=True)
        
        # Summary Footer
        footer = ctk.CTkFrame(self.crafting_frame, fg_color="#222", height=80)
        footer.pack(fill="x", pady=10, ipady=10)
        
        self.lbl_craft_cost = ctk.CTkLabel(footer, text="製作成本: -", font=ctk.CTkFont(size=20))
        self.lbl_craft_cost.pack(side="left", padx=30)
        
        self.lbl_prod_price = ctk.CTkLabel(footer, text="成品市價: -", font=ctk.CTkFont(size=20))
        self.lbl_prod_price.pack(side="left", padx=30)
        
        self.lbl_craft_diff = ctk.CTkLabel(footer, text="預估利潤: -", font=ctk.CTkFont(size=24, weight="bold"))
        self.lbl_craft_diff.pack(side="right", padx=30)
        
        self.lbl_craft_status = ctk.CTkLabel(self.crafting_frame, text="準備就緒", text_color="gray")
        self.lbl_craft_status.pack(anchor="w", padx=5)



    def _process_crafting_logic(self, item_id, item_name):
        # 更新狀態為載入中
        self.after(0, lambda: self.lbl_craft_status.configure(text=f"正在計算製作成本: {item_name}...", text_color="yellow"))
        
        # 呼叫 Service 進行計算 (在背景執行緒中)
        result = self.crafting_service.get_crafting_data(item_id, self.selected_dc)
        
        # 回到 UI 執行緒處理結果
        self.after(0, lambda: self._handle_crafting_result(result))

    def _handle_crafting_result(self, result):
        logging.debug(f"CRAFTING_RESULT: {result}")
        status = result.get("status")
        
        if status == "no_recipe":
            self.lbl_craft_status.configure(text="該物品沒有配方", text_color="gray")
            for item in self.craft_tree.get_children():
                self.craft_tree.delete(item)
            self.lbl_craft_cost.configure(text="製作成本: -")
            self.lbl_prod_price.configure(text="成品市價: -")
            self.lbl_craft_diff.configure(text="預估利潤: -", text_color="gray")
            return
            
        if status == "error" or status == "api_error":
            msg = result.get("message", "未知錯誤")
            self.lbl_craft_status.configure(text=f"查詢失敗: {msg}", text_color="red")
            messagebox.showerror("計算錯誤", f"發生錯誤: {msg}")
            return
            
        if status == "success":
            # The new service returns a nested structure, so we pass it directly
            self._update_crafting_ui(
                result["materials"], 
                result["total_cost"], 
                result["product_price"], 
                result["profit"]
            )

    def _update_crafting_ui(self, materials, cost, prod, profit):
        # Clear old items first
        for item in self.craft_tree.get_children():
            self.craft_tree.delete(item)
            
        # Start the recursive population of the tree
        self._populate_craft_tree("", materials) # Start with root as parent

        # Update summary labels
        self.lbl_craft_cost.configure(text=f"製作成本: {cost:,}")
        self.lbl_prod_price.configure(text=f"成品市價: {prod:,}")
        
        profit_color = "#66FF66" if profit > 0 else "#FF6666"
        self.lbl_craft_diff.configure(text=f"預估利潤: {profit:+,}", text_color=profit_color)
        
        self.lbl_craft_status.configure(text="計算完成", text_color="green")

    def _populate_craft_tree(self, parent_node, materials):
        """Recursively populates the ttk.Treeview."""
        for mat in materials:
            # Prepare values for display
            # The name might need a prefix to show hierarchy
            prefix = "└─ " if parent_node else ""
            
            display_name = self.translate_term(mat["name"]) # Apply Translation

            values = (
                prefix + display_name,
                mat["amount"],
                f"{mat['price']:,}",
                f"{mat['subtotal']:,}",
                mat["status"]
            )
            
            # Insert the material into the tree under its parent
            node_id = self.craft_tree.insert(parent_node, "end", values=values, open=True)
            
            # If the material has sub-materials, recurse
            if "sub_materials" in mat and mat["sub_materials"]:
                self._populate_craft_tree(node_id, mat["sub_materials"])





    def append_log(self, msg):
        """接收來自 logging 的訊息 (Thread-Safe)"""
        def _update_ui():
            self.log_history.append(msg)
            if self.debug_window and self.debug_textbox and self.debug_window.winfo_exists():
                self.debug_textbox.configure(state="normal")
                self.debug_textbox.insert("end", msg + "\n")
                self.debug_textbox.see("end")
                self.debug_textbox.configure(state="disabled")

        # 將工作排程到主執行緒 (加入 RuntimeError 保護)
        try:
            self.after(0, _update_ui)
        except RuntimeError:
            # mainloop 尚未啟動或已關閉時，僅記錄到歷史
            self.log_history.append(msg)

    def setup_treeview_style(self):
        """配置 Treeview 的深色主題樣式"""
        style = ttk.Style()
        style.theme_use("clam") 

        style.configure("Treeview",
                        background="#2b2b2b",
                        foreground="white",
                        fieldbackground="#2b2b2b",
                        rowheight=35,
                        borderwidth=0,
                        font=("Arial", 14))
        
        style.map("Treeview",
                  background=[('selected', '#106BA3')],
                  foreground=[('selected', 'white')])
        
        style.configure("Treeview.Heading",
                        background="#1E1E1E",
                        foreground="white",
                        relief="flat",
                        font=("Arial", 14, "bold"))
        
        style.map("Treeview.Heading",
                  background=[('active', '#2b2b2b')])

    # ------------------ UI Layout ------------------

    def create_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(14, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Universalis\n+ Saddlebag", font=ctk.CTkFont(size=22, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        # Navigation removed - Integrated into Tabs

        self.dc_label = ctk.CTkLabel(self.sidebar_frame, text="資料來源 (自訂列表):", anchor="w", font=ctk.CTkFont(weight="bold"))
        self.dc_label.grid(row=1, column=0, padx=20, pady=(10, 0))
        
        self.dc_option_menu = ctk.CTkOptionMenu(self.sidebar_frame, 
                                                values=[], 
                                                command=self.change_dc)
        self.dc_option_menu.grid(row=2, column=0, padx=20, pady=(0, 20))
        self.update_dc_menu() 
        
        if self.custom_servers:
            self.dc_option_menu.set(self.custom_servers[0])
        else:
            self.dc_option_menu.set("請先新增伺服器")

        self.search_label = ctk.CTkLabel(self.sidebar_frame, text="網站搜尋 (名稱/ID):", anchor="w", font=ctk.CTkFont(weight="bold"))
        self.search_label.grid(row=3, column=0, padx=20, pady=(10, 0))
        
        self.search_entry = ctk.CTkEntry(self.sidebar_frame, placeholder_text="例如: 剛力 / 44096")
        self.search_entry.grid(row=4, column=0, padx=20, pady=(0, 10))
        self.search_entry.bind("<Return>", lambda event: self.start_search())

        self.hq_only_var = ctk.BooleanVar(value=False)
        self.hq_checkbox = ctk.CTkCheckBox(self.sidebar_frame, text="只顯示 HQ", variable=self.hq_only_var, command=self.refresh_ui_from_cache)
        self.hq_checkbox.grid(row=6, column=0, padx=20, pady=(0, 10))
        
        self.search_button = ctk.CTkButton(self.sidebar_frame, text="執行搜尋", command=self.start_search, fg_color="#106BA3", hover_color="#0D5582")
        self.search_button.grid(row=7, column=0, padx=20, pady=(0, 10))

        self.fav_list_button = ctk.CTkButton(self.sidebar_frame, text="我的最愛 (常用品項)", command=self.open_favorites_window, fg_color="#E0A800", hover_color="#B88A00", text_color="black")
        self.fav_list_button.grid(row=8, column=0, padx=20, pady=(20, 0))

        self.link_label = ctk.CTkLabel(self.sidebar_frame, text="操作:", anchor="w")
        self.link_label.grid(row=9, column=0, padx=20, pady=(20, 0))
        
        self.open_web_button = ctk.CTkButton(self.sidebar_frame, text="開啟原始網頁", command=self.open_in_browser, fg_color="transparent", border_width=1)
        self.open_web_button.grid(row=10, column=0, padx=20, pady=(0, 5))

        self.vocab_button = ctk.CTkButton(self.sidebar_frame, text="詞彙管理", command=self.open_vocabulary_window, fg_color="#3B8ED0", hover_color="#36719F")
        self.vocab_button.grid(row=11, column=0, padx=20, pady=(5, 5))

        self.settings_button = ctk.CTkButton(self.sidebar_frame, text="⚙️ 參數設定", command=self.open_settings_window, fg_color="transparent", border_width=1, text_color="silver")
        self.settings_button.grid(row=13, column=0, padx=20, pady=(10, 0), sticky="s")


        self.help_button = ctk.CTkButton(self.sidebar_frame, text="使用說明 / Help", command=self.show_help_window, fg_color="transparent", border_width=1, text_color="silver")
        self.help_button.grid(row=14, column=0, padx=20, pady=(5, 5), sticky="s")

        self.debug_button = ctk.CTkButton(self.sidebar_frame, text="🔧 Debug", command=self.open_debug_window, fg_color="#444", hover_color="#333", height=24)
        self.debug_button.grid(row=15, column=0, padx=20, pady=(5, 20), sticky="s")



    def show_help_window(self):
        msg = (
            "【系統操作說明】\n\n"
            "1. 伺服器設定：\n"
            "   請使用「Custom」手動輸入英文伺服器名稱 (如 Ifrit)。\n\n"
            "2. HQ 篩選：\n"
            "   勾選「只顯示 HQ」後，分析儀表板會重新計算數據。\n\n"
            "3. 參數設定：\n"
            "   點擊「⚙️ 參數設定」可自訂分析門檻。\n\n"
            "4. 除錯：\n"
            "   - 「Debug」可開啟日誌視窗。"
        )
        messagebox.showinfo("使用說明", msg)

    def open_debug_window(self):
        if self.debug_window is None or not self.debug_window.winfo_exists():
            self.debug_window = ctk.CTkToplevel(self)
            self.debug_window.title("Debug Log")
            self.debug_window.geometry("600x400")
            
            self.debug_textbox = ctk.CTkTextbox(self.debug_window)
            self.debug_textbox.pack(fill="both", expand=True, padx=10, pady=10)
            
            self.debug_textbox.insert("0.0", "\n".join(self.log_history) + "\n")
            self.debug_textbox.see("end")
            self.debug_textbox.configure(state="disabled")
        else:
            self.debug_window.focus()

    def open_vocabulary_window(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("自訂詞彙管理")
        dialog.geometry("600x500")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        main_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        tree_frame = ctk.CTkFrame(main_frame)
        tree_frame.grid(row=0, column=0, sticky="nsew", columnspan=2)
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)
        
        cols = ("原文", "修正後")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        tree.heading("原文", text="原文")
        tree.heading("修正後", text="修正後")
        tree.grid(row=0, column=0, sticky="nsew")
        
        scroll = ctk.CTkScrollbar(tree_frame, command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)

        input_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        input_frame.grid(row=1, column=0, sticky="ew", pady=10, columnspan=2)
        input_frame.grid_columnconfigure(1, weight=1)
        input_frame.grid_columnconfigure(3, weight=1)
        
        ctk.CTkLabel(input_frame, text="原文:").grid(row=0, column=0, padx=5)
        entry_orig = ctk.CTkEntry(input_frame)
        entry_orig.grid(row=0, column=1, sticky="ew", padx=5)
        ctk.CTkLabel(input_frame, text="修正後:").grid(row=0, column=2, padx=5)
        entry_corr = ctk.CTkEntry(input_frame)
        entry_corr.grid(row=0, column=3, sticky="ew", padx=5)

        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.grid(row=2, column=0, sticky="e", columnspan=2)

        def refresh_tree():
            for item in tree.get_children():
                tree.delete(item)
            self.vocabulary_map = self.db.get_all_vocabulary()
            
            # [Fix] Update Reverse Map as well
            # [Fix] Update Reverse Map as well
            self.vocabulary_reverse_map = {v: k for k, v in self.vocabulary_map.items()}
            
            sorted_vocab = sorted(self.vocabulary_map.items())
            for orig, corr in sorted_vocab:
                tree.insert("", "end", values=(orig, corr))
            # [Fix] Do NOT refresh UI here. It causes full reload on window open.
            # if self.current_item_id:
            #     self.refresh_ui_from_cache()

        def on_select(event):
            selected_item = tree.focus()
            if selected_item:
                values = tree.item(selected_item, "values")
                entry_orig.delete(0, "end")
                entry_orig.insert(0, values[0])
                entry_corr.delete(0, "end")
                entry_corr.insert(0, values[1])

        def add_or_update():
            orig = entry_orig.get().strip()
            corr = entry_corr.get().strip()
            if orig and corr:
                if self.db.add_or_update_vocabulary(orig, corr):
                    entry_orig.delete(0, "end")
                    entry_corr.delete(0, "end")
                    refresh_tree()
                else:
                    messagebox.showerror("錯誤", "無法儲存詞彙", parent=dialog)
            else:
                messagebox.showwarning("提示", "原文和修正後內容不能為空", parent=dialog)

        def delete_selected():
            selected_item = tree.focus()
            if not selected_item:
                messagebox.showwarning("提示", "請先在列表中選擇要刪除的詞彙", parent=dialog)
                return
            original_term = tree.item(selected_item, "values")[0]
            if messagebox.askyesno("確認刪除", f"確定要刪除 '{original_term}' 這個規則嗎？", parent=dialog):
                if self.db.delete_vocabulary(original_term):
                    refresh_tree()
                else:
                    messagebox.showerror("錯誤", "刪除失敗", parent=dialog)
        
        tree.bind("<<TreeviewSelect>>", on_select)
        ctk.CTkButton(btn_frame, text="刪除選定", command=delete_selected, fg_color="gray").pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="新增/更新", command=add_or_update).pack(side="left", padx=5)
        refresh_tree()

    def open_favorite_manager(self):
        window = ctk.CTkToplevel(self)
        window.title("我的最愛分類管理")
        window.geometry("800x600")
        window.attributes("-topmost", True)
        
        # Data Loading
        cats = self.db.get_categories() # {id: name}
        # Invert for name lookup
        cat_name_map = {v: k for k, v in cats.items()}
        cat_names = list(cats.values())
        
        # Layout: Left (Categories), Right (Items in selected Cat)
        window.grid_columnconfigure(0, weight=1) 
        window.grid_columnconfigure(1, weight=2)
        window.grid_rowconfigure(1, weight=1)
        
        # Top Bar: Add Category
        top = ctk.CTkFrame(window, height=50)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        
        def add_cat():
            new_name = simpledialog.askstring("新增分類", "名稱:", parent=window)
            if new_name:
                if self.db.add_category(new_name):
                    refresh_cats()
                else:
                    messagebox.showerror("錯誤", "新增失敗", parent=window)
                    
        ctk.CTkButton(top, text="+ 新增分類", width=100, command=add_cat).pack(side="left", padx=10)
        
        # Category List
        full_frame_l = ctk.CTkFrame(window)
        full_frame_l.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        ctk.CTkLabel(full_frame_l, text="選擇分類", font=ctk.CTkFont(weight="bold")).pack()
        
        lb_cats = tk.Listbox(full_frame_l, bg="#2b2b2b", fg="white", selectbackground="#F0A500", selectforeground="black", height=20, exportselection=False)
        lb_cats.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Item List
        full_frame_r = ctk.CTkFrame(window)
        full_frame_r.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)
        self.lbl_current_cat = ctk.CTkLabel(full_frame_r, text="物品清單", font=ctk.CTkFont(weight="bold"))
        self.lbl_current_cat.pack()
        
        cols = ("ID", "名稱")
        tree = ttk.Treeview(full_frame_r, columns=cols, show="headings")
        tree.heading("ID", text="ID")
        tree.heading("名稱", text="名稱")
        tree.column("ID", width=80)
        tree.column("名稱", width=250)
        tree.pack(fill="both", expand=True, padx=5, pady=5)
        
        # State
        current_cat_id = [None]
        
        def refresh_cats():
            lb_cats.delete(0, tk.END)
            updated_cats = self.db.get_categories()
            # Update closure scope maps
            cats.clear() 
            cats.update(updated_cats)
            
            for cid, cname in updated_cats.items():
                lb_cats.insert(tk.END, cname)
                
        def on_cat_select(evt):
            sel = lb_cats.curselection()
            if not sel: return
            cname = lb_cats.get(sel[0])
            # Find ID
            cid = next((k for k, v in cats.items() if v == cname), None)
            if cid:
                current_cat_id[0] = cid
                self.lbl_current_cat.configure(text=f"分類: {cname}")
                load_items(cid)
                
        def load_items(cid):
            for item in tree.get_children():
                tree.delete(item)
            items = self.db.get_favorites(cid) # (id, name, cat_id)
            for iid, iname, _ in items:
                dname = self.translate_term(iname)
                tree.insert("", "end", values=(iid, dname))
                
        def move_item():
            sel_item = tree.selection()
            if not sel_item: return
            
            # Show target selection dialog
            target_name = simpledialog.askstring("移動至...", f"輸入目標分類名稱 ({', '.join(cats.values())})", parent=window)
            
            target_id = next((k for k, v in cats.items() if v == target_name), None)
            
            if target_id:
                for item in sel_item:
                    vals = tree.item(item)['values']
                    iid = vals[0]
                    self.db.update_favorite_category(iid, target_id)
                load_items(current_cat_id[0])
                if hasattr(self, 'update_scanner_cat_menu'):
                     self.update_scanner_cat_menu()
            else:
                 messagebox.showerror("錯誤", "找不到該分類", parent=window)

        def remove_item():
            sel_item = tree.selection()
            if not sel_item: return
            if messagebox.askyesno("確認", "從最愛移除選中物品?", parent=window):
                for item in sel_item:
                    vals = tree.item(item)['values']
                    iid = vals[0]
                    self.db.remove_favorite(iid)
                load_items(current_cat_id[0])
                if hasattr(self, 'update_scanner_cat_menu'):
                     self.update_scanner_cat_menu()

        # Actions
        btn_frame = ctk.CTkFrame(window)
        btn_frame.grid(row=2, column=0, columnspan=2, fill="x", padx=10, pady=10)
        
        ctk.CTkButton(btn_frame, text="移動至另一分類", command=move_item).pack(side="left", padx=20)
        ctk.CTkButton(btn_frame, text="移除物品", command=remove_item, fg_color="#E04F5F").pack(side="right", padx=20)
        
        lb_cats.bind("<<ListboxSelect>>", on_cat_select)
        refresh_cats()

    def open_settings_window(self):
        window = ctk.CTkToplevel(self)
        window.title("參數設定")
        window.geometry("400x520")
        window.attributes("-topmost", True)
        window.grab_set() 

        ctk.CTkLabel(window, text="分析參數設定 (進階)", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 15))

        def create_row(label_text, config_key):
            frame = ctk.CTkFrame(window, fg_color="transparent")
            frame.pack(fill="x", padx=30, pady=5)
            ctk.CTkLabel(frame, text=label_text, anchor="w").pack(side="left")
            entry = ctk.CTkEntry(frame, width=100)
            entry.insert(0, str(self.config[config_key]))
            entry.pack(side="right")
            return entry

        entry_velocity = create_row("銷售速度統計天數 (天):", "velocity_days")
        entry_avg = create_row("近期均價參考筆數 (筆):", "avg_price_entries")
        
        # [Phase 2 Configs]
        entry_avg_days = create_row("均價計算期限 (天):", "avg_price_days_limit")
        entry_tax = create_row("市場稅率 (%):", "market_tax_rate")
        entry_sniping = create_row("狙擊最低獲利 (Gil):", "sniping_min_profit")
        
        entry_good = create_row("去化天數 - 優良 (< 天):", "dts_good_threshold")
        entry_bad = create_row("去化天數 - 滯銷 (> 天):", "dts_bad_threshold")

        def save_and_close():
            try:
                v_days = int(entry_velocity.get())
                avg_ent = int(entry_avg.get())
                d_good = float(entry_good.get())
                d_bad = float(entry_bad.get())
                
                # [Phase 2]
                avg_days = int(entry_avg_days.get())
                tax = float(entry_tax.get())
                sniping_min = int(entry_sniping.get())

                if v_days < 1 or avg_ent < 1:
                    messagebox.showerror("錯誤", "天數與筆數必須大於 0", parent=window)
                    return

                self.db.save_setting("velocity_days", v_days)
                self.db.save_setting("avg_price_entries", avg_ent)
                self.db.save_setting("dts_good_threshold", d_good)
                self.db.save_setting("dts_bad_threshold", d_bad)
                self.db.save_setting("avg_price_days_limit", avg_days)
                self.db.save_setting("market_tax_rate", tax)
                self.db.save_setting("sniping_min_profit", sniping_min)
                
                self.config["velocity_days"] = v_days
                self.config["avg_price_entries"] = avg_ent
                self.config["dts_good_threshold"] = d_good
                self.config["dts_bad_threshold"] = d_bad
                self.config["avg_price_days_limit"] = avg_days
                self.config["market_tax_rate"] = tax
                self.config["sniping_min_profit"] = sniping_min
                
                messagebox.showinfo("成功", "設定已儲存並生效。", parent=window)
                window.destroy()
                
                if self.current_data:
                    self.refresh_ui_from_cache()

                # [New] Update Dashboard Labels
                self.update_overview_labels()

            except ValueError:
                messagebox.showerror("錯誤", "請輸入有效的數字", parent=window)

        btn_frame = ctk.CTkFrame(window, fg_color="transparent")
        btn_frame.pack(pady=30)

        ctk.CTkButton(btn_frame, text="取消", command=window.destroy, fg_color="gray", width=100).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="確認儲存", command=save_and_close, fg_color="#2CC985", hover_color="#25A86E", width=100).pack(side="left", padx=10)



    def setup_tab_overview(self):
        tab = self.tabview.tab("市場概況")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # 分析區塊
        self.analysis_frame = ctk.CTkFrame(tab, height=160, fg_color="#1E1E1E", corner_radius=10, border_width=1, border_color="#3A3A3A")
        self.analysis_frame.grid(row=0, column=0, sticky="ew", pady=(10, 10), padx=5)
        self.analysis_frame.grid_columnconfigure((0,1,2,3), weight=1)
        
        self.lbl_velocity_title, self.stat_velocity = self.create_stat_card(0, 0, "銷售速度", "--")
        self.lbl_avg_price_title, self.stat_avg_price = self.create_stat_card(0, 1, "近期平均成交價", "--")
        _, self.stat_days_to_sell = self.create_stat_card(0, 2, "去化天數 (有效庫存)", "--")
        _, self.stat_stock = self.create_stat_card(0, 3, "庫存 (有效/總量)", "--")
        
        _, self.stat_profit = self.create_stat_card(1, 0, "預期營收 (實拿)", "--")
        _, self.stat_arbitrage = self.create_stat_card(1, 1, "跨服價差 (套利)", "--")
        _, self.stat_sniping = self.create_stat_card(1, 2, "狙擊缺口 (價差)", "--")
        _, self.stat_stack_opt = self.create_stat_card(1, 3, "拆售數據 (熱門堆疊)", "--")
        
        # Initial Label Update
        self.update_overview_labels()

        # 販售列表
        self.listings_container = ctk.CTkFrame(tab, corner_radius=0, fg_color="transparent")
        self.listings_container.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        ctk.CTkLabel(self.listings_container, text="販售列表 (Listings)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        
        cols = ("#", "伺服器", "HQ", "魔晶石", "單價", "數量", "總價", "價差%", "雇員")
        self.listings_tree = ttk.Treeview(self.listings_container, columns=cols, show='headings', selectmode='browse')
        
        self.listings_tree.column("#", width=40, anchor="center")
        self.listings_tree.column("伺服器", width=120, anchor="center")
        self.listings_tree.column("HQ", width=50, anchor="center")
        self.listings_tree.column("魔晶石", width=80, anchor="center")
        self.listings_tree.column("單價", width=100, anchor="center")
        self.listings_tree.column("數量", width=60, anchor="center")
        self.listings_tree.column("總價", width=120, anchor="center")
        self.listings_tree.column("價差%", width=80, anchor="center")
        self.listings_tree.column("雇員", width=200, anchor="center")

        for col in cols:
            self.listings_tree.heading(col, text=col)

        vsb_list = ttk.Scrollbar(self.listings_container, orient="vertical", command=self.listings_tree.yview)
        self.listings_tree.configure(yscrollcommand=vsb_list.set)
        
        self.listings_tree.pack(side="left", fill="both", expand=True)
        vsb_list.pack(side="right", fill="y")

    def setup_tab_history(self):
        tab = self.tabview.tab("歷史數據")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        self.history_container = ctk.CTkFrame(tab, corner_radius=0, fg_color="transparent")
        self.history_container.grid(row=0, column=0, sticky="nsew", padx=5, pady=10)

        # [New] Controls Frame
        ctrl_frame = ctk.CTkFrame(self.history_container, fg_color="transparent")
        ctrl_frame.pack(fill="x", pady=(0, 5))

        ctk.CTkLabel(ctrl_frame, text="近期交易 (History - Top 500)", font=ctk.CTkFont(weight="bold")).pack(side="left")
        
        self.history_sort_var = ctk.StringVar(value="依時間排序")
        self.hist_sort_btn = ctk.CTkSegmentedButton(ctrl_frame, values=["依時間排序", "依堆疊熱門度"],
                                                    variable=self.history_sort_var,
                                                    command=self.refresh_history_ui)
        self.hist_sort_btn.pack(side="right") # Pack right aligned

        h_cols = ("單價", "數量", "交易時間")
        self.history_tree = ttk.Treeview(self.history_container, columns=h_cols, show='headings', selectmode='browse')
        
        self.history_tree.column("單價", width=150, anchor="center")
        self.history_tree.column("數量", width=100, anchor="center")
        self.history_tree.column("交易時間", width=200, anchor="center")

        for col in h_cols:
            self.history_tree.heading(col, text=col)

        vsb_hist = ttk.Scrollbar(self.history_container, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=vsb_hist.set)

        self.history_tree.pack(side="left", fill="both", expand=True)
        vsb_hist.pack(side="right", fill="y")

    def update_dc_menu(self):
        menu_values = []
        if self.custom_servers:
            for s in self.custom_servers:
                menu_values.append(s) 
            menu_values.append("----------------")
        menu_values.append("Custom (手動輸入 + 儲存)")
        self.dc_option_menu.configure(values=menu_values)
        
        current_display = self.dc_option_menu.get()
        if current_display not in menu_values and self.custom_servers:
             self.dc_option_menu.set(self.custom_servers[0])

    def create_stat_card(self, row, col, title, value):
        frame = ctk.CTkFrame(self.analysis_frame, fg_color="transparent")
        frame.grid(row=row, column=col, pady=10, padx=5, sticky="ew")
        lbl_title = ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=12), text_color="gray")
        lbl_title.pack()
        lbl_value = ctk.CTkLabel(frame, text=value, font=ctk.CTkFont(size=18, weight="bold"), text_color="#4da6ff")
        lbl_value.pack()
        return lbl_title, lbl_value

    def update_overview_labels(self):
        """Updates the labels in the Analysis Dashboard based on current config."""
        v_days = self.config.get("velocity_days", 7)
        avg_entries = self.config.get("avg_price_entries", 20)
        avg_days = self.config.get("avg_price_days_limit", 30)
        
        if hasattr(self, 'lbl_velocity_title'):
             self.lbl_velocity_title.configure(text=f"銷售速度 ({v_days}天)")
             
        if hasattr(self, 'lbl_avg_price_title'):
             self.lbl_avg_price_title.configure(text=f"近期平均成交價 ({avg_entries}筆/{avg_days}天)")

    def toggle_favorite(self):
        try:
            if not self.current_item_id:
                return
                
            if self.db.is_favorite(self.current_item_id):
                # Already favorite -> Ask to remove
                # Use translated name in dialog
                display_name = self.translate_term(self.current_item_name)
                if messagebox.askyesno("移除收藏", f"確定要將 {display_name} 從最愛中移除嗎？"):
                    if self.db.remove_favorite(self.current_item_id):
                        self.update_favorite_button_state()
            else:
                # Not favorite -> Open Add Dialog
                self.open_add_favorite_dialog()
        except Exception as e:
            logging.exception("Toggle favorite error")
            messagebox.showerror("錯誤", f"開啟收藏視窗失敗: {e}")

    def open_add_favorite_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("加入最愛")
        dialog.geometry("420x550")
        dialog.attributes("-topmost", True)
        
        # Force focus to capture key events
        dialog.after(100, dialog.focus_force)
        
        display_name = self.translate_term(self.current_item_name)
        ctk.CTkLabel(dialog, text=f"加入收藏: {display_name}", font=ctk.CTkFont(weight="bold")).pack(pady=10)
        
        ctk.CTkLabel(dialog, text="選擇分類 (按 Enter 確認):").pack(pady=5)
        
        cats = self.db.get_categories() # [(id, name), ...]
        cat_names = [c[1] for c in cats]
        cat_map = {c[1]: c[0] for c in cats}
        
        current_cat_var = ctk.StringVar(value=cat_names[0] if cat_names else "未分類")
        option_menu = ctk.CTkOptionMenu(dialog, variable=current_cat_var, values=cat_names)
        option_menu.pack(pady=5)

        # Inline Add Category Frame
        add_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        add_frame.pack(pady=10, fill="x", padx=20)
        
        self.add_cat_entry = ctk.CTkEntry(add_frame, placeholder_text="輸入新分類...", width=150)
        
        def toggle_add_mode():
            if self.add_cat_entry.winfo_ismapped():
                self.add_cat_entry.pack_forget()
                btn_add_confirm.pack_forget()
                btn_toggle_add.configure(text="+ 新增分類")
            else:
                self.add_cat_entry.pack(side="left", padx=5)
                btn_add_confirm.pack(side="left")
                btn_toggle_add.configure(text="取消新增")
                self.add_cat_entry.focus_set() # Focus entry when opening

        def confirm_add_cat():
            new_name = self.add_cat_entry.get().strip()
            if new_name:
                self.db.add_category(new_name)
                # Refresh values
                new_cats = self.db.get_categories()
                new_names = [c[1] for c in new_cats]
                option_menu.configure(values=new_names)
                current_cat_var.set(new_name)
                cat_map.update({c[1]: c[0] for c in new_cats})
                # Reset UI
                self.add_cat_entry.delete(0, 'end')
                toggle_add_mode()

        btn_toggle_add = ctk.CTkButton(dialog, text="+ 新增分類", width=100, command=toggle_add_mode, fg_color="gray")
        btn_toggle_add.pack(pady=5)
        
        
        btn_add_confirm = ctk.CTkButton(add_frame, text="儲存", width=60, command=confirm_add_cat, fg_color="#106BA3")
        
        def confirm(event=None):
            selected_name = current_cat_var.get()
            cat_id = cat_map.get(selected_name, 1)
            if self.db.add_favorite(self.current_item_id, self.current_item_name, cat_id):
                self.update_favorite_button_state()
                dialog.destroy()
        
        
        
        # Main Action Button (Confirm)
        # Pack comfortably below the content
        btn_confirm = ctk.CTkButton(dialog, text="確認加入", command=confirm, fg_color="#E0A800", text_color="black")
        btn_confirm.pack(pady=20)

        # Bind Enter key to confirm (Optional convenience)
        dialog.bind("<Return>", confirm)

    def update_favorite_button_state(self):
        if not self.current_item_id:
            self.toggle_fav_button.pack_forget()
            self.refresh_button.pack_forget() # Hide refresh button too
            return
            
        # Favorite Button
        if not self.toggle_fav_button.winfo_ismapped():
            self.toggle_fav_button.pack(side="left", padx=(20, 0), pady=(10, 0))

        if self.db.is_favorite(self.current_item_id):
            self.toggle_fav_button.configure(text="★ 已收藏", fg_color="#E0A800", text_color="black")
        else:
            self.toggle_fav_button.configure(text="☆ 加入最愛", fg_color="transparent", text_color="white")
            
        # Refresh Button
        if not self.refresh_button.winfo_ismapped():
            self.refresh_button.pack(side="left", padx=(10, 0), pady=(10, 0))

    def open_favorites_window(self):
        window = ctk.CTkToplevel(self)
        window.title("我的最愛 (分類管理)")
        window.geometry("600x500") # Wider for 2 columns
        window.attributes("-topmost", True)

        # Layout: Left (Categories), Right (Items)
        window.grid_columnconfigure(0, weight=1)
        window.grid_columnconfigure(1, weight=3)
        window.grid_rowconfigure(0, weight=1)

        # --- Left Panel: Categories ---
        cat_frame = ctk.CTkFrame(window, corner_radius=0)
        cat_frame.grid(row=0, column=0, sticky="nsew")
        
        ctk.CTkLabel(cat_frame, text="分類列表", font=ctk.CTkFont(weight="bold")).pack(pady=10)
        
        cat_scroll = ctk.CTkScrollableFrame(cat_frame)
        cat_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        
        # --- Right Panel: Items ---
        item_frame = ctk.CTkFrame(window, corner_radius=0, fg_color="transparent")
        item_frame.grid(row=0, column=1, sticky="nsew", padx=10)
        
        item_label = ctk.CTkLabel(item_frame, text="物品列表", font=ctk.CTkFont(weight="bold"))
        item_label.pack(pady=10)
        
        item_scroll = ctk.CTkScrollableFrame(item_frame)
        item_scroll.pack(fill="both", expand=True, pady=5)

        # State
        self.fav_selected_cat_id = None

        def load_items(cat_id, cat_name):
            self.fav_selected_cat_id = cat_id
            item_label.configure(text=f"{cat_name} - 物品列表")
            
            # Clear items
            for widget in item_scroll.winfo_children():
                widget.destroy()

            items = self.db.get_favorites(cat_id)
            if not items:
                ctk.CTkLabel(item_scroll, text="(無物品)").pack(pady=20)
                return

            def on_select(iid, iname):
                self.current_item_id = iid
                self.current_item_name = iname
                self.update_title(iname, iid)
                self.current_item_id = iid
                self.current_item_name = iname
                self.update_title(iname, iid)
                
                if self.is_loading: return
                self.is_loading = True
                threading.Thread(target=self.fetch_market_data, args=(iid,)).start()
                
                # Sync to Crafting
                if hasattr(self, 'lbl_craft_status'):
                     self.lbl_craft_status.configure(text=f"正同步搜尋配方: {iname}...", text_color="cyan")
                threading.Thread(target=self._process_crafting_logic, args=(iid, iname)).start()

                window.destroy()  # Optional: Close window on select

            def on_delete(iid):
                if self.db.remove_favorite(iid):
                    load_items(cat_id, cat_name) # Refresh
                    if self.current_item_id == iid:
                        self.update_favorite_button_state()

            for iid, iname, _ in items:
                row = ctk.CTkFrame(item_scroll, fg_color="transparent")
                row.pack(fill="x", pady=2)
                
                display_name = self.translate_term(iname)

                ctk.CTkButton(row, text=display_name, anchor="w", 
                              command=lambda i=iid, n=iname: on_select(i, n),
                              fg_color="transparent", border_width=1).pack(side="left", fill="x", expand=True)
                
                ctk.CTkButton(row, text="X", width=30, fg_color="#FF6666", hover_color="#CC0000",
                              command=lambda i=iid: on_delete(i)).pack(side="right", padx=5)

        def load_categories():
            # Clear categories
            for widget in cat_scroll.winfo_children():
                widget.destroy()
            
            cats = self.db.get_categories()
            
            # "All" option? Maybe later. Just list actual categories.
            # Add "Uncategorized" explicitly at top if needed, but DB returns it sorted by ID (1 is uncategorized)
            
            for cid, cname in cats:
                btn = ctk.CTkButton(cat_scroll, text=cname, anchor="w", fg_color="transparent", border_width=0,
                                    command=lambda i=cid, n=cname: load_items(i, n))
                btn.pack(fill="x", pady=1)
                
            # Default load first category
            if cats:
                load_items(cats[0][0], cats[0][1])

        load_categories()

        # Manage Categories Button
        def open_manage_cats():
            self.open_category_manager(window, load_categories)
        
        ctk.CTkButton(cat_frame, text="管理分類", fg_color="#444", command=open_manage_cats).pack(pady=10)

    def open_category_manager(self, parent, on_close_callback):
        dialog = ctk.CTkToplevel(parent)
        dialog.title("管理分類")
        dialog.geometry("300x400")
        dialog.attributes("-topmost", True)
        
        # Ensure it stays on top and has focus
        dialog.grab_set() 
        dialog.after(100, dialog.focus_force)

        scroll = ctk.CTkScrollableFrame(dialog)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        def refresh_list():
            for w in scroll.winfo_children(): w.destroy()
            cats = self.db.get_categories()
            for cid, cname in cats:
                row = ctk.CTkFrame(scroll, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=cname).pack(side="left", padx=5)
                
                if cid != 1: # Don't delete Default/Uncategorized
                    ctk.CTkButton(row, text="刪除", width=40, fg_color="#FF6666",
                                  command=lambda i=cid: delete_cat(i)).pack(side="right")

        def delete_cat(cid):
            if messagebox.askyesno("刪除分類", "確定要刪除此分類嗎？\n該分類下的物品將會變為「未分類」。"):
                self.db.delete_category(cid)
                refresh_list()
                on_close_callback()

        def add_cat():
            dialog_input = ctk.CTkInputDialog(text="請輸入新分類名稱:", title="新增分類")
            name = dialog_input.get_input()
            if name:
                self.db.add_category(name)
                refresh_list()
                on_close_callback()

        refresh_list()
        ctk.CTkButton(dialog, text="+ 新增分類", command=add_cat, fg_color="#106BA3").pack(pady=10)

    def change_dc(self, selection):
        if "Custom" in selection:
            dialog = ctk.CTkInputDialog(text="請輸入伺服器名稱 (World Name):\n(例如: Ifrit, Bahamut)", title="手動輸入")
            input_val = dialog.get_input()
            if input_val:
                input_val = input_val.strip()
                self.selected_dc = input_val
                if self.db.add_custom_server(input_val):
                    self.custom_servers = self.db.get_custom_servers()
                    self.update_dc_menu()
            else:
                self.update_dc_menu() 
                return
        elif selection in self.custom_servers:
             self.selected_dc = selection
        else:
            return
        
        logging.info(f"使用者切換資料區域: {self.selected_dc}")
        self.status_bar.configure(text=f"資料區域已切換: {self.selected_dc} (請按「執行搜尋」更新)")

    def show_candidate_selection(self, candidates):
        if not candidates:
            messagebox.showinfo("搜尋結果", "找不到符合的物品。")
            self.status_bar.configure(text="搜尋無結果")
            self.search_button.configure(state="normal")
            return

        window = ctk.CTkToplevel(self)
        window.title("請選擇物品")
        window.geometry("400x600")
        window.attributes("-topmost", True)

        lbl = ctk.CTkLabel(window, text=f"找到 {len(candidates)} 個相關物品，請選擇：", font=ctk.CTkFont(size=16, weight="bold"))
        lbl.pack(pady=10)

        scroll = ctk.CTkScrollableFrame(window, width=350, height=500)
        scroll.pack(pady=10, padx=10, fill="both", expand=True)

        def on_select(item_id, item_name):
            if self.is_loading: return
            window.destroy()
            self.current_item_id = item_id
            self.current_item_name = item_name
            self.after(0, lambda: self.update_title(item_name, item_id))
            
            self.is_loading = True
            threading.Thread(target=self.fetch_market_data, args=(item_id,)).start()
            
            # Sync to Crafting
            if hasattr(self, 'lbl_craft_status'):
                self.lbl_craft_status.configure(text=f"正同步搜尋配方: {item_name}...", text_color="cyan")
            
            # Trigger crafting calc in background
            threading.Thread(target=self._process_crafting_logic, args=(item_id, item_name)).start()

        for item_id, item_name in candidates:
            btn_text = f"{item_name}\n(ID: {item_id})"
            btn = ctk.CTkButton(scroll, text=btn_text, anchor="w", height=50, 
                                command=lambda i=item_id, n=item_name: on_select(i, n),
                                fg_color="transparent", border_width=1, text_color="white")
            btn.pack(pady=2, fill="x")

        self.search_button.configure(state="normal")

    def start_search(self, use_current_id=False):
        if not self.selected_dc or self.selected_dc == "尚未設定伺服器":
            messagebox.showwarning("提示", "請先選擇或新增一個伺服器。")
            return

        if use_current_id and self.current_item_id:
            if self.is_loading: return
            logging.info(f"Refreshing data for item ID: {self.current_item_id}")
            self.status_bar.configure(text=f"正在刷新 {self.current_item_name} 的數據...", text_color="yellow")
            # Trigger both market and crafting data fetches
            self.is_loading = True
            threading.Thread(target=self.fetch_market_data, args=(self.current_item_id,)).start()
            threading.Thread(target=self._process_crafting_logic, args=(self.current_item_id, self.current_item_name)).start()
            return

        raw_input = self.search_entry.get().strip()
        if not raw_input:
            return
            
        if self.is_loading: return

        if self.is_loading: return

        # [New] 自訂詞彙反向搜尋轉換
        if raw_input in self.vocabulary_reverse_map:
            original_term = self.vocabulary_reverse_map[raw_input]
            logging.info(f"偵測到自訂詞彙: '{raw_input}' -> 自動轉換為原始名稱: '{original_term}'")
            self.status_bar.configure(text=f"自訂詞彙轉換: {raw_input} -> {original_term}")
            raw_input = original_term

        # 呼叫新的多執行緒搜尋
        self.search_item_thread(raw_input)

    def search_item_thread(self, query):
        """
        啟動搜尋執行緒 (Entry Point) - 替代原本的 perform_search_process
        """
        if not query:
            return

        self.search_button.configure(state="disabled")
        self.status_bar.configure(text=f"正在搜尋: {query} ...")
        
        # 切換到掃描結果分頁以顯示搜尋結果 (因為我們共用 TreeView)
        self.tabview.set("⭐ 我的最愛掃描") 
        
        # 清空舊的顯示
        self.scan_tree.delete(*self.scan_tree.get_children())
        
        # 啟動背景工作
        threading.Thread(target=self._run_search_task, args=(query,), daemon=True).start()

    def _run_search_task(self, query):
        """
        [背景執行緒] 搜尋 Item + 同步檢查製作狀態
        """
        try:
            # 由於 append_log 已經修復為 Thread-Safe，這裡可以放心使用 logging
            logging.info(f"開始多執行緒搜尋: {query}")
            
            # 嘗試解析是否為 ID
            if query.isdigit():
                 item_id = int(query)
                 name = self.db.get_item_name_by_id(item_id)
                 results = [{'id': item_id, 'name': name}] if name else []
                 if not results:
                     # 嘗試透過 API 搜尋 ID
                      results = [{'id': c[0], 'name': c[1]} for c in self.api.search_item_web(query)]
            else:
                 # 關鍵字搜尋 (先本地後 API)
                 local_res = self.db.search_local_items(query.split(), limit=50) # Split specifically for DB method
                 if local_res:
                     results = [{'id': r[0], 'name': r[1]} for r in local_res]
                 else:
                     # Fallback to API
                     api_res = self.api.search_item_web(query)
                     results = [{'id': c[0], 'name': c[1]} for c in api_res]

            if not results:
                self.after(0, lambda: self._search_finished([], "找不到相關物品。"))
                return

            logging.info(f"搜尋找到 {len(results)} 筆結果, 開始分析製作狀態...")
            
            # 準備顯示資料
            display_data = []
            server = self.selected_dc
            
            for item in results:
                item_id = item.get('id')
                item_name = item.get('name') or f"Unknown ({item_id})"
                
                # [Optimization] Cache name if new
                if not self.db.get_item_name_by_id(item_id):
                    self.db.cache_item(item_id, item_name)

                # 檢查製作狀態
                crafting_info = self.crafting_service.get_crafting_data(item_id, server)
                
                craft_status = "❌ 無法製作"
                if crafting_info.get('status') != 'no_recipe':
                    craft_status = "🔨 可製作"
                
                price_info = "---"

                display_data.append({
                    'id': item_id,
                    'name': item_name,
                    'craft_status': craft_status,
                    'price_info': price_info
                })
            
            # 將 UI 更新排程回主執行緒 (雖然在 _update_search_ui 裡面也是安全的，但這裡作為一個 Task 結束點)
            self.after(0, lambda: self._update_search_ui(display_data))

        except Exception as e:
            logging.error(f"搜尋執行緒錯誤: {e}")
            self.after(0, lambda: self._search_finished([], f"錯誤: {e}"))

    def _update_search_ui(self, display_data):
        """
        [主執行緒] 更新 UI - 動態切換 TreeView 欄位為搜尋模式
        """
        try:
            self.scan_tree.delete(*self.scan_tree.get_children())
            
            # 1. 動態切換顯示欄位 (搜尋模式)
            cols = ("ID", "名稱", "製作狀態", "價格資訊")
            self.scan_tree.configure(columns=cols, show="headings")
            
            self.scan_tree.heading("ID", text="ID")
            self.scan_tree.heading("名稱", text="名稱")
            self.scan_tree.heading("製作狀態", text="製作狀態")
            self.scan_tree.heading("價格資訊", text="價格資訊")
            
            self.scan_tree.column("ID", width=60, anchor="center")
            self.scan_tree.column("名稱", width=250, anchor="w")
            self.scan_tree.column("製作狀態", width=100, anchor="center")
            self.scan_tree.column("價格資訊", width=100, anchor="center")

            # 2. 插入資料
            if not display_data:
                self.status_bar.configure(text="無搜尋結果")
            else:
                self.status_bar.configure(text=f"搜尋完成: 找到 {len(display_data)} 筆資料")

            for data in display_data:
                # 翻譯名稱
                d_name = self.translate_term(data['name'])
                
                values = (
                    data['id'],
                    d_name,
                    data['craft_status'],
                    data['price_info']
                )
                self.scan_tree.insert("", "end", values=values)
            
            # 儲存結果以供點擊使用
            self.last_scan_results = display_data 
            
        except Exception as e:
            logging.error(f"UI Update Error: {e}")
        finally:
            self.search_button.configure(state="normal")

    def _search_finished(self, results, msg):
        self.status_bar.configure(text=msg)
        self.search_button.configure(state="normal")
        if not results:
             self.scan_tree.delete(*self.scan_tree.get_children())

    def start_search(self, use_current_id=False):
        if not self.selected_dc or self.selected_dc == "尚未設定伺服器":
            messagebox.showwarning("提示", "請先選擇或新增一個伺服器。")
            return

        if use_current_id and self.current_item_id:
            if self.is_loading: return
            logging.info(f"Refreshing data for item ID: {self.current_item_id}")
            self.status_bar.configure(text=f"正在刷新 {self.current_item_name} 的數據...", text_color="yellow")
            self.is_loading = True
            threading.Thread(target=self.fetch_market_data, args=(self.current_item_id,)).start()
            threading.Thread(target=self._process_crafting_logic, args=(self.current_item_id, self.current_item_name)).start()
            return

        raw_input = self.search_entry.get().strip()
        if not raw_input:
            return
            
        if self.is_loading: return

        # 直接呼叫新的多執行緒搜尋 (不再使用 perform_search_process)
        self.search_item_thread(raw_input)

    def update_title(self, name, iid):
        self.item_title_label.configure(text=name)
        self.item_id_label.configure(text=f"ID: {iid}")
        self.update_favorite_button_state()

    def fetch_market_data(self, item_id):
        self.after(0, lambda: self.prepare_loading_ui(clear_data=True))
        
        try:
            data, status = self.api.fetch_market_data(self.selected_dc, item_id)
            
            self.is_loading = False 
            if status == 404:
                self.update_ui_error(f"在所選區域找不到數據 (404)。\n請確認伺服器名稱與物品是否存在。")
                return
            if status != 200 or not data:
                self.update_ui_error(f"API 請求錯誤 (Code: {status})")
                return

            logging.info(f"成功獲取數據，開始分析...")
            
            self.current_data = data
            hq_only = self.hq_only_var.get()
            analysis = DataAnalyzer.calculate_metrics(data, self.config, hq_only)
            self.current_analysis = analysis
            
            self.after(0, lambda: self.finish_loading_and_update(data, analysis))
        
        except Exception as e:
            self.is_loading = False
            logging.exception("獲取數據時發生例外狀況")
            self.update_ui_error(f"數據讀取失敗: {str(e)}")

    def refresh_ui_from_cache(self):
        if not self.current_data:
            return
        
        self.prepare_loading_ui(clear_data=False)
        self.status_bar.configure(text="正在重新計算分析數據...", text_color="yellow")
        threading.Thread(target=self._recalculate_process).start()

    def _recalculate_process(self):
        time.sleep(0.3) 
        hq_only = self.hq_only_var.get()
        if self.current_data:
            new_analysis = DataAnalyzer.calculate_metrics(self.current_data, self.config, hq_only)
            self.current_analysis = new_analysis
            self.is_loading = False
            self.after(0, lambda: self.finish_loading_and_update(self.current_data, new_analysis))
        else:
             self.is_loading = False

    def prepare_loading_ui(self, clear_data=True):
        self.search_button.configure(state="disabled")
        self.listings_tree.delete(*self.listings_tree.get_children())
        self.history_tree.delete(*self.history_tree.get_children())
        self.reset_analysis_ui()

        if clear_data:
            # Only clear explicitly when starting a NEW search
            self.current_data = None
            self.current_analysis = None

        self.progress_frame.pack(side="left", padx=(20, 0))
        self.progress_bar.set(0)
        self.progress_label.configure(text="0%")
        self.status_bar.configure(text="正在處理數據...", text_color="yellow")

        self.is_loading = True
        self.progress_val = 0.0
        self.animate_progress()

    def animate_progress(self):
        if not self.is_loading:
            return

        # [Optimization] Stop if window is destroyed or loading finished
        if not self.winfo_exists():
            return

        if self.progress_val < 0.3:
            step = 0.05
        elif self.progress_val < 0.6:
            step = 0.02
        elif self.progress_val < 0.9:
            step = 0.005 
        else:
            step = 0.001 

        self.progress_val += step
        if self.progress_val > 0.95:
            self.progress_val = 0.95

        self.progress_bar.set(self.progress_val)
        self.progress_label.configure(text=f"{int(self.progress_val * 100)}%")
        
        self.after(50, self.animate_progress)

    def finish_loading_and_update(self, data, analysis):
        self.progress_bar.set(1.0)
        self.progress_label.configure(text="100%")
        self.after(200, lambda: self._render_data(data, analysis))

    def _render_data(self, data, analysis):
        self.progress_frame.pack_forget()
        self.search_button.configure(state="normal")
        self.update_market_ui(data, analysis)

    def update_ui_error(self, message):
        self.progress_frame.pack_forget()
        self.status_bar.configure(text=message, text_color="red")
        self.search_button.configure(state="normal")
        messagebox.showerror("錯誤", message)

    def reset_analysis_ui(self):
        self.stat_velocity.configure(text="--", text_color="white")
        self.stat_avg_price.configure(text="--", text_color="white")
        self.stat_profit.configure(text="--", text_color="white")
        self.stat_days_to_sell.configure(text="--", text_color="white")
        self.stat_stock.configure(text="--", text_color="white")
        self.stat_arbitrage.configure(text="--", text_color="white")
        self.stat_sniping.configure(text="--", text_color="white")
        self.stat_stack_opt.configure(text="--", text_color="white")

    def update_market_ui(self, data, analysis):
        # 先清除表格舊資料
        self.listings_tree.delete(*self.listings_tree.get_children())
        self.history_tree.delete(*self.history_tree.get_children())

        if analysis:
            vel_val = analysis['velocity']
            vel_tx = analysis.get('velocity_tx', 0)
            vel_color = "#66FF66" if vel_val > 5 else ("#FFD700" if vel_val > 1 else "gray")
            v_days = self.config["velocity_days"]
            self.stat_velocity.configure(text=f"{vel_val:.1f} 個/日\n({vel_tx:.1f} 筆/日)", text_color=vel_color)
            
            # Avg Price with Fallback Tag
            avg_price_val = int(analysis['avg_sale_price'])
            avg_type = analysis.get('avg_price_type', 'Normal')
            
            avg_text = f"{avg_price_val:,}"
            avg_color = "#FFFFFF" # Default
            
            if avg_type == 'Old':
                avg_text += " (歷史)"
                avg_color = "#FFD700" # Gold warning
            elif avg_type == 'Est':
                avg_text += " (掛單)"
                avg_color = "#FF9900" # Orange warning
            elif avg_type == 'None':
                avg_text = "無數據"
                avg_color = "gray"
                
            self.stat_avg_price.configure(text=avg_text, text_color=avg_color)
            
            dts = analysis['days_to_sell']
            dts_str = f"{dts:.1f} 天" if dts < 999 else "∞ 天"
            
            good_th = self.config["dts_good_threshold"]
            bad_th = self.config["dts_bad_threshold"]
            dts_color = "#66FF66" if dts < good_th else ("#FF6666" if dts > bad_th else "#FFD700")
            self.stat_days_to_sell.configure(text=dts_str, text_color=dts_color)

            # Show Effective Stock (with RAW in tooltip/subtitle if possible, but for now just effective)
            stock_eff = analysis['stock_total']
            stock_raw = analysis.get('total_stock_raw', stock_eff)
            self.stat_stock.configure(text=f"{stock_eff:,} (總{stock_raw})")

            # Profit -> Revenue (Unit)
            revenue_val = analysis['profit'] # This is now Unit Revenue (Min * 0.95)
            flip_val = analysis.get('flip_profit', 0)
            roi_val = analysis['roi']
            
            # Display Revenue per unit
            self.stat_profit.configure(text=f"{int(revenue_val):,}", text_color="#66FF66")
            
            arb_val = analysis.get("arbitrage", 0)
            arb_warn = analysis.get("arbitrage_warning", False)
            arb_color = "#66FF66" if arb_val > 0 else "gray"
            arb_text = f"{int(arb_val):+,}"
            if arb_warn:
                arb_text += " ⚠️"
                arb_color = "#FF9900"
            self.stat_arbitrage.configure(text=arb_text, text_color=arb_color)

            # Sniping with Cost
            snipe_val = analysis.get("sniping_profit", 0)
            snipe_cost = analysis.get("sniping_cost", 0)
            snipe_color = "#66FF66" if snipe_val > 0 else "gray"
            
            if snipe_val > 0:
                snipe_text = f"+{int(snipe_val):,}\n(成本: {int(snipe_cost):,})"
            else:
                snipe_text = "--"
                
            self.stat_sniping.configure(text=snipe_text, text_color=snipe_color)

            stack_data = analysis.get("stack_popularity", [])
            if stack_data:
                # Format: List of (qty, count)
                # Display top 3
                lines = []
                for i, (qty, count) in enumerate(stack_data[:3]):
                    lines.append(f"#{i+1}: 堆疊{qty} ({count}筆)")
                stack_str = "\n".join(lines)
                stack_color = "#66FF66" # Green
            else:
                stack_str = "無數據"
                stack_color = "gray"

            self.stat_stack_opt.configure(text=stack_str, text_color=stack_color, font=ctk.CTkFont(size=14)) # Smaller font for multi-line

        listings = analysis.get("merged_listings", []) if analysis else []
        avg_price = analysis['avg_sale_price'] if analysis else 0

        for listing in listings[:50]:
            world = listing.get("worldName", str(listing.get("worldID", "")))
            if not world and self.selected_dc: 
                # Fallback to selected_dc if world is missing (Single server search)
                world = self.selected_dc

            is_hq = listing.get("hq", False)
            hq_text = "★" if is_hq else ""
            materia = listing.get("materia", [])
            mat_text = f"{len(materia)}顆" if materia else "-"
            price = listing.get("pricePerUnit", 0)
            qty = listing.get("quantity", 0)
            total = listing.get("total", 0)
            retainer = listing.get("retainerName", "Unknown")

            diff_val = 0
            if avg_price > 0:
                diff_val = ((price - avg_price) / avg_price) * 100
            diff_str = f"{diff_val:+.0f}%"

            self.listings_tree.insert("", "end", values=(
                "", world, hq_text, mat_text, f"{price:,}", str(qty), f"{total:,}", diff_str, retainer
            ))
            
        for i, item in enumerate(self.listings_tree.get_children()):
            self.listings_tree.set(item, "#", str(i+1))

        for i, item in enumerate(self.listings_tree.get_children()):
            self.listings_tree.set(item, "#", str(i+1))

        # [Modified] Call refresh_history_ui instead of direct populate
        self.refresh_history_ui()

        self.status_bar.configure(text=f"資料更新成功: {datetime.now().strftime('%H:%M:%S')}", text_color="#2CC985")

    def refresh_history_ui(self, value=None):
        """Refreshes the History tab based on current sort method."""
        # Check if we have analysis data
        if not self.current_analysis:
            return

        # Clear current items
        self.history_tree.delete(*self.history_tree.get_children())
        
        history = self.current_analysis.get("merged_history", [])
        if not history:
            return

        sort_mode = self.history_sort_var.get()
        
        # [Sorting Logic]
        if sort_mode == "依堆疊熱門度":
            from collections import Counter
            # 1. Calculate frequency of each quantity
            stack_counts = Counter(h['quantity'] for h in history)
            # 2. Sort by: Frequency DESC, Quantity DESC, Time DESC
            sorted_history = sorted(history, key=lambda x: (stack_counts[x['quantity']], x['quantity'], x['timestamp']), reverse=True)
        else:
            # Default: Time descending (already sorted usually, but ensure it)
            sorted_history = sorted(history, key=lambda x: x['timestamp'], reverse=True)
            
        # [Display]
        # Limit to top 200 for performance if list is huge, though 500 should be fine
        for entry in sorted_history[:500]:
            price = entry.get("pricePerUnit", 0)
            qty = entry.get("quantity", 0)
            ts = entry.get("timestamp", 0)
            date_str = datetime.fromtimestamp(ts).strftime('%m-%d %H:%M')
            is_hq = entry.get("hq", False)
            hq_mark = "★" if is_hq else ""
            
            self.history_tree.insert("", "end", values=(f"{price:,} {hq_mark}", str(qty), date_str))

    def open_in_browser(self):
        if self.current_item_id:
            webbrowser.open(f"https://universalis.app/market/{self.current_item_id}")
        else:
            webbrowser.open("https://universalis.app/")

# --- 🔥 市場熱賣 (Tab) ---
    def setup_tab_hot_items(self):
        tab = self.tabview.tab("🔥 市場熱賣")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # 1. 控制列
        ctrl_frame = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        ctk.CTkLabel(ctrl_frame, text="分析時段:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(10, 5))

        # 時間範圍下拉選單
        self.hot_time_var = ctk.StringVar(value="過去 24 小時")
        time_options = ["過去 24 小時", "過去 48 小時", "過去 72 小時", "過去 7 天"]
        self.hot_time_menu = ctk.CTkComboBox(ctrl_frame, width=160, variable=self.hot_time_var, values=time_options, state="readonly")
        self.hot_time_menu.pack(side="left", padx=5)

        # 取樣範圍下拉選單
        ctk.CTkLabel(ctrl_frame, text="取樣範圍:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(15, 5))
        self.hot_sample_var = ctk.StringVar(value="200 個 (4批)")
        sample_options = ["100 個 (2批)", "200 個 (4批)", "300 個 (6批)", "400 個 (8批)"]
        self.hot_sample_menu = ctk.CTkComboBox(ctrl_frame, width=150, variable=self.hot_sample_var, values=sample_options, state="readonly")
        self.hot_sample_menu.pack(side="left", padx=5)

        # 掃描按鈕
        self.btn_hot_scan = ctk.CTkButton(
            ctrl_frame, text="🔍 開始掃描", 
            command=self.start_hot_scan_thread,
            fg_color="#E04F5F", hover_color="#C03A48", width=130
        )
        self.btn_hot_scan.pack(side="left", padx=15)

        # 清除快取按鈕
        self.btn_hot_clear = ctk.CTkButton(
            ctrl_frame, text="🗑️ 清除快取",
            command=self.clear_hot_cache,
            fg_color="gray", hover_color="#555", width=100
        )
        self.btn_hot_clear.pack(side="left", padx=5)

        # 快取狀態標籤
        self.lbl_hot_status = ctk.CTkLabel(ctrl_frame, text="尚未掃描", text_color="gray", font=ctk.CTkFont(size=13))
        self.lbl_hot_status.pack(side="right", padx=10)

        # 進度條
        self.hot_progress = ctk.CTkProgressBar(ctrl_frame, height=5)
        self.hot_progress.set(0)

        # 2. 結果表格
        res_frame = ctk.CTkFrame(tab)
        res_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        res_frame.grid_columnconfigure(0, weight=1)
        res_frame.grid_rowconfigure(0, weight=1)

        cols = ("排名", "品名", "銷售速度", "時段銷售", "均價", "最低價", "庫存")
        self.hot_tree = ttk.Treeview(res_frame, columns=cols, show="headings")
        self.hot_tree.heading("排名", text="#")
        self.hot_tree.heading("品名", text="品名")
        self.hot_tree.heading("銷售速度", text="銷售速度")
        self.hot_tree.heading("時段銷售", text="時段銷售")
        self.hot_tree.heading("均價", text="均價")
        self.hot_tree.heading("最低價", text="最低價")
        self.hot_tree.heading("庫存", text="庫存")

        self.hot_tree.column("排名", width=50, anchor="center")
        self.hot_tree.column("品名", width=280)
        self.hot_tree.column("銷售速度", width=120, anchor="center")
        self.hot_tree.column("時段銷售", width=100, anchor="center")
        self.hot_tree.column("均價", width=100, anchor="e")
        self.hot_tree.column("最低價", width=100, anchor="e")
        self.hot_tree.column("庫存", width=70, anchor="center")

        self.hot_tree.grid(row=0, column=0, sticky="nsew")

        scroll = ctk.CTkScrollbar(res_frame, command=self.hot_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.hot_tree.configure(yscrollcommand=scroll.set)

        # 雙擊跳轉
        self.hot_tree.bind("<Double-1>", self.on_hot_result_click)

        # 底部提示
        tip_label = ctk.CTkLabel(tab, text="💡 提示：資料來源為 Universalis 最近活躍物品，結合銷售速度排序。雙擊可查看詳情。", 
                                 text_color="gray", font=ctk.CTkFont(size=12))
        tip_label.grid(row=2, column=0, sticky="w", padx=10, pady=(0, 5))

    def _get_hot_hours(self):
        """從下拉選單解析分析時段（小時數）"""
        time_str = self.hot_time_var.get()
        mapping = {
            "過去 24 小時": 24,
            "過去 48 小時": 48,
            "過去 72 小時": 72,
            "過去 7 天": 168
        }
        return mapping.get(time_str, 24)

    def _get_hot_sample_size(self):
        """從下拉選單解析取樣數量"""
        sample_str = self.hot_sample_var.get()
        mapping = {
            "100 個 (2批)": 100,
            "200 個 (4批)": 200,
            "300 個 (6批)": 300,
            "400 個 (8批)": 400
        }
        return mapping.get(sample_str, 200)

    def clear_hot_cache(self):
        """清除熱賣掃描快取"""
        self.hot_items_cache = []
        self.hot_items_cache_time = 0
        self.hot_tree.delete(*self.hot_tree.get_children())
        self.lbl_hot_status.configure(text="快取已清除", text_color="#FFD700")
        self.after(2000, lambda: self.lbl_hot_status.configure(text="尚未掃描", text_color="gray"))

    def start_hot_scan_thread(self):
        """啟動市場熱賣掃描（執行緒安全）"""
        server = self.dc_option_menu.get()
        if not server or server == "請先新增伺服器":
            messagebox.showwarning("提示", "請先選擇伺服器")
            return

        hours = self._get_hot_hours()
        sample_size = self._get_hot_sample_size()
        current_params = {"hours": hours, "sample_size": sample_size}

        # 檢查快取（參數一致且未過期才使用）
        now = time.time()
        if (self.hot_items_cache 
            and (now - self.hot_items_cache_time) < self.hot_items_cache_ttl
            and self.hot_items_cache_params == current_params):
            remaining = int(self.hot_items_cache_ttl - (now - self.hot_items_cache_time))
            self.append_log(f"[市場熱賣] 使用快取資料 (剩餘 {remaining} 秒有效)")
            self.finish_hot_scan(self.hot_items_cache, None, from_cache=True)
            return

        # 禁用按鈕
        self.btn_hot_scan.configure(state="disabled", text="掃描中...")
        self.hot_progress.pack(side="bottom", fill="x", pady=5)
        self.hot_progress.set(0)
        self.lbl_hot_status.configure(text="正在掃描...", text_color="yellow")

        threading.Thread(target=self.run_hot_scan, args=(server, hours), daemon=True).start()

    def run_hot_scan(self, server, hours):
        """[背景執行緒] 執行市場熱賣掃描"""
        def progress_cb(val):
            self.after(0, lambda v=val: self.hot_progress.set(v))

        sample_size = self._get_hot_sample_size()
        results, error = self.api.fetch_hot_items(
            server=server,
            sample_size=sample_size,
            analysis_hours=hours,
            progress_callback=progress_cb
        )

        if not error:
            # 替換 Item ID 為中文名稱
            for r in results:
                name = self.db.get_item_name_by_id(r["id"])
                if name:
                    r["name"] = self.translate_term(name)
                else:
                    r["name"] = f"[ID: {r['id']}]"

        self.after(0, lambda: self.finish_hot_scan(results, error))

    def finish_hot_scan(self, results, error, from_cache=False):
        """[主執行緒] 更新市場熱賣結果 UI"""
        # 恢復按鈕狀態
        self.btn_hot_scan.configure(state="normal", text="🔍 開始掃描")
        self.hot_progress.pack_forget()

        if error:
            messagebox.showerror("掃描錯誤", error)
            self.lbl_hot_status.configure(text=f"掃描失敗", text_color="red")
            return

        # 更新快取
        if not from_cache:
            self.hot_items_cache = results
            self.hot_items_cache_time = time.time()
            self.hot_items_cache_params = {
                "hours": self._get_hot_hours(),
                "sample_size": self._get_hot_sample_size()
            }

        # 清空表格
        self.hot_tree.delete(*self.hot_tree.get_children())

        # 取 Top 20
        top_results = results[:20]
        hours = self._get_hot_hours()

        # 更新表頭
        if hours >= 24:
            unit_label = "個/日"
        else:
            unit_label = f"個/{hours}h"
        self.hot_tree.heading("銷售速度", text=f"銷售速度 ({unit_label})")
        self.hot_tree.heading("時段銷售", text=f"時段銷售 ({hours}h)")

        for i, r in enumerate(top_results):
            heat_str = f"{r['heat']:.1f}" if hours >= 24 else f"{int(r['heat'])}"
            self.hot_tree.insert("", "end", values=(
                f"#{i+1}",
                r["name"],
                heat_str,
                f"{r['sold']}",
                f"{int(r['avg']):,}",
                f"{int(r['min']):,}",
                f"{r['stock']:,}"
            ))

        # 儲存原始結果供雙擊使用
        self.last_hot_results = top_results

        # 更新狀態
        cache_time_str = datetime.now().strftime('%H:%M:%S')
        if from_cache:
            self.lbl_hot_status.configure(text=f"快取資料 | {cache_time_str}", text_color="#4da6ff")
        else:
            self.lbl_hot_status.configure(text=f"掃描完成 | {cache_time_str} | 共分析 {len(results)} 個物品", text_color="#2CC985")

        self.append_log(f"[市場熱賣] 顯示 Top {len(top_results)} 熱賣物品 (共 {len(results)} 個有效物品)")

    def on_hot_result_click(self, event):
        """雙擊熱賣結果 → 跳轉至市場概況並查詢"""
        item = self.hot_tree.selection()
        if not item:
            return

        idx = self.hot_tree.index(item)
        if hasattr(self, 'last_hot_results') and idx < len(self.last_hot_results):
            data = self.last_hot_results[idx]
            item_id = data['id']
            item_name = data['name']

            # 更新當前上下文
            self.current_item_id = item_id
            self.current_item_name = item_name

            display_name = self.translate_term(item_name)
            self.update_title(display_name, item_id)

            # 跳轉至市場概況分頁
            self.tabview.set("市場概況")

            # 更新搜尋欄
            self.search_entry.delete(0, "end")
            self.search_entry.insert(0, str(item_id))

            # 開始載入資料
            if self.is_loading:
                return
            self.is_loading = True

            self.status_bar.configure(text=f"正在載入 {display_name} ...", text_color="yellow")

            threading.Thread(target=self.fetch_market_data, args=(item_id,)).start()

            if hasattr(self, 'lbl_craft_status'):
                self.lbl_craft_status.configure(text=f"正同步搜尋配方: {display_name}...", text_color="cyan")

            threading.Thread(target=self._process_crafting_logic, args=(item_id, item_name)).start()

# --- Hot Item Scanner (Tab) ---
    def setup_tab_scanner(self):
        tab = self.tabview.tab("⭐ 我的最愛掃描")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # 1. Controls
        ctrl_frame = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        # Source Label
        ctk.CTkLabel(ctrl_frame, text="掃描範圍:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(10, 5))

        # Category Dropdown
        self.scan_cat_var = ctk.StringVar(value="全部 (All)")
        self.scan_cat_menu = ctk.CTkComboBox(ctrl_frame, width=150, variable=self.scan_cat_var)
        self.scan_cat_menu.pack(side="left", padx=5)
        
        # Initialize Menu
        self.update_scanner_cat_menu()
        
        # Refresh Categories Button
        self.btn_refresh_cat = ctk.CTkButton(ctrl_frame, text="🔄", width=30, command=self.refresh_scanner_source, fg_color="gray")
        self.btn_refresh_cat.pack(side="left", padx=(0, 20))
        
        # Time Slider
        slider_frame = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        slider_frame.pack(side="left", padx=20)
        
        self.scan_hours_var = ctk.IntVar(value=24)
        self.lbl_scan_hours = ctk.CTkLabel(slider_frame, text="過去 24 小時")
        self.lbl_scan_hours.pack()
        
        def update_slider_label(val):
            v = int(float(val))
            self.scan_hours_var.set(v)
            if v < 24:
                self.lbl_scan_hours.configure(text=f"過去 {v} 小時")
            else:
                d = v // 24
                self.lbl_scan_hours.configure(text=f"過去 {d} 天")

        slider = ctk.CTkSlider(slider_frame, from_=1, to=168, number_of_steps=167, command=update_slider_label)
        slider.set(24)
        slider.pack()
        
        # Batch Checkbox
        # Batch Checkbox
        self.batch_scan_var = ctk.BooleanVar(value=True) 
        self.batch_scan_var.set(True) # Default On
        self.chk_batch = ctk.CTkCheckBox(ctrl_frame, text="⚡ 批次快速掃描", variable=self.batch_scan_var)
        self.chk_batch.pack(side="left", padx=10)
        
        # Scan Button
        self.btn_scan = ctk.CTkButton(ctrl_frame, text="開始掃描", command=self.start_scan_thread, fg_color="#E04F5F", hover_color="#C03A48")
        self.btn_scan.pack(side="right", padx=10)
        
        # Progress
        self.scan_progress = ctk.CTkProgressBar(ctrl_frame, height=5)
        self.scan_progress.set(0)
        
        # 2. Results Table
        res_frame = ctk.CTkFrame(tab)
        res_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        res_frame.grid_columnconfigure(0, weight=1)
        res_frame.grid_rowconfigure(0, weight=1)
        
        cols = ("名稱", "熱度", "均價", "庫存", "最低價")
        self.scan_tree = ttk.Treeview(res_frame, columns=cols, show="headings")
        self.scan_tree.heading("名稱", text="名稱")
        self.scan_tree.heading("熱度", text="熱度指標")
        self.scan_tree.heading("均價", text="均價")
        self.scan_tree.heading("庫存", text="庫存")
        self.scan_tree.heading("最低價", text="最低價")
        
        self.scan_tree.column("名稱", width=250)
        self.scan_tree.column("熱度", width=100)
        self.scan_tree.column("均價", width=80)
        self.scan_tree.column("庫存", width=60)
        self.scan_tree.column("最低價", width=80)
        
        self.scan_tree.grid(row=0, column=0, sticky="nsew")
        
        scroll = ctk.CTkScrollbar(res_frame, command=self.scan_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.scan_tree.configure(yscrollcommand=scroll.set)
        
        # Double click to jump
        self.scan_tree.bind("<Double-1>", self.on_scan_result_click)

    def refresh_scanner_source(self):
        """Manually refresh the category dropdown in scanner tab."""
        self.update_scanner_cat_menu()
        self.status_bar.configure(text="掃描來源清單已刷新", text_color="#2CC985") # Green
        
        # Flash button color
        original_color = "gray" # Default set in setup
        self.btn_refresh_cat.configure(fg_color="#2CC985") # Success green
        self.after(500, lambda: self.btn_refresh_cat.configure(fg_color=original_color))

    def update_scanner_cat_menu(self):
        cats = self.db.get_categories()
        logging.info(f"DEBUG: cats type={type(cats)}, value={cats}")
        if isinstance(cats, list):
             # Fallback if list (should act as dict)
             options = ["全部 (All)"] + [c[1] for c in cats] # Assuming list of tuples?
        else:
             options = ["全部 (All)"] + list(cats.values())
             
        self.scan_cat_menu.configure(values=options)
        self.scan_cat_menu.set("全部 (All)")

    def start_scan_thread(self):
        server = self.dc_option_menu.get()
        if not server or server == "請先新增伺服器":
            messagebox.showwarning("提示", "請先選擇伺服器")
            return
            
        self.btn_scan.configure(state="disabled")
        self.scan_progress.pack(side="bottom", fill="x", pady=5)
        self.scan_progress.set(0)
        
        hours = self.scan_hours_var.get()
        cat_name = self.scan_cat_var.get()
        is_batch = self.batch_scan_var.get()
        
        # Resolve Cat ID
        cat_id = None
        if cat_name != "全部 (All)":
            cats = self.db.get_categories()
            # Handle List vs Dict return from DB
            if isinstance(cats, list):
                # list of tuples [(id, name), ...]
                cat_id = next((c[0] for c in cats if c[1] == cat_name), None)
            else:
                # dict {id: name}
                cat_id = next((k for k, v in cats.items() if v == cat_name), None)

        threading.Thread(target=self.run_scanner, args=(server, hours, cat_id, is_batch), daemon=True).start()

    def run_scanner(self, server, hours, category_id=None, is_batch=False):
        try:
            # 1. Gather IDs (Filter by Category)
            target_ids = set()
            
            favs = self.db.get_favorites(category_id)
            for fav in favs:
                target_ids.add(fav[0]) # ID

            if not target_ids:
                self.after(0, lambda: self.finish_scan([], "該分類清單為空"))
                return

            id_list = list(target_ids)
            total = len(id_list)
            
            mode_str = "批次模式" if is_batch else "循序模式"
            self.append_log(f"開始掃描 {total} 個最愛物品 ({mode_str})...")
            
            results = []
            
            if is_batch:
                # --- BATCH MODE ---
                self.after(0, lambda: self.scan_progress.set(0.1))
                data_map, status = self.api.fetch_market_data_batch(server, id_list)
                
                if status == 200:
                    raw_list = list(data_map.values())
                    self.append_log(f"API 回傳資料筆數: {len(raw_list)}")
                    cleaned_list = DataAnalyzer.clean_market_data(raw_list, min_price_threshold=0)
                    self.append_log(f"有效資料筆數: {len(cleaned_list)}")
                    
                    for item_data in cleaned_list:
                        item_id = item_data.get("itemID")
                        name = self.db.get_item_name_by_id(item_id) or str(item_id)
                        name = self.translate_term(name)
                        
                        history = item_data.get("recentHistory", [])
                        sold, _ = DataAnalyzer.calculate_velocity_in_timeframe(history, hours)
                        
                        heat_val = sold if hours < 24 else sold / (hours/24.0)

                        min_price = item_data.get("minPrice", 0)
                        listings = item_data.get("listings", [])
                        current_stock = len(listings)
                        avg_price = int(sum(l["pricePerUnit"] for l in listings) / current_stock) if current_stock else 0

                        results.append({
                            "name": name,
                            "heat": heat_val,
                            "avg": avg_price,
                            "stock": current_stock,
                            "min": min_price,
                            "id": item_id
                        })
                else:
                    self.append_log(f"批次掃描發生錯誤: HTTP {status}")
                
                self.after(0, lambda: self.scan_progress.set(1.0))
            
            else:
                # --- SEQUENTIAL MODE ---
                for i, item_id in enumerate(id_list):
                    # Update Progress
                    progress = (i + 1) / total
                    self.after(0, lambda p=progress: self.scan_progress.set(p))
                    
                    current_name = self.db.get_item_name_by_id(item_id) or str(item_id)
                    current_name = self.translate_term(current_name)
                    
                    try:
                        raw_data, status = self.api.fetch_market_data(server, item_id)
                        
                        if status != 200 or not raw_data:
                            logging.warning(f"Item {item_id} fetch failed or empty. Status: {status}")
                            continue

                        cleaned_list = DataAnalyzer.clean_market_data([raw_data], min_price_threshold=0)
                        if not cleaned_list: continue
                             
                        item_data = cleaned_list[0]
                        history = item_data.get("recentHistory", [])
                        sold, _ = DataAnalyzer.calculate_velocity_in_timeframe(history, hours)
                        
                        heat_val = sold if hours < 24 else sold / (hours/24.0)

                        min_price = item_data.get("minPrice", 0)
                        listings = item_data.get("listings", [])
                        current_stock = len(listings)
                        avg_price = int(sum(l["pricePerUnit"] for l in listings) / current_stock) if current_stock else 0

                        results.append({
                            "name": current_name,
                            "heat": heat_val,
                            "avg": avg_price,
                            "stock": current_stock,
                            "min": min_price,
                            "id": item_id
                        })
                        time.sleep(0.1)
                        
                    except Exception as inner_e:
                        logging.error(f"Error scanning item {item_id}: {inner_e}")
                        continue

            # Sort by Heat
            results.sort(key=lambda x: x["heat"], reverse=True)
            
            self.append_log(f"掃描完成! 共 {len(results)} 筆")
            self.after(0, lambda: self.finish_scan(results, None))

        except Exception as e:
            logging.exception("Scanner failed")
            self.after(0, lambda: self.finish_scan([], f"掃描失敗: {str(e)}"))



    def finish_scan(self, results, error):
        self.btn_scan.configure(state="normal")
        self.scan_progress.pack_forget()
        
        if error:
            messagebox.showerror("掃描錯誤", error)
            return
            
        # Bind to tree
        self.scan_tree.delete(*self.scan_tree.get_children())
        
        # 動態還原顯示欄位 (掃描模式)
        cols = ("名稱", "熱度", "均價", "庫存", "最低價")
        self.scan_tree.configure(columns=cols, show="headings")
        self.scan_tree.heading("名稱", text="名稱")
        self.scan_tree.heading("熱度", text="熱度指標")
        self.scan_tree.heading("均價", text="均價")
        self.scan_tree.heading("庫存", text="庫存")
        self.scan_tree.heading("最低價", text="最低價")
        
        self.scan_tree.column("名稱", width=250)
        self.scan_tree.column("熱度", width=100)
        self.scan_tree.column("均價", width=80)
        self.scan_tree.column("庫存", width=60)
        self.scan_tree.column("最低價", width=80)
        
        hours = self.scan_hours_var.get()
        unit_label = "個/日" if hours >= 24 else f"個({hours}h)"
        self.scan_tree.heading("熱度", text=f"熱度 ({unit_label})")
        
        for r in results:
            val_str = f"{r['heat']:.1f}" if hours >= 24 else f"{int(r['heat'])}"
            self.scan_tree.insert("", "end", values=(
                r['name'],
                val_str,
                f"{int(r['avg']):,}",
                f"{r['stock']:,}",
                f"{int(r['min']):,}",
                r['id']
            ))
            
        # Store raw results for click mapping
        self.last_scan_results = results
        self.append_log(f"掃描完成，找到 {len(results)} 個項目。")

    def on_scan_result_click(self, event):
        item = self.scan_tree.selection()
        if not item: return
        
        # Get index
        idx = self.scan_tree.index(item)
        if hasattr(self, 'last_scan_results') and idx < len(self.last_scan_results):
            data = self.last_scan_results[idx]
            item_id = data['id']
            item_name = data['name']
            
            # Update Current Context
            self.current_item_id = item_id
            self.current_item_name = item_name

            # Translate for Display
            display_name = self.translate_term(item_name)
            self.update_title(display_name, item_id)
            
            # Jump to Overview Tab
            self.tabview.set("市場概況") 
            
            # Update Sidebar Entry (Visual only, no trigger)
            self.search_entry.delete(0, "end")
            self.search_entry.insert(0, str(item_id))

            # Fetch Data Directly
            if self.is_loading: return
            self.is_loading = True
            
            self.status_bar.configure(text=f"正在載入 {display_name} ...", text_color="yellow")
            
            threading.Thread(target=self.fetch_market_data, args=(item_id,)).start()
            
            if hasattr(self, 'lbl_craft_status'):
                self.lbl_craft_status.configure(text=f"正同步搜尋配方: {display_name}...", text_color="cyan")
            
            threading.Thread(target=self._process_crafting_logic, args=(item_id, item_name)).start()

if __name__ == "__main__":
    app = FF14MarketApp()
    app.mainloop()