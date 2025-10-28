# dal_sqlite.py
import sqlite3
import hashlib
from datetime import datetime
import uuid

DB_PATH = "data.db"
INIT_SQL_FILE = "init_sql.sql"

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


def create_user(name: str, password: str):
    """註冊新使用者"""
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO users (name, password_hash) VALUES (?, ?)",
                (name, hash_password(password)),
            )
            conn.commit()
        return {"ok": True, "msg": f"User '{name}' created."}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": f"Username '{name}' already exists."}

def login_user(name: str, password: str):
    """登入使用者"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, password_hash FROM users WHERE name=?", (name,))
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "User not found."}

        user_id, pw_hash = row
        if pw_hash != hash_password(password):
            return {"ok": False, "error": "Invalid password."}

        cur.execute(
            "UPDATE users SET is_logged_in=1, last_login_at=? WHERE id=?",
            (datetime.now().isoformat(), user_id),
        )
        conn.commit()
        return {"ok": True, "id": user_id, "name": name}

def logout_user(user_id: int):
    """登出使用者"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET is_logged_in=0, current_room_id=NULL WHERE id=?",
            (user_id,),
        )
        conn.commit()

def get_online_users():
    """查詢所有在線使用者"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM users WHERE is_logged_in=1 ORDER BY id")
        return cur.fetchall()

#part3:rooms操作函式

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

def list_rooms():
    """列出所有房間"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT r.id, r.name, u.name AS host_name, r.visibility, r.status, r.created_at
            FROM rooms r
            JOIN users u ON r.host_user_id = u.id
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

def verify_room_password(room_id: int, password: str):
    """驗證私有房間密碼"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM rooms WHERE id=?", (room_id,))
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "Room not found."}
        pw_hash = row[0]
        if pw_hash != hash_password(password):
            return {"ok": False, "error": "Incorrect password."}
        return {"ok": True}

def join_room(user_id: int, room_id: int):
    """玩家加入房間"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET current_room_id=? WHERE id=?", (room_id, user_id)
        )
        conn.commit()
        return {"ok": True}

def leave_room(user_id: int):
    """玩家離開房間"""
    with get_conn() as conn:
        conn.execute("UPDATE users SET current_room_id=NULL WHERE id=?", (user_id,))
        conn.commit()
        return {"ok": True}

#part4:rooms invite操作函式

def create_invite(room_id: int, inviter_id: int, invitee_id: int):
    """建立一筆房間邀請紀錄"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO room_invites (room_id, inviter_id, invitee_id)
            VALUES (?, ?, ?)
            """,
            (room_id, inviter_id, invitee_id),
        )
        conn.commit()
        return {"ok": True, "invite_id": cur.lastrowid}

def list_invites_for_user(user_id: int):
    """列出該使用者被邀請的所有紀錄"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT  ri.id, r.name AS room_name, u.name AS inviter_name,
                    ri.status, ri.invited_at, ri.responded_at
            FROM room_invites ri
            JOIN rooms r ON ri.room_id = r.id
            JOIN users u ON ri.inviter_id = u.id
            WHERE ri.invitee_id=?
            ORDER BY ri.invited_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "room": r[1],
                "inviter": r[2],
                "status": r[3],
                "invited_at": r[4],
                "responded_at": r[5],
            }
            for r in rows
        ]

def update_invite_status(invite_id: int, status: str):
    """更新邀請狀態（'accepted' / 'rejected'）"""
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE room_invites
            SET status=?, responded_at=?
            WHERE id=?
            """,
            (status, datetime.now().isoformat(), invite_id),
        )
        conn.commit()
        return {"ok": True, "status": status}

#part5:game log、game result操作函式


def create_gamelog(room_id: int, seed: str):
    """建立一筆新的遊戲紀錄（自動產生 match_id）"""
    match_id = str(uuid.uuid4())  # 唯一識別碼
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO gamelogs (match_id, room_id, seed)
            VALUES (?, ?, ?)
            """,
            (match_id, room_id, seed),
        )
        conn.commit()
        return {"ok": True, "gamelog_id": cur.lastrowid, "match_id": match_id}

def end_gamelog(gamelog_id: int, winner_user_id: int = None, reason: str = None):
    """更新遊戲結束時間與勝利者"""
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE gamelogs
            SET end_at=?, winner_user_id=?, victory_reason=?
            WHERE id=?
            """,
            (datetime.now().isoformat(), winner_user_id, reason, gamelog_id),
        )
        conn.commit()
        return {"ok": True, "msg": "Game ended."}

def add_game_result(gamelog_id: int, user_id: int, score: int, level: int):
    """紀錄每位玩家的最終成績"""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO gameresults (gamelog_id, user_id, score, level)
            VALUES (?, ?, ?, ?)
            """,
            (gamelog_id, user_id, score, level),
        )
        conn.commit()
        return {"ok": True}

def list_game_results(gamelog_id: int):
    """查詢某場遊戲所有玩家的結果"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.name, gr.score, gr.level
            FROM gameresults gr
            JOIN users u ON gr.user_id = u.id
            WHERE gr.gamelog_id=?
            ORDER BY gr.score DESC
            """,
            (gamelog_id,),
        )
        rows = cur.fetchall()
        return [
            {"player": r[0], "score": r[1], "level": r[2]}
            for r in rows
        ]

