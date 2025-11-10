import sqlite3
import hashlib
from datetime import datetime
import uuid
import os


DB_PATH = "data.db"
INIT_SQL_FILE = os.path.join(os.path.dirname(__file__), "init_sql.sql")

#part1:初始化資料庫連線與結構

def get_conn():
    """建立 SQLite 連線（自動關閉 thread 限制）"""
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    """讀取 init_sql.sql 並初始化資料庫"""
    with open(INIT_SQL_FILE, "r", encoding="utf-8") as f:
        sql_script = f.read()

    with get_conn() as conn:
        conn.executescript(sql_script)
        conn.commit()
    print("✅ Database initialized from init_sql.sql")

#part2:users操作函式

def hash_password(password: str) -> str:
    """用 SHA256 雜湊密碼"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

#use
def lobby_init():
    """Lobby 初始化時呼叫：重設所有使用者登入狀態"""
    with get_conn() as conn:
        
        cur = conn.cursor()
        # 1️⃣ 全部使用者登出
        cur.execute("UPDATE users SET is_logged_in=0, current_room_id=NULL")
        
        
        conn.commit()
    
    print("🧹 Lobby Init: 所有使用者已標記為離線。")
    return {"ok": True, "msg": "All users reset to offline."}


def create_user(name: str, password: str):
    """註冊新使用者（註冊後自動登入）"""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (name, password_hash, is_logged_in, last_login_at) VALUES (?, ?, 1, datetime('now'))",
                (name, hash_password(password)),
            )
            conn.commit()
            user_id = cur.lastrowid
        return {"ok": True, "id": user_id, "msg": f"User '{name}' created & logged in."}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": f"Username '{name}' already exists."}

#use
def login_user(name: str, password: str):
    """登入使用者"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, password_hash, is_logged_in FROM users WHERE name=?", (name,))
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "User not found."}

        user_id, pw_hash, is_logged_in = row
        if pw_hash != hash_password(password):
            return {"ok": False, "error": "Invalid password."}

        # ✅ 檢查是否已登入
        if is_logged_in:
            return {"ok": False, "error": "User already logged in elsewhere."}

        # 更新登入狀態
        cur.execute(
            "UPDATE users SET is_logged_in=1, last_login_at=? WHERE id=?",
            (datetime.now().isoformat(), user_id),
        )
        conn.commit()
        return {"ok": True, "id": user_id, "name": name}

#use
def logout_user(user_id: int):
    """登出使用者"""
    with get_conn() as conn:
        cur = conn.cursor()
        # 取出使用者名稱
        cur.execute("SELECT name FROM users WHERE id=?", (user_id,))
        row = cur.fetchone()
        username = row[0] if row else None

        # 更新狀態
        cur.execute(
            "UPDATE users SET is_logged_in=0, current_room_id=NULL WHERE id=?",
            (user_id,),
        )
        conn.commit()

    print(f"🗂 使用者登出: id={user_id}, name={username}")
    return {"ok": True, "id": user_id, "name": username, "msg": "User logged out."}

#use
def get_online_users():
    """查詢所有在線使用者"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM users WHERE is_logged_in=1 ORDER BY id")
        return cur.fetchall()


#part5:game log、game result操作函式

def report_game_result(data):
    """
    將一場兩人對戰結果寫入 gameresults 表
    data:
    {
        "room_id": 3,
        "winner": 101,
        "result": {
            "p1": {"user_id": 101, "score": 12000, "level": 7},
            "p2": {"user_id": 205, "score": 9500,  "level": 6}
        }
    }
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        room_id = data.get("room_id")
        winner_id = data.get("winner")
        result = data.get("result", {})

        p1 = result.get("p1")
        p2 = result.get("p2")

        if not p1 or not p2:
            raise ValueError("❌ report_game_result: 缺少玩家資料")

        # 🧩 玩家 A
        cur.execute("""
            INSERT INTO gameresults (user_id, opponent_id, score, level, win)
            VALUES (?, ?, ?, ?, ?)
        """, (
            p1["user_id"], p2["user_id"], p1.get("score", 0), p1.get("level", 0),
            1 if p1["user_id"] == winner_id else 0
        ))

        # 🧩 玩家 B
        cur.execute("""
            INSERT INTO gameresults (user_id, opponent_id, score, level, win)
            VALUES (?, ?, ?, ?, ?)
        """, (
            p2["user_id"], p1["user_id"], p2.get("score", 0), p2.get("level", 0),
            1 if p2["user_id"] == winner_id else 0
        ))

        conn.commit()
        conn.close()

        print(f"🧾 已寫入房間 {room_id} 的遊戲結果：{p1['user_id']} vs {p2['user_id']}")
        return {"ok": True, "count": 2}

    except Exception as e:
        print("❌ report_game_result 寫入失敗:", e)
        return {"ok": False, "error": str(e)}

