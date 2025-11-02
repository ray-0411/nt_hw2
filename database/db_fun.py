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
        # 2️⃣ 所有房間設為 closed
        cur.execute("UPDATE rooms SET status='closed'")
        # 🔹 清除所有邀請紀錄
        cur.execute("DELETE FROM room_invites")
        
        conn.commit()
    
    print("🧹 Lobby Init: 所有使用者已標記為離線。")
    return {"ok": True, "msg": "All users reset to offline."}

#use
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
        
        # 若該使用者是房主，關閉其所有房間
        cur.execute("""
            UPDATE rooms
            SET status='closed'
            WHERE host_user_id=? AND status!='closed'
        """, (user_id,))

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

####################
#part3:rooms操作函式
####################

#use 
def create_room(name: str, host_user_id: int, visibility="public", password=None):
    """建立新房間，可選 private 密碼"""
    pw_hash = hash_password(password) if (password and visibility == "private") else None
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO rooms (name, host_user_id, visibility, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (name, host_user_id, visibility, pw_hash),
        )
        conn.commit()
        return {"ok": True, "room_id": cur.lastrowid}

#use
def list_rooms():
    """列出所有房間"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT r.id, r.name, u.name AS host_name, r.visibility, r.status, r.created_at
            FROM rooms r
            JOIN users u ON r.host_user_id = u.id
            WHERE r.status = 'idle'             -- ✅ 只顯示可用房間
                AND (r.guest_user_id IS NULL)   -- ✅ 只顯示未被佔用的房間
            ORDER BY r.id
            """
        )
        rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "host": r[2],
                "visibility": r[3],
                "status": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]


#use
def close_room(room_id: int, host_user_id: int):
    """關閉指定房間（僅限房主）"""
    with get_conn() as conn:
        cur = conn.cursor()
        # 驗證房主身分
        cur.execute("SELECT host_user_id FROM rooms WHERE id=?", (room_id,))
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "房間不存在"}
        if row[0] != host_user_id:
            return {"ok": False, "error": "非房主無法關閉房間"}

        # 🔹 關閉房間
        cur.execute("UPDATE rooms SET status='closed' WHERE id=?", (room_id,))
        # 🔹 移除使用者的 current_room_id
        cur.execute("UPDATE users SET current_room_id=NULL WHERE id=?", (host_user_id,))
        
        # 🔹 清除所有該房間的邀請
        cur.execute("DELETE FROM room_invites WHERE room_id=?", (room_id,))
        
        conn.commit()
    print(f"🏁 房間已關閉 id={room_id}")
    return {"ok": True}


def join_room(room_id: int, user_id: int, password=None):
    """玩家加入房間（檢查狀態與密碼）"""
    with get_conn() as conn:
        cur = conn.cursor()

        # 查詢房間狀態
        cur.execute("SELECT visibility, password_hash, status FROM rooms WHERE id=?", (room_id,))
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "房間不存在"}

        visibility, pw_hash, status = row

        # 檢查房間狀態
        if status != "idle":
            return {"ok": False, "error": "該房間不可加入（可能已開始或已關閉）"}

        # 若是 private，檢查密碼
        if visibility == "private":
            if not password:
                return {"ok": False, "error": "此房間需要密碼"}
            if hash_password(password) != pw_hash:
                return {"ok": False, "error": "密碼錯誤"}
        
        # ✅ 更新 guest_user_id
        cur.execute("UPDATE rooms SET guest_user_id=? WHERE id=?", (user_id, room_id))
        # 更新使用者所在房間
        cur.execute("UPDATE users SET current_room_id=? WHERE id=?", (room_id, user_id))
        conn.commit()

    print(f"🚪 玩家 {user_id} 加入房間 {room_id}")
    return {"ok": True}

#part4:rooms invite操作函式

def create_invite(inviter_id, invitee_id, room_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO room_invites (from_user_id, to_user_id, room_id, created_at) VALUES (?, ?, ?, datetime('now'))",
            (inviter_id, invitee_id, room_id)
        )
        conn.commit()
        return {"ok": True, "invite_id": cur.lastrowid}


#part5:game log、game result操作函式



