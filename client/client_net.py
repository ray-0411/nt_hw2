import asyncio
from common.network import send_msg, recv_msg


# 🟩 你自己的候選 Lobby IP 列表
LOBBY_CANDIDATES = [
    "127.0.0.1",        # 本機測試用
    "140.113.xx.xx",    # 學校伺服器 IP（替換成真實值）
    "192.168.0.10"      # 宿舍或 VPN 環境 IP（可選）
]

LOBBY_PORT = 14110

async def connect_to_lobby():
    """嘗試依序連接多個 Lobby IP，直到成功"""
    for host in LOBBY_CANDIDATES:
        try:
            reader, writer = await asyncio.open_connection(host, LOBBY_PORT)
            print(f"✅ 已連線到 Lobby Server：{host}:{LOBBY_PORT}")
            return reader, writer
        except Exception as e:
            print(f"⚠️ 無法連線 {host}:{LOBBY_PORT} ({e})")
    raise ConnectionError("❌ 所有候選 Lobby IP 都無法連線！")


class LobbyClient:
    """封裝與 Lobby Server 的所有通訊邏輯"""

    def __init__(self, hosts=None, port=14110):
        self.hosts = hosts or [
            "140.113.66.30",   # my ip 
            "140.113.17.11",   # school ip
        ]
        
        self.host = self.hosts[0]  # 預設使用第一個 host
        self.port = port
        self.reader = None
        self.writer = None
        self.user_id = None
        self.username = None
        self.lock = asyncio.Lock()

    async def connect(self):
        """嘗試多個 IP，直到成功連線到 Lobby"""
        for host in self.hosts:
            try:
                print(f"🔍 嘗試連線 Lobby：{host}:{self.port} ...")
                self.reader, self.writer = await asyncio.open_connection(host, self.port)
                self.host = host
                print(f"✅ 已連線到 Lobby Server：{host}:{self.port}")
                return True
            except Exception as e:
                print(f"⚠️ 無法連線 {host}:{self.port} ({e})")
        print("❌ 所有候選 IP 都無法連線！")
        return False


    async def close(self):
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

    # -------------------------------
    # 封裝請求/回應機制
    # -------------------------------
    async def _req(self, collection, action, data=None):
        req = {"collection": collection, "action": action, "data": data or {}}
        async with self.lock:  # ✅ 同步鎖
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
    async def list_rooms(self, only_available="space"):
        data = {"only_available": only_available}
        return await self._req("Room", "list", data)

    async def create_room(self, name, visibility="public", password=None):
        if not self.user_id:
            return {"ok": False, "error": "請先登入"}
        
        data = {"name": name, 
                "host_user_id": self.user_id, 
                "visibility": visibility}
        if password:
            data["password"] = password
        
        return await self._req("Room", "create", data)
    
    async def close_room(self, room_id):
        """關閉自己建立的房間"""
        data = {"room_id": room_id, "host_user_id": self.user_id}
        return await self._req("Room", "close", data)
    
    async def join_room(self, room_id, password=None):
        """加入指定房間"""
        if not self.user_id:
            return {"ok": False, "error": "請先登入"}

        data = {
            "room_id": room_id,
            "user_id": self.user_id,
            "password": password
        }

        return await self._req("Room", "join", data)

    async def leave_room(self, room_id):
        """離開當前房間"""
        if not self.user_id:
            return {"ok": False, "error": "請先登入"}

        data = {"room_id": room_id, "user_id": self.user_id}
        return await self._req("Room", "leave", data)
    # -------------------------------
    # 邀請相關
    # -------------------------------
    
    async def send_invite(self, target_user_id, room_id):
        """發送邀請給其他玩家"""
        if not self.user_id:
            return {"ok": False, "error": "請先登入"}

        # 準備邀請資料
        data = {
            "inviter_id": self.user_id,   # 發送者
            "invitee_id": target_user_id, # 接收者
            "room_id": room_id
        }

        # 傳送請求給 Lobby Server
        resp = await self._req("Invite", "create", data)

        # 回傳伺服器回應
        return resp

    async def list_invites(self):
        """查詢自己收到的邀請"""
        if not self.user_id:
            return {"ok": False, "error": "請先登入"}

        data = {"user_id": self.user_id}
        return await self._req("Invite", "list", data)

    async def respond_invite(self, invite_id, accept=True):
        """回應邀請（accept=True 同意，False 拒絕）"""
        if not self.user_id:
            return {"ok": False, "error": "請先登入"}

        data = {
            "invitee_id": self.user_id,   # 自己（被邀請者）
            "invite_id": invite_id,       # 要處理的邀請編號
            "accept": accept              # True 同意, False 拒絕
        }

        return await self._req("Invite", "respond", data)