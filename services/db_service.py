import sqlite3
import os

DB_PATH = os.path.join("db", "id_manager.db")
SCHEMA_PATH = os.path.join("models", "schema.sql")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    with open(SCHEMA_PATH, "r") as f:
        cur.executescript(f.read())

    conn.commit()
    conn.close()

def add_account():
    print("=== 新規アカウント登録 ===")
    title = input("タイトル: ")
    account_id = input("アカウントID: ")
    password = input("パスワード: ")
    email = input("メールアドレス: ")
    email2 = input("2nd メールアドレス: ")
    url = input("URL: ")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO accounts (title, account_id, password, email, email2, url)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (title, account_id, password, email, email2, url))
    conn.commit()
    conn.close()

    print("保存しました！")
