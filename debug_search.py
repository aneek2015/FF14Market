import sqlite3
import os
from database import DatabaseManager

def test_search_logic():
    print("Initializing DB...")
    db = DatabaseManager()
    
    # 1. Setup Mock Data
    print("Setting up mock items...")
    db.cache_item(1001, "陳舊的地圖 G1")
    db.cache_item(1002, "陳舊的地圖 G2")
    db.cache_item(1003, "西蘭花")
    db.cache_item(1004, "高貴的西蘭花")
    
    # 2. Test Multi-Keyword Search (Local)
    print("\n--- Test 1: Multi-Keyword Search ---")
    results = db.search_local_items(["陳舊的", "地圖"], limit=10)
    print(f"Search ['陳舊的', '地圖']: Found {len(results)} items")
    for r in results:
        print(f" - {r[1]} (ID: {r[0]})")
    
    if len(results) >= 2:
        print(">> PASS: Found multiple map items.")
    else:
        print(">> FAIL: Did not find expected items.")

    # 3. Test Vocabulary Logic Simulation
    print("\n--- Test 2: Vocabulary Logic ---")
    # Simulate App logic
    vocab_map = {"花椰菜": "西蘭花"}
    
    # Case A: "花椰菜"
    input_a = "花椰菜"
    tokens_a = input_a.split()
    trans_tokens_a = [vocab_map.get(t, t) for t in tokens_a]
    print(f"Input: '{input_a}' -> Tokens: {tokens_a} -> Translated: {trans_tokens_a}")
    
    results_a = db.search_local_items(trans_tokens_a)
    print(f"Search Results for {trans_tokens_a}:")
    for r in results_a:
        print(f" - {r[1]}")
    
    if any("西蘭花" in r[1] for r in results_a):
        print(">> PASS: Vocabulary replacement worked.")
    else:
        print(">> FAIL: Vocabulary replacement failed.")

    # Case B: "高貴 花椰菜"
    input_b = "高貴 花椰菜"
    tokens_b = input_b.split()
    trans_tokens_b = [vocab_map.get(t, t) for t in tokens_b]
    print(f"Input: '{input_b}' -> Tokens: {tokens_b} -> Translated: {trans_tokens_b}")
    
    results_b = db.search_local_items(trans_tokens_b)
    print(f"Search Results for {trans_tokens_b}:")
    for r in results_b:
        print(f" - {r[1]}")

    if any("高貴的西蘭花" in r[1] for r in results_b):
        print(">> PASS: Mixed mixed vocabulary worked.")
    else:
        print(">> FAIL: Mixed vocabulary failed.")

if __name__ == "__main__":
    test_search_logic()
