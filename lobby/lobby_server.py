import asyncio
from common.network import send_msg, recv_msg

# -------------------------------
# 設定區
# -------------------------------
DB_HOST = "127.0.0.1"       # DB Server 位址
DB_PORT = 9000              # DB Server 監聽埠
LOBBY_HOST = "0.0.0.0"      # Lobby Server 對外開放 IP
LOBBY_PORT = 8000           # Lobby Server 監聽埠

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
    """把 JSON 請求轉送給 DB Server 並回傳回應"""
    reader, writer = await asyncio.open_connection(DB_HOST, DB_PORT)
    await send_msg(writer, req)
    resp = await recv_msg(reader)
    writer.close()
    await writer.wait_closed()
    return resp


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

        # 加入房間
        elif action == "join":
            resp = await db_request(req)
            if resp.get("ok"):
                rid = data["room_id"]
                uid = data["user_id"]
                if rid in rooms:
                    rooms[rid]["members"].append(uid)
                    online_users[uid]["room_id"] = rid
                    await broadcast_room(rid, {
                        "type": "room_update",
                        "room_id": rid,
                        "members": rooms[rid]["members"]
                    })
            return resp

        # 離開房間
        elif action == "leave":
            resp = await db_request(req)
            if resp.get("ok"):
                uid = data["user_id"]
                rid = online_users[uid]["room_id"]
                if rid and rid in rooms:
                    if uid in rooms[rid]["members"]:
                        rooms[rid]["members"].remove(uid)
                        online_users[uid]["room_id"] = None
                        await broadcast_room(rid, {
                            "type": "room_update",
                            "room_id": rid,
                            "members": rooms[rid]["members"]
                        })
            return resp


    # === 3️⃣ Invite 相關 ===
    elif collection == "Invite":
        # 建立邀請（DB 寫入 + Lobby 暫存）
        if action == "create":
            resp = await db_request(req)
            if resp.get("ok"):
                invitee = data["invitee_id"]
                inviter = data["inviter_id"]
                room_id = data["room_id"]

                # 新增到 invitation list
                invites.setdefault(invitee, []).append({
                    "invite_id": resp["invite_id"],
                    "room_id": room_id,
                    "inviter": online_users[inviter]["name"],
                    "status": "pending",
                })

                # 通知被邀請者（非阻塞）
                await send_to_user(invitee, {
                    "type": "invited",
                    "from": online_users[inviter]["name"],
                    "room_id": room_id,
                })
            return resp

        # 列出邀請清單（不阻塞）
        elif action == "list":
            uid = data["user_id"]
            return {"ok": True, "invites": invites.get(uid, [])}

        # 回覆邀請（更新 DB 並通知雙方）
        elif action == "update":
            resp = await db_request(req)
            if resp.get("ok"):
                iid = data["invite_id"]
                status = data["status"]
                for lst in invites.values():
                    for inv in lst:
                        if inv["invite_id"] == iid:
                            inv["status"] = status
                await broadcast_room(data["room_id"], {
                    "type": "invite_update",
                    "invite_id": iid,
                    "status": status
                })
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
                online_users.pop(uid)
                break
        writer.close()
        await writer.wait_closed()


# -------------------------------
# 主程式入口
# -------------------------------
async def main():
    server = await asyncio.start_server(handle_client, LOBBY_HOST, LOBBY_PORT)
    addr = server.sockets[0].getsockname()
    print(f"✅ Lobby Server 啟動於 {addr}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
