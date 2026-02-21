import logging
import math

class CraftingService:
    def __init__(self, api, recipe_provider, db_manager):
        self.api = api
        self.recipe_provider = recipe_provider
        self.db = db_manager
        self.MAX_RECURSION_DEPTH = 10 # 防止無限遞迴
        self._no_recipe_cache = set()  # [P2] 無配方物品快取

    def get_crafting_data(self, item_id, server_dc):
        """
        計算指定物品的製作成本與預期利潤 (包含遞迴成本分析)。
        此方法負責處理頂層物品，並呼叫遞迴函式來處理子材料。
        """
        # 1. [P2] 快取檢查
        if item_id in self._no_recipe_cache:
            return {"status": "no_recipe"}

        # 2. 取得頂層配方
        top_recipe = self.recipe_provider.get_recipe(item_id)
        if not top_recipe:
            self._no_recipe_cache.add(item_id)
            return {"status": "no_recipe"}

        if not server_dc or server_dc == "尚未設定伺服器":
            server_dc = "Japan"  # 預設備案

        try:
            # 2. 遞迴獲取整個製作樹中所有需要的 item ID
            all_ids_needed = set()
            self._get_full_recipe_tree(item_id, all_ids_needed, set())
            
            # 3. 一次性批次查詢所有物品的市場價格
            market_data, status_code = self.api.fetch_market_data_batch(server_dc, list(all_ids_needed))
            if status_code != 200:
                return {"status": "api_error", "code": status_code, "message": f"API 請求失敗 ({status_code})"}

            # 4. 建立頂層物品的材料列表
            total_craft_cost = 0
            top_level_materials = []
            is_craftable = True

            for mat in top_recipe["materials"]:
                mat_id = mat["id"]
                mat_amount = mat["amount"]

                # 為每個材料遞迴計算其最佳成本
                sub_result = self._calculate_cost_recursive(mat_id, market_data, set())
                
                mat_cost = sub_result["cost"]
                if mat_cost == math.inf:
                    is_craftable = False
                    mat_cost = 0 # 在UI上顯示為0，但標記為缺貨

                total_craft_cost += mat_cost * mat_amount

                mat_name = self.db.get_item_name_by_id(mat_id) or f"Item {mat_id}"
                
                source_display = "⚙️ 製作" if sub_result["source"] == "製作" else "✅ 購買"
                if sub_result["cost"] == math.inf:
                    source_display = "⚠️ 缺貨"

                details = {
                    "name": mat_name,
                    "amount": mat_amount,
                    "price": mat_cost,
                    "subtotal": mat_cost * mat_amount,
                    "status": source_display,
                    "sub_materials": sub_result.get("materials", [])
                }
                top_level_materials.append(details)

            final_cost = total_craft_cost if is_craftable else math.inf
            
            # 5. 取得成品市價以計算利潤
            prod_market_price = self._get_price_from_market_data(item_id, market_data)
            
            final_profit = 0
            if prod_market_price > 0 and final_cost != math.inf:
                final_profit = prod_market_price - final_cost

            return {
                "status": "success",
                "total_cost": final_cost if final_cost != math.inf else 0,
                "product_price": prod_market_price,
                "profit": final_profit,
                "materials": top_level_materials
            }

        except Exception as e:
            logging.error(f"Crafting Service Error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def _get_full_recipe_tree(self, item_id, all_ids_set, visited_set, depth=0):
        """遞迴遍歷製作樹，收集所有需要的 Item ID。"""
        if item_id in visited_set or depth >= self.MAX_RECURSION_DEPTH:
            return
            
        visited_set.add(item_id)
        all_ids_set.add(item_id)

        recipe = self.recipe_provider.get_recipe(item_id)
        if not recipe:
            return

        for mat in recipe["materials"]:
            self._get_full_recipe_tree(mat["id"], all_ids_set, visited_set, depth + 1)

    def _get_price_from_market_data(self, item_id, market_data):
        """從已獲取的市場數據中提取物品的最低價。"""
        item_data = market_data.get(str(item_id))
        if item_data and item_data.get("listings") and item_data["listings"]:
            return item_data["listings"][0]["pricePerUnit"]
        return 0

    def _calculate_cost_recursive(self, item_id, market_data, visited_set, depth=0):
        """遞迴計算一個物品的最佳成本（製作 vs 購買）。"""
        if item_id in visited_set or depth >= self.MAX_RECURSION_DEPTH:
            price = self._get_price_from_market_data(item_id, market_data)
            return {"cost": price if price > 0 else math.inf, "materials": [], "source": "購買"}

        visited_set.add(item_id)

        buy_cost = self._get_price_from_market_data(item_id, market_data)
        if buy_cost == 0:
            buy_cost = math.inf

        recipe = self.recipe_provider.get_recipe(item_id)
        if not recipe:
            return {"cost": buy_cost, "materials": [], "source": "購買"}

        craft_cost = 0
        material_details = []
        is_craftable = True
        
        for mat in recipe["materials"]:
            sub_result = self._calculate_cost_recursive(mat["id"], market_data, visited_set.copy(), depth + 1)
            
            if sub_result["cost"] == math.inf:
                is_craftable = False
                break 

            mat_cost = sub_result["cost"]
            craft_cost += mat_cost * mat["amount"]

            mat_name = self.db.get_item_name_by_id(mat["id"]) or f"Item {mat['id']}"
            
            source_display = "⚙️ 製作" if sub_result["source"] == "製作" else "✅ 購買"
            if sub_result["cost"] == math.inf:
                 source_display = "⚠️ 缺貨"

            details = {
                "name": mat_name,
                "amount": mat["amount"],
                "price": mat_cost,
                "subtotal": mat_cost * mat["amount"],
                "status": source_display,
                "sub_materials": sub_result.get("materials", [])
            }
            material_details.append(details)

        if not is_craftable:
            craft_cost = math.inf

        if craft_cost < buy_cost:
            return {"cost": craft_cost, "materials": material_details, "source": "製作"}
        else:
            return {"cost": buy_cost, "materials": [], "source": "購買"}