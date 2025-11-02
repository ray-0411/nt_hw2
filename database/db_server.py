import asyncio
import logging
from database import db_fun as db
from common.network import send_msg, recv_msg


asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

HOST = "0.0.0.0"
PORT = 9000

# ----------------------------
# 處理單一請求
# ----------------------------
async def handle_request(req: dict):
    collection = req.get("collection")
    action = req.get("action")
    data = req.get("data", {})

    try:
        # ---------- User ----------
        if collection == "User":
            if action == "create":
                return db.create_user(data["name"], data["password"])
            elif action == "login":
                return db.login_user(data["name"], data["password"])
            elif action == "logout":
                return db.logout_user(data["id"])
            elif action == "list_online":
                return {"ok": True, "users": db.get_online_users()}

        # ---------- Room ----------
        elif collection == "Room":
            if action == "create":
                return db.create_room(
                    data["name"],
                    data["host_user_id"],
                    data.get("visibility", "public"),
                    data.get("password")
                )
            elif action == "list":
                return {"ok": True, "rooms": db.list_rooms()}
            elif action == "join":
                return db.join_room(data["user_id"], data["room_id"])
            elif action == "leave":
                return db.leave_room(data["user_id"])

        # ---------- Invite ----------
        elif collection == "Invite":
            if action == "create":
                return db.create_invite(
                    data["room_id"], data["inviter_id"], data["invitee_id"]
                )
            elif action == "list":
                return {"ok": True, "invites": db.list_invites_for_user(data["user_id"])}
            elif action == "update":
                return db.update_invite_status(data["invite_id"], data["status"])

        # ---------- Game ----------
        elif collection == "Game":
            if action == "create_log":
                return db.create_gamelog(data["room_id"], data["seed"])
            elif action == "end_log":
                return db.end_gamelog(
                    data["gamelog_id"], data.get("winner_user_id"), data.get("reason")
                )
            elif action == "add_result":
                return db.add_game_result(
                    data["gamelog_id"], data["user_id"], data["score"], data["level"]
                )
            elif action == "list_results":
                return {"ok": True, "results": db.list_game_results(data["gamelog_id"])}

        return {"ok": False, "error": f"Unknown collection/action: {collection}/{action}"}

    except KeyError as e:
        return {"ok": False, "error": f"Missing field: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ----------------------------
# 處理每個連線
# ----------------------------
async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    print(f"📡 連線來自 {addr}")

    try:
        while True:
            req = await recv_msg(reader)
            if req is None:
                break
            print(f"📥 收到: {req}")
            resp = await handle_request(req)
            await send_msg(writer, resp)
    except asyncio.IncompleteReadError:
        print(f"❌ 客戶端 {addr} 中斷連線")
    finally:
        # 🧩 安全關閉區段
        try:
            writer.close()
            await writer.wait_closed()
        except (ConnectionResetError, OSError):
            # ⚠️ 忽略常見的斷線錯誤（例如對方已關閉 socket）
            pass


# ----------------------------
# 主程式
# ----------------------------
async def main():
    db.init_db()
    server = await asyncio.start_server(handle_client, HOST, PORT)
    addr = server.sockets[0].getsockname()
    print(f"✅ DB Server 啟動於 {addr}")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
