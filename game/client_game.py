import pygame, asyncio, time
from common.network import send_msg, recv_msg
from game.game_server import SHAPES


WIDTH, HEIGHT = 900, 640
CELL = 24
MARGIN = 20

HOST, PORT = "127.0.0.1", 9100



class NetClient:
    def __init__(self):
        self.reader = None
        self.writer = None
        self.player_id = None
        self.state = {"me":None, "op":None, "time_left":0.0}
        self.running = True

    async def connect(self, host, port, name="Player"):
        self.reader, self.writer = await asyncio.open_connection(host, port)
        # welcome
        w = await recv_msg(self.reader)
        self.player_id = w["player_id"]
        await send_msg(self.writer, {"type":"hello","name": name})
        # 等 start
        while True:
            m = await recv_msg(self.reader)
            if m["type"] == "start":
                self.start_info = m
                break
        # 啟動收訊息
        asyncio.create_task(self._reader_loop())

    async def _reader_loop(self):
        while self.running:
            m = await recv_msg(self.reader)
            if not m: break
            t = m["type"]
            if t == "snapshot":
                self._update_snapshot(m)
            elif t == "game_over":
                print("GAME OVER:", m)
                self.running = False

    def _update_snapshot(self, snap):
        me_id = self.player_id
        p1, p2 = snap["players"]
        a = p1 if p1["id"] == me_id else p2
        b = p2 if p1["id"] == me_id else p1
        self.state["me"] = a
        self.state["op"] = b
        self.state["time_left"] = snap.get("time_left", 0.0)

    async def send_input(self, ev:str):
        now_ms = int(time.time()*1000)
        await send_msg(self.writer, {"type":"input","when_ms":now_ms,"ev":ev})

# --- Pygame ---

def draw_board(screen, board, ox, oy, color=(200,200,200)):
    # board: 20x10, 值=0/1（你可以改成顏色或方塊代號）
    for r in range(20):
        for c in range(10):
            v = board[r][c]
            rect = pygame.Rect(ox+c*CELL, oy+r*CELL, CELL-1, CELL-1)
            pygame.draw.rect(screen, (50,50,50), rect, 0)
            if v:
                pygame.draw.rect(screen, color, rect, 0)

def draw_active(screen, active, ox, oy, color=(80,180,255)):
    if not active: return
    kind = active["kind"]
    rot = active["rot"]
    x, y = active["x"], active["y"]
    shape = SHAPES[kind][rot]
    for (a,b) in shape:
        rect = pygame.Rect(ox + (x+a)*CELL, oy + (y+b)*CELL, CELL-1, CELL-1)
        pygame.draw.rect(screen, color, rect)



async def game_main():
    net = NetClient()
    await net.connect(HOST, PORT, name="Me")

    pygame.init()
    pygame.key.set_repeat(150, 50)
    
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Tetris (No Attack)")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont(None, 28)

    while net.running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                net.running = False

            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_LEFT:
                    await net.send_input("L")
                elif e.key == pygame.K_RIGHT:
                    await net.send_input("R")
                elif e.key == pygame.K_UP:
                    await net.send_input("CW")
                elif e.key == pygame.K_z:
                    await net.send_input("CCW")
                elif e.key == pygame.K_DOWN:
                    await net.send_input("SD")
                elif e.key == pygame.K_SPACE:
                    await net.send_input("HD")
                elif e.key == pygame.K_c:
                    await net.send_input("HOLD")

        screen.fill((22,22,24))

        me = net.state["me"]
        op = net.state["op"]

        # 左：自己；右：對手
        ox_me, oy = MARGIN, MARGIN
        ox_op = WIDTH//2 + MARGIN

        if me:
            draw_board(screen, me["board"], ox_me, oy, (200,200,100))
            draw_active(screen, me["active"], ox_me, oy, (255,240,120))
            txt = font.render(f"Me  score:{me['score']}  lines:{me['lines']}", True, (230,230,230))
            screen.blit(txt, (ox_me, oy+20*CELL+10))

        if op:
            draw_board(screen, op["board"], ox_op, oy, (120,180,220))
            draw_active(screen, op["active"], ox_op, oy, (150,210,255))
            txt = font.render(f"Rival  score:{op['score']}  lines:{op['lines']}", True, (230,230,230))
            screen.blit(txt, (ox_op, oy+20*CELL+10))

        # 時間
        tl = net.state["time_left"]
        if tl is not None:
            ttxt = font.render(f"Time left: {tl:.1f}s", True, (230,230,230))
            screen.blit(ttxt, (WIDTH//2 - 60, 10))

        pygame.display.flip()
        clock.tick(60)
        await asyncio.sleep(0)  # 不阻塞 loop

    pygame.quit()

if __name__ == "__main__":
    asyncio.run(game_main())
