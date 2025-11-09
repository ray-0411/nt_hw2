import asyncio, time
from collections import deque, defaultdict
from typing import Dict, Any
from common.network import send_msg, recv_msg  # 你現成的

HOST, PORT = "0.0.0.0", 9100
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

    def enqueue_input(self, ev:str, when_ms:int):
        self.input_q.append((when_ms, ev))

class Game:
    def __init__(self):
        self.players: Dict[int, Player] = {}
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
            p.board[y][x] = 1

        # 🟩 消行
        full = [i for i,row in enumerate(p.board) if all(row)]
        for i in full:
            del p.board[i]
            p.board.insert(0, [0]*10)
        lines = len(full)
        p.lines += lines
        p.score += lines * 100

        # 🟩 如果最上面一行有方塊 → Game Over
        if any(p.board[0]):
            p.alive = False

        # 🟩 方塊鎖定後允許再次 Hold
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
    name = msg.get("name","P"+str(pid)) if msg and msg.get("type")=="hello" else f"P{pid}"
    p = Player(pid, writer, name)
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
        for p in game.players.values():
            if now_ms - last_gravity_ms[p.id] >= game.gravity_ms:
                game.gravity_step(p)
                last_gravity_ms[p.id] = now_ms

        # 3) 廣播 snapshot（每 100ms 一次）
        if now_ms - game.last_snapshot_ms >= SNAPSHOT_INTERVAL_MS:
            snap = game.snapshot()
            for p in game.players.values():
                await send_msg(p.writer, snap)
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

    # 🏆 比較分數
    if p1.score > p2.score:
        winner = p1.id
    elif p2.score > p1.score:
        winner = p2.id
    else:
        winner = None  # 平手

    result = {
        f"p{pid}": {"score": p.score, "lines": p.lines, "alive": p.alive}
        for pid, p in game.players.items()
    }

    msg = {
        "type": "game_over",
        "reason": reason,
        "winner": winner,
        "result": result,
    }

    for p in game.players.values():
        await send_msg(p.writer, msg)

    print(f"🏁 Game over ({reason}), winner={winner}")

async def main():
    game = Game()
    # 等兩位玩家
    print(f"🎮 Game server on {HOST}:{PORT}, waiting players...")

    waiting = []

    async def accept(reader, writer):
        nonlocal waiting, game
        if len(game.players) >= 2:
            await send_msg(writer, {"type":"full"})
            writer.close(); await writer.wait_closed()
            return
        pid = 1 if 1 not in game.players else 2
        task = asyncio.create_task(handle_player(reader, writer, game, pid))
        waiting.append(task)

        # 🟩 這裡改成等待 players 加入完畢後再檢查
        await asyncio.sleep(0.5)   # 給 handle_player() 時間加進 game.players

        if len(game.players) == 2 and not getattr(game, "_started", False):
            game._started = True
            asyncio.create_task(game_loop(game))


    server = await asyncio.start_server(accept, HOST, PORT)
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
