import asyncio
import logging
from common.network import send_msg, recv_msg

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

# -------------------------------
# 設定區
# -------------------------------
DB_HOST = "127.0.0.1"       # DB Server 位址
DB_PORT = 9000              # DB Server 監聽埠
LOBBY_HOST = "0.0.0.0"      # Lobby Server 對外開放 IP
LOBBY_PORT = 8000           # Lobby Server 監聽埠
db_reader = None
db_writer = None

# -------------------------------
# 記憶體內資料結構
# -------------------------------
# 線上使用者：{ user_id: {"name": str, "writer": StreamWriter, "room_id": int|None} }
online_users = {}

# 房間：{ room_id: {"name": str, "host": int, "members": [user_id...] } }
rooms = {}

# 邀請列表（非阻塞邀請系統）
# { invitee_id: [ { "invite_id": int, "room_id": int, "inviter": str, "status": "pending" } ] }
invites = {}

# -------------------------------
# 與 DB Server 溝通
# -------------------------------
async def db_request(req: dict):
    """透過既有的持續 TCP 連線與 DB Server 溝通"""
    global db_reader, db_writer
    try:
        await send_msg(db_writer, req)
        resp = await recv_msg(db_reader)
        return resp
    except Exception as e:
        print(f"⚠️ DB Server 通訊錯誤: {e}")
        return {"ok": False, "error": str(e)}


# -------------------------------
# 輔助函式
# -------------------------------
async def send_to_user(user_id: int, data: dict):
    """對特定使用者發送訊息"""
    user = online_users.get(user_id)
    if user:
        await send_msg(user["writer"], data)

async def broadcast_room(room_id: int, data: dict):
    """向房間內所有玩家廣播"""
    room = rooms.get(room_id)
    if room:
        for uid in room["members"]:
            await send_to_user(uid, data)

# -------------------------------
# 核心邏輯：處理玩家請求
# -------------------------------
async def handle_request(req, writer):
    collection = req.get("collection")
    action = req.get("action")
    data = req.get("data", {})

    # === 1️⃣ User 相關：註冊、登入、登出 ===
    if collection == "User":
        resp = await db_request(req)

        # 登入成功 → 紀錄使用者資訊
        if action in ("create", "login") and resp.get("ok"):
            uid = resp["id"]
            online_users[uid] = {
                "name": data["name"],
                "writer": writer,
                "room_id": None
            }
            print(f"👤 使用者登入：{data['name']} (id={uid})")

        # 登出 → 移除線上清單
        elif action == "logout" and resp.get("ok"):
            uid = data["id"]
            if uid in online_users:
                online_users.pop(uid)
                print(f"👋 使用者登出 id={uid}")

        return resp


    # === 2️⃣ Room 相關 ===
    elif collection == "Room":
        # 建立房間（交給 DB Server 寫入）
        if action == "create":
            resp = await db_request(req)
            if resp.get("ok"):
                rid = resp["room_id"]
                host = data["host_user_id"]
                rooms[rid] = {
                    "name": data["name"],
                    "host": host,
                    "members": [host],
                }
                online_users[host]["room_id"] = rid
                print(f"🏠 建立房間 {rid} ({data['name']}) by user {host}")
            return resp

        # 列出公開房間（只轉發）
        elif action == "list":
            return await db_request(req)
        
        elif action == "close":
            resp = await db_request(req)
            return resp


    # === 3️⃣ Invite 相關 ===
    elif collection == "Invite":
        # 建立邀請（DB 寫入 + Lobby 暫存）
        if action == "create":
            resp = await db_request(req)
            return resp


    # === 4️⃣ Game 相關（之後開對戰伺服器用）===
    elif collection == "Game":
        # 先只轉發給 DB（記錄對局），之後再改為啟動 game_server
        return await db_request(req)


    # === 5️⃣ 其他未知請求 ===
    else:
        return {"ok": False, "error": f"未知 collection/action: {collection}/{action}"}


# -------------------------------
# 玩家連線處理
# -------------------------------
async def handle_client(reader, writer):
    addr = writer.get_extra_info("peername")
    print(f"📡 玩家連線: {addr}")

    try:
        while True:
            req = await recv_msg(reader)
            if not req:
                break
            print(f"📥 收到來自 {addr}: {req}")

            resp = await handle_request(req, writer)
            await send_msg(writer, resp)

    except asyncio.IncompleteReadError:
        print(f"❌ 玩家斷線: {addr}")
    finally:
        # 清理掉線的玩家
        for uid, info in list(online_users.items()):
            if info["writer"] is writer:
                print(f"👋 玩家離線 id={uid}")
                
                # 通知 DB Server 登出
                try:
                    await db_request({
                        "collection": "User",
                        "action": "logout",
                        "data": {"id": uid}
                    })
                    print(f"🗂 已通知 DB Server 登出使用者 id={uid}")
                except Exception as e:
                    print(f"⚠️ 登出通知 DB Server 失敗：{e}")
                
                online_users.pop(uid)
                break
        try:
            writer.close()
            await writer.wait_closed()
        except (ConnectionResetError, OSError):
            # ✅ 忽略 WinError 64 等常見錯誤
            pass


# -------------------------------
# 主程式入口
# -------------------------------
async def main():
    global db_reader, db_writer

    # 啟動時就連上 DB Server
    db_reader, db_writer = await asyncio.open_connection(DB_HOST, DB_PORT)
    print(f"✅ 已連線至 DB Server {DB_HOST}:{DB_PORT}")
    
    # Lobby 初始化
    resp = await db_request({"collection": "Lobby", "action": "init"})
    if resp.get("ok"):
        print("🧹 Lobby 初始化：所有使用者狀態已重設。")
    else:
        print(f"⚠️ Lobby 初始化失敗：{resp.get('error')}")

    # 啟動 Lobby Server
    server = await asyncio.start_server(handle_client, LOBBY_HOST, LOBBY_PORT)
    addr = server.sockets[0].getsockname()
    print(f"✅ Lobby Server 啟動於 {addr}")

    try:
        async with server:
            await server.serve_forever()
    finally:
        if db_writer:
            db_writer.close()
            await db_writer.wait_closed()
            print("🛑 已關閉 DB 連線。")

if __name__ == "__main__":
    asyncio.run(main())
