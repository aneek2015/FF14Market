import sqlite3
import logging
import os
import json
import ijson

class DatabaseManager:
    def __init__(self, db_path="market_app.db"):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        """Creates and returns a new database connection."""
        conn = sqlite3.connect(self.db_path)
        # Enable Write-Ahead Logging for better concurrency
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        return conn

    def init_db(self):
        """Initializes database tables."""
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute('''CREATE TABLE IF NOT EXISTS custom_servers
                             (name TEXT PRIMARY KEY)''')
                c.execute('''CREATE TABLE IF NOT EXISTS item_cache
                             (id INTEGER PRIMARY KEY, name TEXT)''')
                c.execute('''CREATE INDEX IF NOT EXISTS idx_item_name ON item_cache (name)''')
                
                # Favorites table updated with category_id
                c.execute('''CREATE TABLE IF NOT EXISTS favorites
                             (id INTEGER PRIMARY KEY, name TEXT, category_id INTEGER DEFAULT 1)''')
                
                # Check if category_id column exists (migration)
                try:
                    c.execute("SELECT category_id FROM favorites LIMIT 1")
                except sqlite3.OperationalError:
                     logging.info("Migrating favorites table: Adding category_id column...")
                     c.execute("ALTER TABLE favorites ADD COLUMN category_id INTEGER DEFAULT 1")

                # Categories Table
                c.execute('''CREATE TABLE IF NOT EXISTS categories
                             (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)''')
                
                # Settings
                c.execute('''CREATE TABLE IF NOT EXISTS settings
                             (key TEXT PRIMARY KEY, value TEXT)''')

                # User Vocabulary Table (New)
                c.execute('''CREATE TABLE IF NOT EXISTS user_vocabulary
                             (original_term TEXT PRIMARY KEY, corrected_term TEXT)''')
                
                # Ensure default servers exist
                default_servers = ['伊弗利特', '利維坦', '奧汀', '巴哈姆特', '泰坦', '迦樓羅', '鳳凰', '繁中服']
                c.executemany("INSERT OR IGNORE INTO custom_servers (name) VALUES (?)", [(s,) for s in default_servers])
                
                # Ensure default categories exist
                default_cats = ['未分類', '材料', '食物', '藥水', '裝備', '其他']
                for cat in default_cats:
                    c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))
                
                conn.commit()
                logging.info("Database initialized successfully.")
        except Exception as e:
            logging.error(f"Database initialization failed: {e}")

    # --- Vocabulary (New) ---
    def get_all_vocabulary(self):
        """Fetches all user-defined vocabulary into a dictionary."""
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT original_term, corrected_term FROM user_vocabulary")
                return dict(c.fetchall())
        except Exception as e:
            logging.error(f"Failed to get vocabulary: {e}")
            return {}

    def add_or_update_vocabulary(self, original_term, corrected_term):
        """Adds or updates a vocabulary rule."""
        if not original_term or not corrected_term: return False
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO user_vocabulary (original_term, corrected_term) VALUES (?, ?)", (original_term, corrected_term))
                conn.commit()
            logging.info(f"Vocabulary updated: '{original_term}' -> '{corrected_term}'")
            return True
        except Exception as e:
            logging.error(f"Failed to update vocabulary: {e}")
            return False

    def delete_vocabulary(self, original_term):
        """Deletes a vocabulary rule."""
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute("DELETE FROM user_vocabulary WHERE original_term = ?", (original_term,))
                conn.commit()
            logging.info(f"Vocabulary rule removed for: '{original_term}'")
            return True
        except Exception as e:
            logging.error(f"Failed to delete vocabulary rule: {e}")
            return False

    # --- Settings ---
    def load_settings(self, default_config):
        """Loads settings from DB, overriding defaults where applicable."""
        config = default_config.copy()
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT key, value FROM settings")
                rows = c.fetchall()
                
            for key, val in rows:
                if key in config:
                    try:
                        if '.' in val:
                            config[key] = float(val)
                        else:
                            config[key] = int(val)
                    except:
                        pass
            logging.info(f"Settings loaded: {config}")
        except Exception as e:
            logging.error(f"Failed to load settings: {e}")
        return config

    def save_setting(self, key, value):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
                conn.commit()
        except Exception as e:
            logging.error(f"Failed to save setting {key}: {e}")

    # --- Servers ---
    def get_custom_servers(self):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT name FROM custom_servers")
                rows = c.fetchall()
            return [r[0] for r in rows]
        except Exception as e:
            logging.error(f"Failed to get servers: {e}")
            return []

    def add_custom_server(self, server_name):
        if not server_name: return False
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute("INSERT OR IGNORE INTO custom_servers (name) VALUES (?)", (server_name,))
                conn.commit()
            return True
        except Exception as e:
            logging.error(f"Failed to add server: {e}")
            return False

    # --- Item Cache ---
    def cache_item(self, item_id, item_name):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO item_cache (id, name) VALUES (?, ?)", (item_id, item_name))
                conn.commit()
        except Exception as e:
            logging.error(f"Failed to cache item: {e}")

    def search_local_items(self, query, limit=1):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                if limit == 1:
                    c.execute("SELECT id, name FROM item_cache WHERE name = ? LIMIT 1", (query,))
                    result = c.fetchone()
                    if not result:
                        c.execute("SELECT id, name FROM item_cache WHERE name LIKE ? LIMIT 1", (f'%{query}%',))
                        result = c.fetchone()
                    return result
                else:
                    c.execute("SELECT id, name FROM item_cache WHERE name LIKE ? ORDER BY length(name) ASC LIMIT ?", (f'%{query}%', limit))
                    return c.fetchall()
        except Exception as e:
            logging.error(f"Local search failed: {e}")
            return None if limit == 1 else []

    def get_item_name_by_id(self, item_id):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT name FROM item_cache WHERE id = ?", (item_id,))
                result = c.fetchone()
            return result[0] if result else None
        except Exception as e:
             logging.error(f"Get item name failed: {e}")
             return None

    def import_json_cache(self, json_filename="items_cache_tw.json"):
        if not os.path.exists(json_filename):
            return
        try:
            logging.info(f"Checking for new items in {json_filename} to import via streaming...")
            
            with self.get_connection() as conn:
                c = conn.cursor()
                # We can do a rough check. If the DB is empty, show a more detailed message.
                c.execute("SELECT Count(*) FROM item_cache")
                db_count = c.fetchone()[0]
                if db_count == 0:
                    logging.info("Database item cache is empty, performing full import. This might take a moment...")

                # Use a transaction for much faster inserts
                conn.execute("BEGIN TRANSACTION;")
                try:
                    with open(json_filename, 'rb') as f: # Open in binary mode for ijson
                        # The JSON has a structure like {"by_name": {"item_name": item_id, ...}}
                        # We stream the inner dictionary's key-value pairs
                        items_stream = ijson.kvitems(f, 'by_name')
                        
                        # Use a generator expression for memory efficiency
                        # The stream yields (key, value), which is (name, id). We need to insert (id, name).
                        data_generator = ((v, k) for k, v in items_stream)
                        
                        c.executemany("INSERT OR IGNORE INTO item_cache (id, name) VALUES (?, ?)", data_generator)
                    
                    conn.commit()
                    logging.info(f"Item cache stream import completed. {c.rowcount} rows were affected in this run.")

                except Exception as e:
                    conn.rollback() # Rollback on error
                    logging.error(f"Error during streaming import, transaction rolled back: {e}")
                    # If ijson fails, it could be a malformed file.
                    # We don't want to delete it automatically, but we can log a hint.
                    logging.warning("The JSON cache file might be corrupted.")

        except Exception as e:
            logging.error(f"Import JSON failed: {e}")

    # --- Categories ---
    def get_categories(self):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT id, name FROM categories ORDER BY id")
                return c.fetchall()
        except Exception: return []

    def add_category(self, name):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute("INSERT INTO categories (name) VALUES (?)", (name,))
                conn.commit()
            return True
        except Exception: return False

    def delete_category(self, cat_id):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                # Move items to "Uncategorized" (ID 1) before deleting
                c.execute("UPDATE favorites SET category_id = 1 WHERE category_id = ?", (cat_id,))
                c.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
                conn.commit()
            return True
        except Exception: return False
    
    def rename_category(self, cat_id, new_name):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute("UPDATE categories SET name = ? WHERE id = ?", (new_name, cat_id))
                conn.commit()
            return True
        except Exception: return False

    # --- Favorites ---
    def add_favorite(self, item_id, item_name, category_id=1):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                # Upsert
                c.execute("INSERT OR REPLACE INTO favorites (id, name, category_id) VALUES (?, ?, ?)", (item_id, item_name, category_id))
                conn.commit()
            return True
        except Exception: return False

    def remove_favorite(self, item_id):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute("DELETE FROM favorites WHERE id = ?", (item_id,))
                conn.commit()
            return True
        except Exception: return False

    def get_favorites(self, category_id=None):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                if category_id:
                    c.execute("SELECT id, name, category_id FROM favorites WHERE category_id = ? ORDER BY name", (category_id,))
                else:
                    c.execute("SELECT id, name, category_id FROM favorites ORDER BY name")
                return c.fetchall()
        except Exception: return []

    def is_favorite(self, item_id):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT 1 FROM favorites WHERE id = ?", (item_id,))
                return c.fetchone() is not None
        except Exception: return False
