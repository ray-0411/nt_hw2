import asyncio, time
from collections import deque, defaultdict
from typing import Dict, Any
from common.network import send_msg, recv_msg  # 你現成的
import sys
import socket
import json

def get_host_ip():
    """自動偵測這台機器對外可連線的 IP"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))   # 不會真的傳資料，只是拿來問 OS 用哪張網卡出網
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


HOST = get_host_ip()
PORT = 16800
LOBBY_PORT = 14110
ROOM_ID = None

if len(sys.argv) > 1:
    try:
        PORT = int(sys.argv[1])
    except ValueError:
        print("⚠️ 無效的 port 參數，使用預設值 10010")
if len(sys.argv) > 2:
    ROOM_ID = int(sys.argv[2])


TPS = 30                         # 模擬頻率（ticks per second）
SNAPSHOT_INTERVAL_MS = 100
MATCH_SEC = None                   # 計時賽 60s
GRAVITY_DROP_MS = 800            # 重力（固定）

from game.bag import seven_bag_stream

# --- 簡化：方塊旋轉與碰撞、鎖定、消行的細節請逐步補完 ---
# 我先留 TODO，先跑起「流程＋同步」；你可把既有 Tetris 邏輯移入。

SHAPES = {
    "I": [
        [(0,0),(1,0),(2,0),(3,0)],
        [(2,-1),(2,0),(2,1),(2,2)],
        [(0,1),(1,1),(2,1),(3,1)],
        [(1,-1),(1,0),(1,1),(1,2)]
    ],
    "O": [
        [(0,0),(1,0),(0,1),(1,1)]
    ],
    "T": [
        [(1,0),(0,1),(1,1),(2,1)],
        [(1,0),(1,1),(2,1),(1,2)],
        [(0,1),(1,1),(2,1),(1,2)],
        [(1,0),(0,1),(1,1),(1,2)]
    ],
    "L": [
        [(0,0),(0,1),(0,2),(1,2)],
        [(0,1),(1,1),(2,1),(0,2)],
        [(0,0),(1,0),(1,1),(1,2)],
        [(2,0),(0,1),(1,1),(2,1)]
    ],
    "J": [
        [(1,0),(1,1),(1,2),(0,2)],
        [(0,0),(0,1),(1,1),(2,1)],
        [(0,0),(1,0),(0,1),(0,2)],
        [(0,1),(1,1),(2,1),(2,2)]
    ],
    "S": [
        [(1,0),(2,0),(0,1),(1,1)],
        [(1,0),(1,1),(2,1),(2,2)],
        [(1,1),(2,1),(0,2),(1,2)],
        [(0,0),(0,1),(1,1),(1,2)]
    ],
    "Z": [
        [(0,0),(1,0),(1,1),(2,1)],
        [(2,0),(1,1),(2,1),(1,2)],
        [(0,1),(1,1),(1,2),(2,2)],
        [(1,0),(0,1),(1,1),(0,2)]
    ]
}

class Player:
    def __init__(self, pid:int, writer:asyncio.StreamWriter, name:str):
        self.id = pid
        self.writer = writer
        self.name = name
        self.input_q = deque()
        self.board = [[0]*10 for _ in range(20)]
        self.active = None     # dict: {"kind","x","y","rot"}
        self.hold = None
        self.can_hold = True
        self.score = 0
        self.lines = 0
        self.alive = True
        self.next_queue = deque()
        self.level = 0
        self.lines_cleared_total = 0
        self.user_id = None 

    def enqueue_input(self, ev:str, when_ms:int):
        self.input_q.append((when_ms, ev))

class Game:
    def __init__(self):
        self.players: Dict[int, Player,int] = {}
        self.watchers: Dict[str, asyncio.StreamWriter] = {}
        
        self.start_monotonic = None
        self.t0_server_ms = None
        self.finish = False
        self.seed = int(time.time()*1000) & 0xFFFFFFFF
        self.bag = seven_bag_stream(self.seed)
        self.last_snapshot_ms = 0
        self.gravity_ms = GRAVITY_DROP_MS
        self.mode = {"mode": "endless", "seconds": None}
        


    def add_player(self, pid:int, p:Player):
        self.players[pid] = p
        # 預先補足 next_queue
        while len(p.next_queue) < 8:
            p.next_queue.append(next(self.bag))

    # ---- 這裡是方塊/碰撞/鎖定/消行的 TODO 位置 ---- #
    def ensure_active(self, p:Player):
        if p.active is None:
            kind = p.next_queue.popleft()
            while len(p.next_queue) < 8:
                p.next_queue.append(next(self.bag))
            # 置中出生
            p.active = {"kind": kind, "x": 3, "y": 0, "rot": 0}
            # TODO: 若一出生就碰撞 ⇒ top out
            # p.alive = False

    def apply_input(self, p:Player, ev:str):
        if not p.alive or not p.active:
            return

        kind = p.active["kind"]
        rot = p.active["rot"]
        x, y = p.active["x"], p.active["y"]

        # 目前方塊形狀
        shape = SHAPES[kind][rot]

        if ev == "L":
            if not self.collide(p.board, shape, x-1, y):
                p.active["x"] -= 1
        elif ev == "R":
            if not self.collide(p.board, shape, x+1, y):
                p.active["x"] += 1
        elif ev == "SD":  # Soft Drop
            if not self.collide(p.board, shape, x, y+1):
                p.active["y"] += 1
                p.score += 1
            else:
                self.lock_piece(p, [(a+x,b+y) for (a,b) in shape])
                p.active = None
        elif ev == "CW":  # 順時針旋轉
            new_rot = (rot + 1) % len(SHAPES[kind])
            new_shape = SHAPES[kind][new_rot]
            if not self.collide(p.board, new_shape, x, y):
                p.active["rot"] = new_rot
        elif ev == "CCW":  # 逆時針旋轉
            new_rot = (rot - 1) % len(SHAPES[kind])
            new_shape = SHAPES[kind][new_rot]
            if not self.collide(p.board, new_shape, x, y):
                p.active["rot"] = new_rot
        
        elif ev == "HD":  # 🟩 Hard Drop（空白鍵）
            drop = 0
            while not self.collide(p.board, shape, x, y+1):
                y += 1
                drop += 1
            p.active["y"] = y
            # 鎖定到底部
            self.lock_piece(p, [(a+x,b+y) for (a,b) in shape])
            p.active = None
            p.score += drop * 2   # 每下降一格 +2 分
        
        elif ev == "HOLD":  # 🟦 暫存方塊
            if not p.can_hold or not p.active:
                return  # 已經用過 Hold 或沒方塊可暫存

            cur_kind = p.active["kind"]

            if p.hold is None:
                # 第一次 Hold：暫存目前方塊，生成新方塊
                p.hold = cur_kind
                p.active = None
                self.ensure_active(p)
            else:
                # 已經有暫存方塊：交換
                temp = p.hold
                p.hold = cur_kind
                p.active = {"kind": temp, "x": 3, "y": 0, "rot": 0}

            p.can_hold = False  # 一顆方塊只能 Hold 一次
        
        


    def gravity_step(self, p: Player):
        if not p.alive:
            return

        self.ensure_active(p)
        kind = p.active["kind"]
        rot = p.active["rot"]
        x, y = p.active["x"], p.active["y"]
        shape = SHAPES[kind][rot]

        if not self.collide(p.board, shape, x, y+1):
            p.active["y"] += 1
        else:
            self.lock_piece(p, [(a+x,b+y) for (a,b) in shape])
            p.active = None

    
    def collide(self, board, shape, ox, oy):
        """檢查形狀是否與邊界或已放方塊碰撞"""
        for (x, y) in shape:
            nx, ny = x + ox, y + oy
            if nx < 0 or nx >= 10 or ny < 0 or ny >= 20:
                return True
            if board[ny][nx]:
                return True
        return False

    def lock_piece(self, p, shape):
        for (x, y) in shape:
            if y < 0:
                p.alive = False
                return
            p.board[y][x] = p.active["kind"]

        # 🟩 消行
        full = [i for i,row in enumerate(p.board) if all(row)]
        lines = len(full)

        if lines > 0:
            for i in full:
                del p.board[i]
                p.board.insert(0, [0]*10)

            # 累積總消行
            p.lines_cleared_total += lines
            p.lines += lines

            # Level 提升：每滿 10 行升 1 等
            new_level = p.lines_cleared_total // 10
            if new_level > p.level:
                p.level = new_level
                print(f"⬆️ Player {p.id} level up to {p.level}")

            # 分數表 (NES 規則)
            score_table = {1: 40, 2: 100, 3: 300, 4: 1200}
            base = score_table.get(lines, 0)
            p.score += base * (p.level + 1)

        # 如果最上面一行有方塊 → 死亡
        if any(p.board[0]):
            p.alive = False

        p.can_hold = True


    def snapshot(self) -> Dict[str,Any]:
        players_view=[]
        for pid in (1,2):
            p = self.players.get(pid)
            players_view.append({
                "id": pid,
                "board": p.board,
                "active": p.active,
                "next": list(p.next_queue)[:5],
                "hold": p.hold,
                "can_hold": p.can_hold,
                "score": p.score,
                "level": p.level,
                "lines": p.lines,
                "alive": p.alive
            })
        now_ms = int(time.time()*1000)
        return {"type": "snapshot", "server_ms": now_ms, "players": players_view}


async def handle_player(reader:asyncio.StreamReader, writer:asyncio.StreamWriter, game:Game, pid:int):
    # welcome
    await send_msg(writer, {"type":"welcome","player_id": pid})

    # hello
    msg = await recv_msg(reader)
    
    if msg and msg.get("type") == "hello":
        name = msg.get("name", f"P{pid}")
        user_id = msg.get("user_id")   # ✅ 建議用 user_id 比 player_id 一致
    else:
        name = f"P{pid}"
        user_id = None
    
    p = Player(pid, writer, name)
    p.user_id = user_id
    game.add_player(pid, p)
    print(f"✅ Player{pid} connected: {name}")

    # 等待開局之後，常駐讀取輸入
    try:
        while not game.finish:
            m = await recv_msg(reader)
            if not m: break
            t = m.get("type")
            if t == "input":
                p.enqueue_input(m.get("ev"), int(m.get("when_ms", 0)))
            # 其他類型（ping等）可擴充
    except Exception as e:
        print(f"⚠️ player {pid} error: {e}")
    finally:
        p.alive = False

async def handle_watcher(reader, writer, game, wid):
    """觀戰者獨立處理，不干擾主程式"""
    await send_msg(writer, {"type": "welcome", "id": wid})
    print(f"👀 Watcher {wid} 已啟動")

    try:
        # 觀戰者只接收，不回傳
        while not game.finish:
            await asyncio.sleep(1)  # 保持 loop 活著
    except Exception as e:
        print(f"⚠️ 觀戰者 {wid} 發生錯誤: {e}")
    finally:
        if wid in game.watchers:
            del game.watchers[wid]
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass
        print(f"👋 Watcher {wid} 離開")





async def game_loop(game:Game):
    # 開場廣播 start（延遲 1 秒對齊）
    game.t0_server_ms = int(time.time()*1000) + 1000
    start_payload = {
        "type":"start",
        "seed": game.seed,
        "bagRule": "7bag",
        "gravity": {"dropIntervalMs": game.gravity_ms},
        "match": game.mode,
        "t0_server_ms": game.t0_server_ms
    }
    for p in game.players.values():
        await send_msg(p.writer, start_payload)

    # 等待 t0
    await asyncio.sleep(max(0, (game.t0_server_ms - int(time.time()*1000))/1000.0))
    game.start_monotonic = time.monotonic()
    print("🎬 Game started!")

    tick_dt = 1.0/TPS
    last_gravity_ms = defaultdict(lambda: 0)

    while not game.finish:
        now_ms = int(time.time()*1000)

        # 1) 處理輸入
        for p in game.players.values():
            while p.input_q:
                _, ev = p.input_q.popleft()
                game.apply_input(p, ev)

        # 2) 重力（獨立對每位玩家）
        level_speed_table = {
            0: 800, 1: 717, 2: 633, 3: 550, 4: 467, 5: 383, 6: 300, 7: 217,
            8: 133, 9: 100, 10: 83, 11: 83, 12: 83, 13: 67, 14: 67, 15: 67,
            16: 50, 17: 50, 18: 50, 19: 33, 20: 33, 29: 17
        }

        for p in game.players.values():
            # 找對應等級的掉落間隔（預設最快 17ms）
            lv = min(p.level, 29)
            drop_ms = level_speed_table.get(lv, 17)

            if now_ms - last_gravity_ms[p.id] >= drop_ms:
                game.gravity_step(p)
                last_gravity_ms[p.id] = now_ms

        # 3) 廣播 snapshot（每 100ms 一次）
        if now_ms - game.last_snapshot_ms >= SNAPSHOT_INTERVAL_MS:
            snap = game.snapshot()
            
            
            for p in game.players.values():
                await send_msg(p.writer, snap)
                
            if hasattr(game, "watchers"):
                for wid, w in list(game.watchers.items()):
                    async def send_to_watcher(wid, w):
                        try:
                            await send_msg(w, snap)
                        except Exception as e:
                            print(f"⚠️ 傳送 snapshot 給觀戰者 {wid} 失敗：{e}")
                            if wid in game.watchers:
                                del game.watchers[wid]
                    # 👇 不 await，直接啟動任務
                    asyncio.create_task(send_to_watcher(wid, w))
                        
                        
                        
            game.last_snapshot_ms = now_ms

        # 4) 檢查結束條件
        alive_players = [p for p in game.players.values() if p.alive]
        all_dead = len(alive_players) == 0
        

        if all_dead:
            game.finish = True
            break

        await asyncio.sleep(tick_dt)

    # ===== 遊戲結算 =====
    print("🏁 Game over, computing result...")

    p1, p2 = game.players.values()
    reason = "both_dead"

    winner_user_id = None
    # 🏆 比較分數
    if p1.score > p2.score:
        winner = p1.id
        winner_user_id = p1.user_id
    elif p2.score > p1.score:
        winner = p2.id
        winner_user_id = p2.user_id
    else:
        winner = None  # 平手

    result = {
        f"p{pid}": {
            "user_id": getattr(p, "user_id", None),
            "score": p.score,
            "level": p.level,
            "lines": p.lines,
        }
        for pid, p in game.players.items()
    }

    msg = {
        "type": "game_over",
        "reason": reason,
        "winner": winner,
        "winner_user_id": winner_user_id,
        "result": result,
    }

    

    for p in game.players.values():
        await send_msg(p.writer, msg)
        
    if hasattr(game, "watchers") and game.watchers:
        for wid, w in list(game.watchers.items()):
            try:
                await send_msg(w, msg)
            except Exception as e:
                print(f"⚠️ 傳送 game_over 給觀戰者 {wid} 失敗：{e}")
                if wid in game.watchers:
                    del game.watchers[wid]
    

    print(f"🏁 Game over ({reason}), winner={winner}")
    
    payload = {
        "collection": "Game",
        "action": "report",
        "data": {
            "room_id": ROOM_ID,
            "winner": winner_user_id,
            "result": result
        }
    }

    try:
        # 用最基礎 TCP 傳送 JSON（Length-prefixed framing）
        with socket.create_connection((HOST, LOBBY_PORT), timeout=5) as s:
            data = json.dumps(payload).encode("utf-8")
            s.sendall(len(data).to_bytes(4, "big") + data)
            print("📤 已回報比賽結果給 Lobby Server")
    except Exception as e:
        print(f"⚠️ 回報 Lobby 失敗：{e}")
    
    

async def main():
    game = Game()
    # 等兩位玩家
    print(f"🎮 Game server on {HOST}:{PORT}, waiting players...")

    waiting = []
    
    accept_lock = asyncio.Lock()

    async def accept(reader, writer):
        nonlocal waiting, game, accept_lock
        
        if len(game.players) >= 2:
            watcher_id = f"W{len(game.watchers)+1}"
            game.watchers[watcher_id] = writer
            print(f"👀 Watcher connected: {watcher_id}")
            # 🔸 啟動獨立 watcher task，不 await！
            asyncio.create_task(handle_watcher(reader, writer, game, watcher_id))
            return

        async with accept_lock:  # 🔒 保證同時間只會進入一次

            pid = 1 if 1 not in game.players else 2
            task = asyncio.create_task(handle_player(reader, writer, game, pid))
            waiting.append(task)

            # 等 handle_player() 加入
            await asyncio.sleep(0.2)

            if len(game.players) == 2 and not getattr(game, "_started", False):
                game._started = True
                asyncio.create_task(game_loop(game))


    server = await asyncio.start_server(accept, HOST, PORT)
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
