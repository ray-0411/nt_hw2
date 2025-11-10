import asyncio
import logging
from common.network import send_msg, recv_msg
import socket
import subprocess
import time

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

# -------------------------------
# 設定區
# -------------------------------
DB_HOST = "127.0.0.1"       # DB Server 位址
DB_PORT = 14411              # DB Server 監聽埠




def get_host_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 不需要真的連上網，這行只是讓 OS 幫我們找出出口介面 IP
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

LOBBY_HOST = get_host_ip()     # Lobby Server 對外開放 IP
LOBBY_PORT = 14110           # Lobby Server 監聽埠
db_reader = None
db_writer = None

# -------------------------------
# 記憶體內資料結構
# -------------------------------
# online_users = {
#     user_id: {
#         "name": str,
#         "writer": asyncio.StreamWriter,  # 用來發訊息給該玩家
#         "room_id": int | None            # 目前所在房間（None 表示沒進房）
#     }
# }
online_users = {}

# rooms = {
#     room_id: {
#         "name": str,              # 房間名稱
#         "host_id": int,           # 房主使用者 ID
#         "guest_id": int | None,   # 客人 ID（無人時為 None）
#         "visibility": "public" | "private",  # 房間類型
#         "password": str | None,         # 若為 private，存雜湊密碼
#         "status": "space" | "full" | "play", # 房間狀態
#         "port": int | None                   # 遊戲伺服器埠號
#     }
# }
rooms = {}
room_counter = 0  

# invites = {
#     invitee_id: [
#         {
#             "invite_id": int,
#             "room_id": int,
#             "inviter_id": int,
#             "invitee_id": int
#         }
#     ]
# }
invites = {}
invite_counter = 0
    
