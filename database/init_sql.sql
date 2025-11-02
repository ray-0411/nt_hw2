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
--  Table 2. rooms
--  房間資訊 (房主、公私有、狀態、密碼)
-- ========================================

CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                               -- 房間名稱
    host_user_id INTEGER NOT NULL,                    -- 房主 ID
    guest_user_id INTEGER DEFAULT NULL,
    visibility TEXT CHECK(visibility IN ('public', 'private')) DEFAULT 'public',  -- 公開/私有
    password_hash TEXT,                               -- 私有房間密碼 (雜湊儲存)
    status TEXT CHECK(status IN ('idle', 'playing', 'closed')) DEFAULT 'idle',     -- 房間狀態
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,        -- 建立時間
    game_port INTEGER,                                -- 遊戲伺服器連線埠 (遊戲中使用)
    FOREIGN KEY (host_user_id) REFERENCES users(id)
);

-- ========================================
--  Table 3. room_invites
--  房間邀請記錄 (發出者、被邀請者、回覆狀態)
-- ========================================

CREATE TABLE IF NOT EXISTS room_invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,                         -- 房間 ID
    inviter_id INTEGER NOT NULL,                      -- 發出邀請的使用者
    invitee_id INTEGER NOT NULL,                      -- 被邀請的使用者
    status TEXT CHECK(status IN ('pending', 'accepted', 'rejected')) DEFAULT 'pending',  -- 狀態
    invited_at TEXT DEFAULT CURRENT_TIMESTAMP,        -- 發送邀請時間
    responded_at TEXT,                                -- 回覆時間
    FOREIGN KEY (room_id) REFERENCES rooms(id),
    FOREIGN KEY (inviter_id) REFERENCES users(id),
    FOREIGN KEY (invitee_id) REFERENCES users(id)
);

-- ========================================
--  Table 4. gamelogs
--  功能：記錄每場遊戲的整體摘要（哪個房間、何時開始結束、誰贏了）
-- ========================================

CREATE TABLE IF NOT EXISTS gamelogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,              -- 主鍵，自動流水號
    match_id TEXT UNIQUE,                              -- 對局識別碼（可用 UUID，方便跨伺服器追蹤）
    room_id INTEGER NOT NULL,                          -- 該場比賽所屬房間 ID
    seed TEXT,                                         -- 方塊生成亂數種子（確保雙方方塊一致）
    start_at TEXT DEFAULT CURRENT_TIMESTAMP,           -- 遊戲開始時間
    end_at TEXT,                                       -- 遊戲結束時間
    winner_user_id INTEGER,                            -- 勝利者 ID（平手可為 NULL）
    victory_reason TEXT,                               -- 結束原因（例如：'timeup', 'topout', 'tie'）

    -- 關聯：房間與使用者
    FOREIGN KEY (room_id) REFERENCES rooms(id),
    FOREIGN KEY (winner_user_id) REFERENCES users(id)
);

-- ========================================
--  Table 5. gameresults
--  功能：記錄每位玩家在該場遊戲的最終成績
--  一場遊戲 (gamelog) 對應多筆結果（每位玩家一筆）
-- ========================================

CREATE TABLE IF NOT EXISTS gameresults (
    id INTEGER PRIMARY KEY AUTOINCREMENT,              -- 主鍵，自動流水號
    gamelog_id INTEGER NOT NULL,                       -- 對應哪一場遊戲（外鍵對 gamelogs.id）
    user_id INTEGER NOT NULL,                          -- 玩家 ID（外鍵對 users.id）

    score INTEGER DEFAULT 0 CHECK(score >= 0),         -- 最終分數
    level INTEGER DEFAULT 1 CHECK(level >= 1),         -- 最終等級（依規則上升）

    -- 關聯：一場遊戲中同一玩家只能有一筆記錄
    UNIQUE (gamelog_id, user_id),

    FOREIGN KEY (gamelog_id) REFERENCES gamelogs(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

