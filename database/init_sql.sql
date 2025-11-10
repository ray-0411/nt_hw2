-- ========================================
--  Table 1. users
--  玩家帳號、登入狀態、所在房間
-- ========================================

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,                        -- 使用者名稱
    password_hash TEXT NOT NULL,                      -- 雜湊密碼
    is_logged_in INTEGER DEFAULT 0,                   -- 登入狀態 (0=離線, 1=在線)
    current_room_id INTEGER DEFAULT NULL,             -- 玩家目前所在房間 (NULL 表示未在房間)
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,        -- 建立時間
    last_login_at TEXT                               -- 最後登入時間
);

-- ========================================
--  Table 5. gameresults
--  功能：記錄每位玩家在該場遊戲的最終成績
--  一場遊戲 (gamelog) 對應多筆結果（每位玩家一筆）
-- ========================================

CREATE TABLE IF NOT EXISTS gameresults (
    id INTEGER PRIMARY KEY AUTOINCREMENT,              -- 主鍵，自動流水號
    user_id INTEGER NOT NULL,                          -- 玩家 ID（外鍵對 users.id）
    opponent_id INTEGER NOT NULL,                      -- 對手玩家 ID（外鍵對 users.id）

    score INTEGER DEFAULT 0 CHECK(score >= 0),         -- 最終分數
    level INTEGER DEFAULT 0 CHECK(level >= 0),         -- 最終等級（依規則上升）
    win INTEGER DEFAULT 0 CHECK(win IN (0, 1)),      -- 是否獲勝（0=否, 1=是）

    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (opponent_id) REFERENCES users(id)
);

