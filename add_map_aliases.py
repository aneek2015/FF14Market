"""
藏寶圖別名新增腳本
在 items_cache_tw.json 中為所有藏寶圖新增 G 編號別名
"""
import json
import os

JSON_FILE = "items_cache_tw.json"

# 完整的藏寶圖對映表 (舊名 → 新名, Item ID)
# G 編號參照日文版 Name_ja 及使用者提供的對映
TREASURE_MAP_ALIASES = {
    # 舊名: (新別名, Item ID)
    "陳舊的鞣革地圖":         ("陳舊的地圖G1",  6688),
    "陳舊的山羊革地圖":       ("陳舊的地圖G2",  6689),
    "陳舊的巨蟾蜍革地圖":     ("陳舊的地圖G3",  6690),
    "陳舊的野豬革地圖":       ("陳舊的地圖G4",  6691),
    "陳舊的毒蜥蜴革地圖":     ("陳舊的地圖G5",  6692),
    "陳舊的古鳥革地圖":       ("陳舊的地圖G6",  12241),
    "陳舊的飛龍革地圖":       ("陳舊的地圖G7",  12242),
    "陳舊的巨龍革地圖":       ("陳舊的地圖G8",  12243),
    "陳舊的迦迦納怪鳥革地圖": ("陳舊的地圖G9",  17835),
    "陳舊的瞪羚革地圖":       ("陳舊的地圖G10", 17836),
    "陳舊的綠飄龍革地圖":     ("陳舊的地圖G11", 26744),
    "陳舊的纏尾蛟革地圖":     ("陳舊的地圖G12", 26745),
    "陳舊的賽加羚羊革地圖":   ("陳舊的地圖G13", 36611),
    "陳舊的金毗羅鱷革地圖":   ("陳舊的地圖G14", 36612),
    "陳舊的蛇牛革地圖":       ("陳舊的地圖G15", 39591),
    "陳舊的銀狼革地圖":       ("陳舊的地圖G16", 43556),
    "陳舊的獰豹革地圖":       ("陳舊的地圖G17", 43557),
}

def main():
    # 讀取 JSON
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    by_name = data["by_name"]
    
    added = 0
    skipped = 0
    verified = 0
    
    for old_name, (new_alias, expected_id) in TREASURE_MAP_ALIASES.items():
        # 驗證舊名存在且 ID 正確
        if old_name in by_name:
            actual_id = by_name[old_name]
            if actual_id != expected_id:
                print(f"[警告] {old_name} 的 ID 不符: 預期 {expected_id}, 實際 {actual_id}")
            else:
                verified += 1
        else:
            print(f"[警告] 舊名 {old_name} 不存在於快取中")
        
        # 新增別名
        if new_alias in by_name:
            existing_id = by_name[new_alias]
            if existing_id == expected_id:
                print(f"[跳過] {new_alias} (ID:{expected_id}) 已存在")
                skipped += 1
            else:
                print(f"[衝突] {new_alias} 已存在但指向不同 ID: {existing_id} vs {expected_id}")
        else:
            by_name[new_alias] = expected_id
            print(f"[新增] {new_alias} → ID:{expected_id} (原名: {old_name})")
            added += 1
    
    # 寫回 JSON
    if added > 0:
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=8)
        print(f"\n✅ 完成！新增 {added} 個別名，跳過 {skipped} 個，驗證 {verified} 個舊名正確")
    else:
        print(f"\n⚠️ 沒有需要新增的別名（跳過 {skipped} 個已存在的條目）")

if __name__ == "__main__":
    main()
