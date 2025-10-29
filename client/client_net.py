import asyncio
from common.network import send_msg, recv_msg

class LobbyClient:
    """封裝與 Lobby Server 的所有通訊邏輯"""

    def __init__(self, host="127.0.0.1", port=8000):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self.user_id = None
        self.username = None

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

    async def close(self):
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

    # -------------------------------
    # 封裝請求/回應機制
    # -------------------------------
    async def _req(self, collection, action, data=None):
        req = {"collection": collection, "action": action, "data": data or {}}
        await send_msg(self.writer, req)
        return await recv_msg(self.reader)

    # -------------------------------
    # 使用者相關
    # -------------------------------
    async def register(self, name, password):
        resp = await self._req("User", "create", {"name": name, "password": password})
        if resp.get("ok"):
            self.user_id = resp["id"]
            self.username = name
        return resp

    async def login(self, name, password):
        resp = await self._req("User", "login", {"name": name, "password": password})
        if resp.get("ok"):
            self.user_id = resp["id"]
            self.username = name
        return resp

    async def logout(self):
        if not self.user_id:
            return {"ok": False, "error": "尚未登入"}
        resp = await self._req("User", "logout", {"id": self.user_id})
        if resp.get("ok"):
            self.user_id = None
            self.username = None
        return resp

    async def list_online_users(self):
        return await self._req("User", "list_online")

    # -------------------------------
    # 房間相關
    # -------------------------------
    async def list_rooms(self):
        return await self._req("Room", "list")

    async def create_room(self, name, visibility="public"):
        if not self.user_id:
            return {"ok": False, "error": "請先登入"}
        data = {"name": name, "host_user_id": self.user_id, "visibility": visibility}
        return await self._req("Room", "create", data)

    async def join_room(self, room_id):
        if not self.user_id:
            return {"ok": False, "error": "請先登入"}
        data = {"user_id": self.user_id, "room_id": room_id}
        return await self._req("Room", "join", data)

    async def leave_room(self):
        if not self.user_id:
            return {"ok": False, "error": "請先登入"}
        data = {"user_id": self.user_id}
        return await self._req("Room", "leave", data)

    # -------------------------------
    # 邀請相關
    # -------------------------------
    async def list_invites(self):
        if not self.user_id:
            return {"ok": False, "error": "請先登入"}
        return await self._req("Invite", "list", {"user_id": self.user_id})
