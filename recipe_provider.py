import requests
import json
import os
import logging
import threading

class RecipeProvider:
    """
    Fetches crafting recipes from Teamcraft Data (GitHub).
    Caches the data locally in 'recipes_cache.json'.
    """
    TC_URL = "https://raw.githubusercontent.com/ffxiv-teamcraft/ffxiv-teamcraft/master/libs/data/src/lib/json/recipes.json"
    CACHE_FILE = "recipes_cache.json"

    def __init__(self):
        self.recipe_index = {}
        self.is_loaded = False
        self.lock = threading.Lock()
        
    def _download_and_load(self):
        """Downloads data if missing, then loads into memory."""
        with self.lock:
            if self.is_loaded:
                return

            if not os.path.exists(self.CACHE_FILE) or os.path.getsize(self.CACHE_FILE) == 0:
                logging.info("Downloading Teamcraft recipes...")
                try:
                    r = requests.get(self.TC_URL, stream=True, timeout=30)
                    if r.status_code == 200:
                        with open(self.CACHE_FILE, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                        logging.info("Download complete.")
                    else:
                        logging.error(f"Failed to download recipes: {r.status_code}")
                        return
                except Exception as e:
                    logging.error(f"Download failed: {e}")
                    return

            # Load
            try:
                logging.info("Loading recipes into memory...")
                with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # Build Index: ItemID (result) -> Recipe
                # Note: Some items have multiple recipes. We'll verify structure.
                # Data is a list of objects.
                count = 0
                for r in data:
                    res_id = r.get('result')
                    if res_id:
                        # Prefer existing recipe? Or overwrite? 
                        # Teamcraft recipes usually unique by ID, but multiple recipes can produce same item.
                        # We'll just take the first one or overwrite. Optimization: maybe pick simpler one?
                        # For now, just store any.
                        if res_id not in self.recipe_index:
                             self.recipe_index[res_id] = r
                             count += 1
                
                self.is_loaded = True
                logging.info(f"Recipes loaded: {count} entries.")
            except Exception as e:
                logging.error(f"Failed to load recipes JSON: {e}")
                # Try validation or delete bad file?
                if os.path.exists(self.CACHE_FILE):
                    os.remove(self.CACHE_FILE)

    def get_recipe(self, item_id):
        """
        Returns a dictionary with recipe details or None if not found.
        Blocks if data is not yet loaded.
        """
        if not self.is_loaded:
            self._download_and_load()
            
        if not self.is_loaded:
            return None # Failed to load
            
        raw = self.recipe_index.get(item_id)
        if not raw:
            return None
            
        # Parse into standard format
        materials = []
        for ing in raw.get("ingredients", []):
            materials.append({
                "id": ing.get("id"),
                "amount": ing.get("amount", 1)
            })
            
        return {
            "recipe_id": raw.get("id"),
            "result_amount": raw.get("yields", 1),
            "materials": materials
        }
