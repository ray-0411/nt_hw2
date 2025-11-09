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
        
        self.hold = None
        self.can_hold = True


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
                self.result = m
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

def draw_hold(screen, hold_kind, ox, oy, cell=12):
    """畫出暫存方塊 (縮小版)"""
    font_small = pygame.font.SysFont(None, 18)
    pygame.draw.rect(screen, (80, 80, 90), (ox-5, oy-5, 6*cell, 6*cell), 2, border_radius=6)
    label = font_small.render("HOLD", True, (230, 230, 230))
    screen.blit(label, (ox, oy - 20))

    if not hold_kind:
        return

    shape = SHAPES[hold_kind][0]  # 顯示第一個旋轉狀態即可
    color = (100, 200, 255)       # 暫存顏色
    for (x, y) in shape:
        rect = pygame.Rect(ox + (x+1)*cell, oy + (y+1)*cell, cell-1, cell-1)
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

        # === 座標設定 ===
        BOARD_W = 10 * CELL
        BOARD_H = 20 * CELL

        CELL_OP = int(CELL * 0.6)
        BOARD_W_OP = 10 * CELL_OP
        BOARD_H_OP = 20 * CELL_OP

        # 🔹 將整體往右移 100px
        OFFSET_X = 100

        ox_me = 100 + OFFSET_X                 # 自己棋盤位置
        oy_me = (HEIGHT - BOARD_H) // 2 - 20

        ox_op = ox_me + BOARD_W + 180          # 對手棋盤位置（靠右上）
        oy_op = oy_me

        # --- 對手棋盤（含 active 掉落方塊） ---
        if op:
            # 棋盤
            for r in range(20):
                for c in range(10):
                    v = op["board"][r][c]
                    rect = pygame.Rect(ox_op + c * CELL_OP, oy_op + r * CELL_OP, CELL_OP - 1, CELL_OP - 1)
                    pygame.draw.rect(screen, (40, 40, 50), rect, 0)
                    if v:
                        pygame.draw.rect(screen, (120, 180, 220), rect, 0)

            # 掉落方塊 (active)
            if op["active"]:
                kind = op["active"]["kind"]
                rot = op["active"]["rot"]
                x, y = op["active"]["x"], op["active"]["y"]
                shape = SHAPES[kind][rot]
                for (a, b) in shape:
                    rect = pygame.Rect(ox_op + (x + a) * CELL_OP, oy_op + (y + b) * CELL_OP, CELL_OP - 1, CELL_OP - 1)
                    pygame.draw.rect(screen, (150, 210, 255), rect)

            # 外框
            pygame.draw.rect(screen, (180,180,180),
                            (ox_op-2, oy_op-2, BOARD_W_OP+4, BOARD_H_OP+4), 2)

        # --- 自己棋盤（左側主要畫面） ---
        if me:
            if me["alive"]:
                draw_board(screen, me["board"], ox_me, oy_me, (200,200,100))
                draw_active(screen, me["active"], ox_me, oy_me, (255,240,120))
            else:
                draw_board(screen, me["board"], ox_me, oy_me, (100,100,100))
                font_dead = pygame.font.SysFont("Microsoft JhengHei", 40)
                txt_dead = font_dead.render("你已死亡", True, (255,120,120))
                screen.blit(txt_dead, (
                    ox_me + (BOARD_W // 2 - txt_dead.get_width() // 2),
                    oy_me + (BOARD_H // 2 - txt_dead.get_height() // 2)
                ))
        
        # --- HOLD 區塊 ---
            cell_hold = int(CELL_OP * 1.2)
            hold_x = ox_op
            hold_y = oy_op + BOARD_H_OP + 30
            draw_hold(screen, me.get("hold"), hold_x, hold_y, cell=cell_hold)

            # --- 分數與等級（在 HOLD 下方） ---
            font_info = pygame.font.SysFont("Microsoft JhengHei", 28)
            info_y = hold_y + 6 * cell_hold + 12
            text_sc = font_info.render(f"分數：{me['score']}", True, (230,230,230))
            text_lv = font_info.render(f"等級：{me.get('level', 0)}", True, (230,230,230))
            screen.blit(text_sc, (hold_x, info_y))
            screen.blit(text_lv, (hold_x, info_y + 30))

        pygame.display.flip()
        clock.tick(60)
        await asyncio.sleep(0)  # 不阻塞 loop

    
    # --- 顯示結束畫面（雙方都死 / 時間到） ---
    if hasattr(net, "result"):
        result = net.result
        reason = result.get("reason", "timeup")
        winner = result.get("winner")

        screen.fill((0, 0, 0))
        # ✅ 使用支援中文的字型（不含 emoji）
        font_big = pygame.font.SysFont("Microsoft JhengHei", 48)
        font_small = pygame.font.SysFont("Microsoft JhengHei", 32)

        # 標題
        title_txt = f"遊戲結束（原因：{reason}）"
        text = font_big.render(title_txt, True, (255, 255, 255))
        screen.blit(text, (WIDTH // 2 - text.get_width() // 2, HEIGHT // 2 - 100))

        # 判定勝負
        if winner is None:
            msg = "平手"
        elif winner == net.player_id:
            msg = "你贏了！"
        else:
            msg = "你輸了！"

        text2 = font_big.render(msg, True, (255, 255, 120))
        screen.blit(text2, (WIDTH // 2 - text2.get_width() // 2, HEIGHT // 2))

        # 顯示分數
        r = result["result"]
        # 🟩 保險寫法：確保有 p1 / p2
        p1_score = r.get("p1", {}).get("score", 0)
        p2_score = r.get("p2", {}).get("score", 0)
        score_txt = f"分數：你 {p1_score}  vs  對手 {p2_score}"
        text3 = font_small.render(score_txt, True, (200, 200, 200))
        screen.blit(text3, (WIDTH // 2 - text3.get_width() // 2, HEIGHT // 2 + 80))

        pygame.display.flip()
        await asyncio.sleep(5)
    

    pygame.quit()
    

if __name__ == "__main__":
    asyncio.run(game_main())
