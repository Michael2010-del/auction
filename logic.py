import sqlite3
from datetime import datetime, timedelta
from config import DATABASE 
import os
import cv2
import numpy as np
from math import sqrt, ceil, floor

class DatabaseManager:
    def __init__(self, database):
        self.database = database

    def create_tables(self):
        conn = sqlite3.connect(self.database)
        with conn:
            conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                user_name TEXT,
                bonus_balance INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0
            )
        ''')

            conn.execute('''
            CREATE TABLE IF NOT EXISTS prizes (
                prize_id INTEGER PRIMARY KEY,
                image TEXT,
                used INTEGER DEFAULT 0,
                added_by INTEGER,
                added_date TEXT
            )
        ''')

            conn.execute('''
            CREATE TABLE IF NOT EXISTS winners (
                user_id INTEGER,
                prize_id INTEGER,
                win_time TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(prize_id) REFERENCES prizes(prize_id)
            )
        ''')

            conn.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                setting_name TEXT PRIMARY KEY,
                setting_value TEXT
            )
        ''')

            conn.execute('''
            CREATE TABLE IF NOT EXISTS re_auctions (
                prize_id INTEGER PRIMARY KEY,
                original_prize_id INTEGER,
                start_time TEXT,
                end_time TEXT,
                bonus_cost INTEGER DEFAULT 50,
                FOREIGN KEY(prize_id) REFERENCES prizes(prize_id)
            )
        ''')

            conn.commit()
            
            self.init_default_settings()

    def init_default_settings(self):
        default_settings = {
            'message_interval': '1',
            'winners_per_prize': '3',
            'bonus_per_win': '10',
            're_auction_bonus_cost': '50',
            're_auction_duration': '5'
        }
        
        conn = sqlite3.connect(self.database)
        with conn:
            for name, value in default_settings.items():
                conn.execute('''INSERT OR IGNORE INTO bot_settings (setting_name, setting_value) 
                              VALUES (?, ?)''', (name, value))
            conn.commit()

    def get_setting(self, setting_name):
        conn = sqlite3.connect(self.database)
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT setting_value FROM bot_settings WHERE setting_name = ?', (setting_name,))
            result = cur.fetchone()
            return result[0] if result else None

    def update_setting(self, setting_name, setting_value):
        conn = sqlite3.connect(self.database)
        with conn:
            conn.execute('''UPDATE bot_settings SET setting_value = ? 
                          WHERE setting_name = ?''', (setting_value, setting_name))
            conn.commit()

    def add_user(self, user_id, user_name):
        conn = sqlite3.connect(self.database)
        with conn:
            conn.execute('INSERT INTO users (user_id, user_name, bonus_balance, is_admin) VALUES (?, ?, 0, 0)', 
                        (user_id, user_name))
            conn.commit()

    def check_admin(self, user_id):
        conn = sqlite3.connect(self.database)
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
            result = cur.fetchone()
            if result:
                return result[0] == 1
            return False

    def set_admin(self, user_id):
        conn = sqlite3.connect(self.database)
        with conn:
            conn.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (user_id,))
            conn.commit()

    def add_prize(self, data, added_by=None):
        conn = sqlite3.connect(self.database)
        with conn:
            added_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            for item in data:
                conn.execute('''INSERT INTO prizes (image, used, added_by, added_date) 
                              VALUES (?, 0, ?, ?)''', (item[0], added_by, added_date))
            conn.commit()

    def add_winner(self, user_id, prize_id):
        win_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        bonus_per_win = int(self.get_setting('bonus_per_win'))
        
        conn = sqlite3.connect(self.database)
        with conn:
            cur = conn.cursor() 
            cur.execute("SELECT * FROM winners WHERE user_id = ? AND prize_id = ?", (user_id, prize_id))
            if cur.fetchall():
                return 0
            else:
                conn.execute('''INSERT INTO winners (user_id, prize_id, win_time) 
                              VALUES (?, ?, ?)''', (user_id, prize_id, win_time))
                conn.execute('''UPDATE users SET bonus_balance = bonus_balance + ? 
                              WHERE user_id = ?''', (bonus_per_win, user_id))
                conn.commit()
                return 1

    def get_user_bonus(self, user_id):
        conn = sqlite3.connect(self.database)
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT bonus_balance FROM users WHERE user_id = ?', (user_id,))
            result = cur.fetchone()
            if result:
                return result[0]
            return 0

    def spend_bonus(self, user_id, amount):
        conn = sqlite3.connect(self.database)
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT bonus_balance FROM users WHERE user_id = ?', (user_id,))
            current = cur.fetchone()[0]
            
            if current >= amount:
                cur.execute('''UPDATE users SET bonus_balance = bonus_balance - ? 
                             WHERE user_id = ?''', (amount, user_id))
                conn.commit()
                return True
            return False

    def create_re_auction(self, prize_id):
        bonus_cost = int(self.get_setting('re_auction_bonus_cost'))
        
        conn = sqlite3.connect(self.database)
        with conn:
            winners_count = self.get_winners_count(prize_id)
            max_winners = int(self.get_setting('winners_per_prize'))
            
            if winners_count < max_winners:
                cur = conn.cursor()
                cur.execute('SELECT image FROM prizes WHERE prize_id = ?', (prize_id,))
                image = cur.fetchone()[0]
                
                cur.execute('''INSERT INTO prizes (image, used) VALUES (?, 0)''', (image,))
                new_prize_id = cur.lastrowid
                
                start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                end_time = (datetime.now() + timedelta(minutes=int(self.get_setting('re_auction_duration')))).strftime('%Y-%m-%d %H:%M:%S')
                
                conn.execute('''INSERT INTO re_auctions (prize_id, original_prize_id, start_time, end_time, bonus_cost)
                              VALUES (?, ?, ?, ?, ?)''', (new_prize_id, prize_id, start_time, end_time, bonus_cost))
                conn.commit()
                
                return new_prize_id
            return None

    def get_active_re_auctions(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = sqlite3.connect(self.database)
        with conn:
            cur = conn.cursor()
            cur.execute('''SELECT * FROM re_auctions 
                          WHERE end_time > ?''', (now,))
            return cur.fetchall()

    def get_winners_img(self, user_id):
        conn = sqlite3.connect(self.database)
        with conn:
            cur = conn.cursor()
            cur.execute(''' 
                SELECT image FROM winners 
                INNER JOIN prizes ON winners.prize_id = prizes.prize_id
                WHERE user_id = ?
            ''', (user_id, ))
            return [x[0] for x in cur.fetchall()]

    def get_users(self):
        conn = sqlite3.connect(self.database)
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT user_id FROM users')
            return [x[0] for x in cur.fetchall()] 
            
    def get_random_prize(self):
        conn = sqlite3.connect(self.database)
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT * FROM prizes WHERE used = 0 ORDER BY RANDOM()')
            rows = cur.fetchall()
            return rows[0] if rows else None
        
    def get_prize_img(self, prize_id):
        conn = sqlite3.connect(self.database)
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT image FROM prizes WHERE prize_id = ?', (prize_id, ))
            return cur.fetchall()[0][0]
        
    def get_winners_count(self, prize_id):
        conn = sqlite3.connect(self.database)
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT COUNT(*) FROM winners WHERE prize_id = ?', (prize_id, ))
            return cur.fetchall()[0][0]

    def mark_prize_used(self, prize_id):
        conn = sqlite3.connect(self.database)
        with conn:
            conn.execute('''UPDATE prizes SET used = 1 WHERE prize_id = ?''', (prize_id,))
            conn.commit()

    def reset_used_prizes(self):
        conn = sqlite3.connect(self.database)
        with conn:
            conn.execute('''UPDATE prizes SET used = 0''')
            conn.commit()

    def get_rating(self):
        conn = sqlite3.connect(self.database)
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT users.user_name, COUNT(winners.prize_id) as count_prize, users.bonus_balance 
                FROM winners
                INNER JOIN users on users.user_id = winners.user_id
                GROUP BY winners.user_id
                ORDER BY count_prize DESC
                LIMIT 10
            ''')
            return cur.fetchall()

    def get_all_prizes(self):
        conn = sqlite3.connect(self.database)
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT * FROM prizes ORDER BY added_date DESC')
            return cur.fetchall()

    def delete_prize(self, prize_id):
        conn = sqlite3.connect(self.database)
        with conn:
            conn.execute('DELETE FROM prizes WHERE prize_id = ?', (prize_id,))
            conn.commit()

def hide_img(img_name):
    image = cv2.imread(f'img/{img_name}')
    blurred_image = cv2.GaussianBlur(image, (15, 15), 0)
    pixelated_image = cv2.resize(blurred_image, (30, 30), interpolation=cv2.INTER_NEAREST)
    pixelated_image = cv2.resize(pixelated_image, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(f'hidden_img/{img_name}', pixelated_image)

def create_collage(image_paths):
    images = []
    for path in image_paths:
        image = cv2.imread(path)
        images.append(image)

    num_images = len(images)
    num_cols = floor(sqrt(num_images))
    if num_cols == 0:
        num_cols = 1
    num_rows = ceil(num_images/num_cols)
    
    collage = np.zeros((num_rows * images[0].shape[0], num_cols * images[0].shape[1], 3), dtype=np.uint8)
    
    for i, image in enumerate(images):
        row = i // num_cols
        col = i % num_cols
        collage[row*image.shape[0]:(row+1)*image.shape[0], col*image.shape[1]:(col+1)*image.shape[1], :] = image
    
    return collage

if __name__ == '__main__':
    manager = DatabaseManager(DATABASE)
    manager.create_tables()
    
    if os.path.exists('img'):
        prizes_img = os.listdir('img')
        data = [(x,) for x in prizes_img]
        manager.add_prize(data)