def find_free_port(start=16800, end=16900):
    import socket
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((LOBBY_HOST, port))
                s.listen(1)  # 確保真的能 listen
                return port
            except OSError:
                continue
    raise RuntimeError("❌ 沒有可用的 port")



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
            global room_counter
            rid = room_counter
            room_counter += 1
            
            host_id = data["host_user_id"]
            name = data.get("name", f"Room_{rid}")
            visibility = data.get("visibility", "public")
            password = data.get("password") if visibility == "private" else None

            rooms[rid] = {
                "name": name,
                "host_id": host_id,
                "guest_id": None,
                "visibility": visibility,
                "password": password,   
                "status": "space",
                "port": None
            }

            online_users[host_id]["room_id"] = rid
            print(f"🏠 房主 {host_id} 建立房間 {rid}（{visibility}）")
            return {"ok": True, "room_id": rid}

        # 列出公開房間（只轉發）
        elif action == "list":
            try:
                only_available = data.get("only_available", "space")
                result = []
                
                for rid, r in rooms.items():
                    if only_available == "space":
                        if r["status"] == "space":
                            result.append({
                                "id": rid,
                                "name": r["name"],
                                "host": online_users[r["host_id"]]["name"],
                                "visibility": r["visibility"],
                                "status": r["status"]
                            })

                return {"ok": True, "rooms": result}
            except Exception as e:
                return {"ok": False, "error": str(e)}
            
        elif action == "close":
            rid = data.get("room_id")
            host_id = data.get("host_user_id")

            # 🟩 檢查房間是否存在
            if rid not in rooms:
                return {"ok": False, "error": "Room not found."}
            room = rooms[rid]

            # 🟩 確認執行者是房主
            if room["host_id"] != host_id:
                return {"ok": False, "error": "Only the host can close the room."}
            
            # 🟩 若房間裡有 guest，通知他房間被關閉
            guest_id = room.get("guest_id")
            if guest_id and guest_id in online_users:
                online_users[guest_id]["room_id"] = None

            # 🟩 更新房主狀態
            if host_id in online_users:
                online_users[host_id]["room_id"] = None

            # 🟩 最後刪除房間
            rooms.pop(rid, None)
            print(f"🗑️ 房間 {rid} 已由房主 {host_id} 關閉。")
            return {"ok": True, "msg": f"房間 {rid} 已關閉。"}

        elif action == "join":
            rid = data.get("room_id")
            uid = data.get("user_id")
            password = data.get("password")

            # 🟩 檢查房間是否存在
            if rid not in rooms:
                return {"ok": False, "error": "房間不存在。"}
            room = rooms[rid]

            # 🟩 檢查是否為私人房，若是就比對密碼
            if room["visibility"] == "private":
                if not password:
                    return {"ok": False, "error": "此房間為私人房，請輸入密碼。"}
                if password != room["password"]:
                    return {"ok": False, "error": "密碼錯誤。"}

            return await join_room(uid, rid)
        
        elif action == "status":
            rid = data.get("room_id")
            room = rooms.get(rid)

            if not room:
                return {"ok": False, "error": "Room not found."}

            # 從 online_users 查出 guest 名字
            guest_id = room.get("guest_id")
            guest_name = None
            if guest_id and guest_id in online_users:
                guest_name = online_users[guest_id]["name"]
                
            
            host = get_host_ip()
            game_port = room.get("port")

            return {
                "ok": True,
                "status": room["status"],
                "guest_joined": bool(guest_id),
                "guest_id": guest_id,
                "guest_name": guest_name,
                "game_host": host,
                "game_port": game_port
            }
        
        elif action == "kick":
            rid = data.get("room_id")
            room = rooms.get(rid)

            if not room:
                return {"ok": False, "error": "Room not found."}

            guest_id = room.get("guest_id")
            if not guest_id:
                return {"ok": False, "error": "No guest to kick."}

            # 從 online_users 查出 guest 名字
            guest_name = online_users.get(guest_id, {}).get("name", "未知玩家")

            # 清空 guest 資料並重設狀態
            room["guest_id"] = None
            room["status"] = "space"

            # 更新 guest 狀態
            if guest_id in online_users:
                online_users[guest_id]["room_id"] = None

            print(f"👢 房主踢出了玩家 {guest_name} (id={guest_id}) from room {rid}")
            return {"ok": True, "msg": f"玩家 {guest_name} 已被踢出。"}

        elif action == "leave":
            rid = data.get("room_id")
            uid = data.get("user_id")

            room = rooms.get(rid)
            if not room:
                return {"ok": False, "error": "房間不存在。"}

            user_info = online_users.get(uid)
            if not user_info:
                return {"ok": False, "error": "使用者未登入。"}

            if uid == room["guest_id"]:
                print(f"👋 玩家 {user_info['name']} 離開房間 {rid}")
                room["guest_id"] = None
                room["status"] = "space"
                user_info["room_id"] = None
                return {"ok": True, "msg": "你已離開房間。"}

            return {"ok": False, "error": "你不在該房間中。"}

    # === 3️⃣ Invite 相關 ===
    elif collection == "Invite":
        if action == "create":
            global invite_counter
            inviter_id = data.get("inviter_id")
            invitee_id = data.get("invitee_id")
            room_id = data.get("room_id")

            # 🟩 防呆：檢查 inviter 是否在線上
            if inviter_id not in online_users:
                return {"ok": False, "error": "Inviter not online."}

            # 🟩 防呆：檢查 invitee 是否在線上
            if invitee_id not in online_users:
                return {"ok": False, "error": "該玩家目前不在線上。"}

            # 🟩 檢查房間是否存在
            if room_id not in rooms:
                return {"ok": False, "error": "房間不存在。"}

            # 🟩 建立邀請紀錄
            invite = {
                "invite_id": invite_counter,
                "room_id": room_id,
                "inviter_id": inviter_id,
                "invitee_id": invitee_id
            }
            invite_counter += 1

            invites.setdefault(invitee_id, []).append(invite)

            inviter_name = online_users[inviter_id]["name"]
            invitee_name = online_users[invitee_id]["name"]
            room_name = rooms[room_id]["name"]

            print(f"📨 {inviter_name} (id={inviter_id}) 邀請 {invitee_name} (id={invitee_id}) 加入房間 {room_name} (id={room_id})")

            return {"ok": True, "invite_id": invite["invite_id"]}

        elif action == "list":
            uid = data.get("user_id")

            # 🟩 檢查使用者是否在線
            if uid not in online_users:
                return {"ok": False, "error": "User not online."}

            # 🟩 取出該使用者收到的所有邀請
            user_invites = invites.get(uid, [])

            # 🟩 整理成可讀格式
            result = []
            for inv in user_invites:
                inviter_id = inv["inviter_id"]
                inviter_name = online_users.get(inviter_id, {}).get("name", "未知玩家")
                room_id = inv["room_id"]
                room_name = rooms.get(room_id, {}).get("name", "未知房間")

                result.append({
                    "invite_id": inv["invite_id"],
                    "from_id": inviter_id,
                    "from_name": inviter_name,
                    "room_id": room_id,
                    "room_name": room_name
                })

            return {"ok": True, "invites": result}

        elif action == "respond":
            invitee_id = data.get("invitee_id")  # 被邀請者（當前玩家）
            invite_id = data.get("invite_id")    # 要處理的邀請 ID
            accept = data.get("accept", False)   # True=同意, False=拒絕

            # 🟩 1️⃣ 檢查該玩家有無邀請
            if invitee_id not in invites:
                return {"ok": False, "error": "沒有邀請資料。"}
            user_invites = invites[invitee_id]

            # 🟩 2️⃣ 找出該邀請
            invite = next((inv for inv in user_invites if inv["invite_id"] == invite_id), None)
            if not invite:
                return {"ok": False, "error": "找不到指定的邀請。"}

            inviter_id = invite["inviter_id"]
            room_id = invite["room_id"]
            inviter_name = online_users.get(inviter_id, {}).get("name", "未知玩家")
            invitee_name = online_users.get(invitee_id, {}).get("name", "未知玩家")

            # 🟩 3️⃣ 如果拒絕邀請
            if not accept:
                user_invites.remove(invite)
                if not user_invites:
                    invites.pop(invitee_id, None)

                print(f"❌ {invitee_name} 拒絕了 {inviter_name} 的邀請 (invite_id={invite_id})")
            
                return {"ok": True, "msg": "已拒絕邀請。"}
            
            else:
                print(f"✅ {invitee_name} 同意 {inviter_name} 的邀請，加入房間 {room_id}")
                
                join_resp = await join_room(invitee_id, room_id)
                
                user_invites.remove(invite)
                if not user_invites:
                    invites.pop(invitee_id, None)

                return join_resp


    # === 4️⃣ Game 相關（之後開對戰伺服器用）===
    elif collection == "Game":
        if action == "start":
            rid = data.get("room_id")
            room = rooms.get(rid)
            
            if not room:
                return {"ok": False, "error": "房間不存在"}
            
            game_port = find_free_port(16800, 16900)
            
            print(f"🎮 房間 {rid} 要開始遊戲 → 啟動 Game Server on port {game_port}")
            
            subprocess.Popen(
                ["python", "-m", "game.game_server", str(game_port),str(rid)]
            )
            
            room["status"] = "play"
            room["port"] = game_port
            
            host= get_host_ip()
            
            return {
                "ok": True,
                "game_host": host,
                "game_port": game_port
            }
        
        elif action == "report":
            data = req.get("data", {})
            result = data.get("result", {})
            winner = data.get("winner")

            print(f"🏁 房間 {data.get('room_id')} 結束，勝方是 {winner}")
            for key, info in result.items():
                uid = info.get("user_id")
                sc = info.get("score")
                lv = info.get("level")
                print(f"  玩家 {uid}: 分數={sc}, 等級={lv}")


    # === 5️⃣ 其他未知請求 ===
    else:
        return {"ok": False, "error": f"未知 collection/action: {collection}/{action}"}

#重複function

async def join_room(uid: int, rid: int):
    room = rooms.get(rid)
    if not room:
        return {"ok": False, "error": "房間不存在。"}
    
    if uid not in online_users:
        return {"ok": False, "error": "使用者未登入。"}

    # 🟩  檢查房間狀態
    if room["status"] == "full":
        return {"ok": False, "error": "房間已滿。"}
    if room["status"] == "play":
        return {"ok": False, "error": "遊戲已開始，無法加入。"}
    
    # 🟩  確認使用者沒有同時在其他房
    user_info = online_users.get(uid)
    if user_info["room_id"] is not None:
        return {"ok": False, "error": "你已在其他房間中。"}


    # 🟩 更新房間與玩家狀態
    room["guest_id"] = uid
    room["status"] = "full"
    online_users[uid]["room_id"] = rid

    guest_name = user_info["name"]

    print(f"🎮 玩家 {guest_name} (id={uid}) 加入房間 {rid}")

    return {"ok": True, "room_id": rid}

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
            #print(f"📥 收到來自 {addr}: {req}")

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
