import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
from datetime import datetime
import time

class MarketAPI:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://universalis.app/",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        
        # Initialize Session with Retry strategy
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # [P1] 記憶體快取
        self._market_cache = {}   # key: "server:item_id" -> (data, timestamp)
        self._search_cache = {}   # key: query -> (results, timestamp)
        self._cache_ttl = 180     # 快取有效期：3 分鐘

    def search_item_web(self, query):
        """Searches for an item using Cafemaker API (with cache)."""
        # [P1] 檢查快取
        cache_key = query.lower()
        cached = self._search_cache.get(cache_key)
        if cached and (time.time() - cached[1]) < self._cache_ttl:
            logging.debug(f"Search cache hit: {query}")
            return cached[0]

        try:
            if query.isdigit():
                item_id = int(query)
                url = f"https://cafemaker.wakingsands.com/Item/{item_id}"
                resp = self.session.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    name = data.get("Name")
                    if name:
                        result = [(item_id, name)]
                        self._search_cache[cache_key] = (result, time.time())
                        return result
            else:
                search_url = f"https://cafemaker.wakingsands.com/search?indexes=Item&string={query}"
                resp = self.session.get(search_url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("Results", [])
                    candidates = []
                    for res in results:
                        candidates.append((res.get("ID"), res.get("Name", "Unknown")))
                    self._search_cache[cache_key] = (candidates, time.time())
                    return candidates
        except Exception as e:
            logging.error(f"Web search failed: {e}")
        return []

    def fetch_market_data(self, server, item_id):
        """Fetches market data from Universalis (Single Item, with cache)."""
        # [P1] 檢查快取
        cache_key = f"{server}:{item_id}"
        cached = self._market_cache.get(cache_key)
        if cached and (time.time() - cached[1]) < self._cache_ttl:
            logging.debug(f"Market cache hit: {cache_key}")
            return cached[0], 200

        url = f"https://universalis.app/api/v2/{server}/{item_id}?entries=500"
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 404:
                return None, 404
            if resp.status_code != 200:
                logging.error(f"Universalis API Error: {resp.status_code}")
                return None, resp.status_code
            data = resp.json()
            self._market_cache[cache_key] = (data, time.time())
            return data, 200
        except Exception as e:
            logging.error(f"Fetch market data failed: {e}")
            raise e

    
    def fetch_recently_updated_items(self, server, entries=50):
        """
        Fetches 'most-recently-updated' item IDs from Universalis.
        Server can be World or DC.
        Returns: list of integer item IDs
        """
        url = f"https://universalis.app/api/v2/extra/stats/most-recently-updated?world={server}&entries={entries}"
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                raw_items = data.get("items", [])
                
                # API 回傳格式可能是：
                # 1. 純 ID 列表: [12345, 67890, ...]
                # 2. 物件列表: [{"itemID": 12345, "lastUploadTime": ...}, ...]
                if raw_items and isinstance(raw_items[0], dict):
                    item_ids = [item.get("itemID") for item in raw_items if item.get("itemID")]
                    logging.info(f"從物件列表中解析出 {len(item_ids)} 個物品 ID")
                else:
                    item_ids = raw_items
                
                return item_ids
            else:
                logging.error(f"Recently updated fetch failed: {resp.status_code}")
                return []
        except Exception as e:
            logging.error(f"Fetch recently updated items failed: {e}")
            return []

    def fetch_market_data_batch(self, server, item_ids):
        """
        Fetches market data for multiple items by batching requests to avoid URL length limits.
        Returns a dictionary mapping ItemID to its market data.
        """
        if not item_ids:
            return {}, 200

        all_items_data = {}
        batch_size = 50  # Universalis can handle up to 100 IDs per request
        item_ids_str = [str(i) for i in item_ids]

        for i in range(0, len(item_ids_str), batch_size):
            batch_ids = item_ids_str[i:i + batch_size]
            ids_str = ",".join(batch_ids)
            url = f"https://universalis.app/api/v2/{server}/{ids_str}?entries=500"
            
            logging.info(f"Fetching batch {i//batch_size + 1}, IDs: {len(batch_ids)}")

            try:
                resp = self.session.get(url, timeout=20)
                if resp.status_code != 200:
                    logging.error(f"Universalis Batch Error: {resp.status_code} for IDs {ids_str}")
                    # Skip this batch on error, or handle as needed
                    continue
                
                data = resp.json()
                
                # Case 1: Multiple items -> data["items"] is a dict
                if "items" in data:
                    all_items_data.update(data["items"])
                # Case 2: Single item in response (for a batch of one)
                elif "itemID" in data:
                    all_items_data[str(data["itemID"])] = data
                # Should not be here if asking for multiple, but safe to handle

                time.sleep(0.3) # Gentle rate limit

            except Exception as e:
                logging.error(f"Batch fetch for IDs {ids_str} failed: {e}")
                continue # Move to the next batch

        return all_items_data, 200

    def fetch_hot_items(self, server, sample_size=200, analysis_hours=24, progress_callback=None):
        """
        市場熱賣掃描策略：
        1. 取得最近被更新的物品 ID（活躍交易指標）
        2. 批量查詢市場資料
        3. 過濾垃圾物品 + 計算銷售速度
        4. 回傳排序後的結果清單

        Args:
            server: 伺服器名稱
            sample_size: 取樣數量（最近更新物品數）
            analysis_hours: 分析時間範圍（小時）
            progress_callback: 進度回呼 fn(float 0~1)

        Returns:
            (results_list, error_msg) - results 按銷售速度降序排列
        """
        try:
            # Step 1: 取得最近被更新的物品 ID
            if progress_callback:
                progress_callback(0.1)
            logging.info(f"[市場熱賣] 正在取得最近 {sample_size} 個活躍物品 ID...")
            
            item_ids = self.fetch_recently_updated_items(server, entries=sample_size)
            
            if not item_ids:
                return [], "無法取得最近更新的物品清單，請確認伺服器名稱是否正確"
            
            logging.info(f"[市場熱賣] 取得 {len(item_ids)} 個物品 ID，開始批量查詢市場資料...")
            if progress_callback:
                progress_callback(0.2)
            
            # Step 2: 批量查詢市場資料
            data_map, status = self.fetch_market_data_batch(server, item_ids)
            
            if status != 200 or not data_map:
                return [], f"批量查詢失敗 (HTTP {status})"
            
            logging.info(f"[市場熱賣] 收到 {len(data_map)} 筆市場資料，開始分析...")
            if progress_callback:
                progress_callback(0.7)
            
            # Step 3: 過濾 + 計算銷售速度
            results = []
            raw_list = list(data_map.values())
            cleaned_list = DataAnalyzer.clean_market_data(raw_list, min_price_threshold=300)
            
            for item_data in cleaned_list:
                item_id = item_data.get("itemID")
                history = item_data.get("recentHistory", [])
                
                # 計算指定時間內的銷售數量
                sold_count, _ = DataAnalyzer.calculate_velocity_in_timeframe(history, analysis_hours)
                
                # 計算日均銷售速度
                if analysis_hours >= 24:
                    heat_val = sold_count / (analysis_hours / 24.0)
                else:
                    heat_val = sold_count  # 小時級別直接顯示數量
                
                # 跳過完全沒銷售的物品
                if sold_count == 0:
                    continue
                
                # 取得價格資訊
                min_price = item_data.get("minPrice", 0)
                listings = item_data.get("listings", [])
                current_stock = len(listings)
                avg_price = int(sum(l["pricePerUnit"] for l in listings) / current_stock) if current_stock else 0
                
                # 計算交易筆數（用於排名參考）
                now_ts = datetime.now().timestamp()
                cutoff = now_ts - (analysis_hours * 3600)
                tx_count = len([h for h in history if h.get("timestamp", 0) > cutoff])
                
                results.append({
                    "id": item_id,
                    "name": str(item_id),  # 稍後由 UI 層替換為中文名
                    "heat": heat_val,       # 銷售速度（個/日 or 個/Nh）
                    "sold": sold_count,     # 時段內總銷售數
                    "tx_count": tx_count,   # 交易筆數
                    "avg": avg_price,       # 當前掛單均價
                    "min": min_price,       # 最低價
                    "stock": current_stock  # 庫存數
                })
            
            # Step 4: 排序（銷售速度降序，同速度按交易筆數降序）
            results.sort(key=lambda x: (x["heat"], x["tx_count"]), reverse=True)
            
            if progress_callback:
                progress_callback(1.0)
            
            logging.info(f"[市場熱賣] 分析完成，有效熱賣物品: {len(results)} 個")
            return results, None
            
        except Exception as e:
            logging.exception("[市場熱賣] 掃描失敗")
            return [], f"掃描發生錯誤: {str(e)}"


class DataAnalyzer:
    @staticmethod
    def calculate_metrics(data, config, hq_only=False):
        # 1. Configuration & Initial Setup
        velocity_days = max(1, config.get("velocity_days", 7))
        avg_entries = config.get("avg_price_entries", 20)
        
        # [Phase 2 Configs]
        avg_price_days_limit = config.get("avg_price_days_limit", 30)
        tax_rate = config.get("market_tax_rate", 5) / 100.0
        sniping_threshold = config.get("sniping_min_profit", 2000)

        listings = []
        history = []
        
        # Flatten data
        if "items" in data and isinstance(data["items"], dict):
            for _, item_data in data["items"].items():
                listings.extend(item_data.get("listings", []))
                history.extend(item_data.get("recentHistory", []))
        else:
            listings = data.get("listings", [])
            history = data.get("recentHistory", [])

        # --- 1. STRICT HQ/NQ FILTERING (GLOBAL) ---
        if hq_only:
            listings = [l for l in listings if l.get("hq")]
            history = [h for h in history if h.get("hq")]

        listings.sort(key=lambda x: x.get("pricePerUnit", 0))
        history.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

        if not history and not listings:
            return DataAnalyzer._empty_metrics()
        
        # Define current time once
        now_ts = datetime.now().timestamp()

        # --- 2. VELOCITY & OUTLIER REMOVAL ---
        valid_history = [h for h in history if h.get("pricePerUnit", 0) > 0]
        
        if valid_history:
            prices = sorted([h['pricePerUnit'] for h in valid_history])
            median_price = prices[len(prices)//2]
            valid_history = [
                h for h in valid_history 
                if 0.1 * median_price <= h['pricePerUnit'] <= 10 * median_price
            ]
        
        check_days_ago = now_ts - (velocity_days * 24 * 3600)
        recent_sales = [h for h in valid_history if h['timestamp'] > check_days_ago]
        
        total_quantity_sold = sum(h['quantity'] for h in recent_sales)
        total_tx_sold = len(recent_sales)
        
        velocity_items = total_quantity_sold / float(velocity_days)
        velocity_tx = total_tx_sold / float(velocity_days)

        # --- 3. AVERAGE PRICE (3-STAGE FALLBACK) ---
        # Stage 1: Recent Valid History (within N days)
        avg_price_cutoff = now_ts - (avg_price_days_limit * 24 * 3600)
        recent_avg_candidates = [h for h in valid_history if h['timestamp'] > avg_price_cutoff][:avg_entries]
        
        avg_sale_price = 0
        avg_price_type = "Normal" # Normal, Old, Est, None

        if recent_avg_candidates:
            avg_sale_price = sum(h['pricePerUnit'] for h in recent_avg_candidates) / len(recent_avg_candidates)
            avg_price_type = "Normal"
        else:
            # Stage 2: Old History (ignoring time limit, max 5 entries)
            old_candidates = valid_history[:5]
            if old_candidates:
                avg_sale_price = sum(h['pricePerUnit'] for h in old_candidates) / len(old_candidates)
                avg_price_type = "Old"
            else:
                # Stage 3: Current Listings (max 5 cheapest)
                if listings:
                    listing_candidates = listings[:5]
                    avg_sale_price = sum(l['pricePerUnit'] for l in listing_candidates) / len(listing_candidates)
                    avg_price_type = "Est"
                else:
                    avg_price_type = "None"

        # --- 4. ZOMBIE LISTING FILTER (Effective Stock) ---
        min_price = listings[0]['pricePerUnit'] if listings else 0
        effective_limit = min_price * 1.5
        effective_listings = [l for l in listings if l.get("pricePerUnit", 0) <= effective_limit]
        effective_stock = sum(l.get("quantity", 0) for l in effective_listings)
        
        days_to_sell = 999.0
        if velocity_items > 0:
            days_to_sell = effective_stock / velocity_items
        
        # --- 5. REVENUE & PROFIT ---
        expected_revenue_per_unit = min_price * (1 - tax_rate)
        
        # Flip Profit: (Avg * (1-Tax)) - Min
        flip_profit = (avg_sale_price * (1 - tax_rate)) - min_price

        roi = 0
        if min_price > 0:
            roi = (flip_profit / min_price) * 100

        # --- 6. ARBITRAGE (Dynamic Warning) ---
        arbitrage_spread = 0
        arbitrage_warning = False
        
        if velocity_items > 20:
            warning_threshold = 1800
        elif velocity_items < 1:
            warning_threshold = 21600
        else:
            warning_threshold = 7200
        
        if listings:
            world_min_prices = {}
            for l in listings:
                w_name = l.get("worldName", str(l.get("worldID")))
                price = l.get("pricePerUnit")
                if w_name not in world_min_prices or price < world_min_prices[w_name]['price']:
                    world_min_prices[w_name] = {
                        'price': price,
                        'time': l.get('lastReviewTime', 0)
                    }
            
            if len(world_min_prices) > 1:
                global_min_entry = min(world_min_prices.values(), key=lambda x: x['price'])
                global_min = global_min_entry['price']
                global_max_of_mins = max(v['price'] for v in world_min_prices.values())
                
                arbitrage_spread = (global_max_of_mins * (1 - tax_rate)) - global_min
                
                last_upload = global_min_entry['time']
                if last_upload > 2000000000: last_upload /= 1000
                
                if (now_ts - last_upload) > warning_threshold:
                    arbitrage_warning = True

        # --- 7. SNIPING VALIDATION (Total Profit & ROI) ---
        sniping_profit = 0
        sniping_cost = 0
        
        if len(listings) >= 2:
            first_l = listings[0]
            second_l = listings[1]
            first_price = first_l['pricePerUnit']
            second_price = second_l['pricePerUnit']
            
            # Additional Sniping Context
            qty_stack = first_l['quantity']
            total_cost = first_price * qty_stack
            
            # Sanity Check (2nd price vs Avg) - Skip validation if Avg is None or unreliable?
            # Let's keep strict validation against "Absurd" prices.
            is_valid_gap = True
            if avg_sale_price > 0 and second_price > (avg_sale_price * 3.0):
                is_valid_gap = False
            
            if is_valid_gap:
                unit_profit = (second_price * (1 - tax_rate)) - first_price
                total_snipe_profit = unit_profit * qty_stack
                
                snipe_roi = (unit_profit / first_price) * 100 if first_price > 0 else 0
                
                # Logic: Total Profit > Threshold OR (ROI > 200% AND Cost < 5000)
                is_worth = False
                if total_snipe_profit >= sniping_threshold:
                    is_worth = True
                elif snipe_roi > 200 and total_cost < 5000:
                    is_worth = True # "Penny stock" sniping
                
                if is_worth:
                    sniping_profit = total_snipe_profit
                    sniping_cost = total_cost
        
        # --- 8. Stack Sales Data (Popularity) ---
        # Replacing old optimization with top 3 popular stack sizes
        from collections import Counter
        stack_counts = Counter(h['quantity'] for h in valid_history)
        top_stacks = stack_counts.most_common(3) # [(qty, count), ...]
        
        return {
            "velocity": velocity_items,
            "velocity_tx": velocity_tx,
            "avg_sale_price": avg_sale_price,
            "avg_price_type": avg_price_type, # [Phase 3] New Tag
            "min_price": min_price,
            "profit": expected_revenue_per_unit,
            "flip_profit": flip_profit,
            "roi": roi,
            "arbitrage": arbitrage_spread,
            "arbitrage_warning": arbitrage_warning,
            "sniping_profit": sniping_profit, # Now Total Profit
            "sniping_cost": sniping_cost,     # [Phase 3] New Field
            "days_to_sell": days_to_sell,
            "stock_total": effective_stock,
            "total_stock_raw": sum(l.get("quantity", 0) for l in listings),
            "stack_popularity": top_stacks, # New field
            "merged_listings": listings,
            "merged_history": history
        }

    @staticmethod
    def _empty_metrics():
        return {
            "velocity": 0, "velocity_tx": 0, "avg_sale_price": 0, "avg_price_type": "None",
            "min_price": 0, "profit": 0, "flip_profit": 0, "roi": 0, "arbitrage": 0, 
            "arbitrage_warning": False, "sniping_profit": 0, "sniping_cost": 0,
            "days_to_sell": 999, "stock_total": 0, "total_stock_raw": 0, 
            "stack_diff": 0, "stack_popularity": [],
            "merged_listings": [], "merged_history": []
        }

    @staticmethod
    def clean_market_data(data_list, min_price_threshold=300):
        """
        Filters out 'garbage' items from a list of market data objects.
        Criteria:
        1. Min Price < Threshold (e.g. 300 gil) -> likely trash/dye/junk
        2. No Listings -> dead item
        """
        cleaned = []
        for item_data in data_list:
            listings = item_data.get("listings", [])
            if not listings:
                continue
            
            # Check Min Price
            min_price = listings[0].get("pricePerUnit", 0)
            if min_price < min_price_threshold:
                continue
                
            cleaned.append(item_data)
        return cleaned

    @staticmethod
    def clean_market_data(data_list, min_price_threshold=300):
        """
        Filters out 'garbage' items from a list of market data objects.
        Criteria:
        1. Min Price < Threshold (e.g. 300 gil) -> likely trash/dye/junk
        2. No Listings -> dead item
        """
        cleaned = []
        for item_data in data_list:
            listings = item_data.get("listings", [])
            if not listings:
                continue
            
            # Check Min Price
            min_price = listings[0].get("pricePerUnit", 0)
            if min_price < min_price_threshold:
                continue
                
            cleaned.append(item_data)
        return cleaned

    @staticmethod
    def calculate_velocity_in_timeframe(history, hours=24):
        """
        Calculates sales count within the last N hours.
        Return: (sold_count, is_unstable)
        is_unstable: True if the extrapolated daily velocity is highly volatile compared to actual short-term data.
        """
        if not history:
            return 0, False
            
        now_ts = datetime.now().timestamp()
        cutoff = now_ts - (hours * 3600)
        
        valid_history = [h for h in history if h.get("pricePerUnit", 0) > 0]
        recent_sales = [h for h in valid_history if h['timestamp'] > cutoff]
        
        sold_count = sum(h['quantity'] for h in recent_sales)
        
        return sold_count, False
