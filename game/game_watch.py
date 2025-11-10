import asyncio
import pygame
import sys
from common.network import send_msg, recv_msg

WIDTH, HEIGHT = 800, 600
CELL = 24

# 🎨 顏色表（可與玩家端相同）
COLOR_TABLE = {
    "I": (0, 200, 200),     # Cyan → 稍灰
    "O": (230, 230, 90),    # Yellow → 柔和
    "T": (150, 80, 190),    # Purple → 淡一點
    "S": (80, 200, 80),     # Green → 不那麼亮
    "Z": (200, 80, 80),     # Red → 減亮度
    "J": (80, 100, 200),    # Blue → 柔藍
    "L": (220, 150, 60)     # Orange → 暖但不刺眼
}

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


def draw_board(screen, board, ox, oy, cell_size=CELL, color=None):
    """畫出整個棋盤（背景格子 + 方塊 + 外框）"""

    # --- 1️⃣ 背景底格 ---
    for r in range(20):
        for c in range(10):
            base_color = (40, 40, 40) if (r + c) % 2 == 0 else (45, 45, 45)
            rect = pygame.Rect(
                ox + c * cell_size,
                oy + r * cell_size,
                cell_size - 1,
                cell_size - 1
            )
            pygame.draw.rect(screen, base_color, rect)

    # --- 2️⃣ 方塊 ---
    for r in range(20):
        for c in range(10):
            v = board[r][c]
            if not v:
                continue
            col = color or COLOR_TABLE.get(v, (200, 200, 200))
            rect = pygame.Rect(
                ox + c * cell_size,
                oy + r * cell_size,
                cell_size - 1,
                cell_size - 1
            )
            pygame.draw.rect(screen, col, rect)

    # --- 3️⃣ 外框 ---
    pygame.draw.rect(
        screen,
        (200, 200, 200),
        (ox - 2, oy - 2, 10 * cell_size + 4, 20 * cell_size + 4),
        2
    )

async def watch_main(host, port):
    print(f"👀 觀戰模式啟動，連線至 {host}:{port}")

    reader, writer = await asyncio.open_connection(host, port)
    await send_msg(writer, {"type": "hello", "name": "Watcher"})

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Tetris - Watch Mode")
    clock = pygame.time.Clock()

    snapshot = None
    running = True

    async def recv_loop():
        nonlocal snapshot, running
        while running:
            try:
                #print("⏳ 等待接收 snapshot...")
                msg = await recv_msg(reader)
            except Exception as e:
                #print(f"⚠️ 讀取 snapshot 錯誤：{e}")
                break
            if not msg:
                #print("⚠️ 伺服器斷線")
                break
            if msg["type"] == "snapshot":
                snapshot = msg
                #print(f"📸 收到 snapshot，包含玩家數：{len(snapshot.get('players', []))}")
            elif msg["type"] == "game_over":
                print("🏁 遊戲結束！")
                running = False

    asyncio.create_task(recv_loop())

    while running:
        await asyncio.sleep(0)
        
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False

        screen.fill((10, 10, 15))

        if snapshot:
            players = snapshot.get("players", [])
            if len(players) >= 2:
                p1, p2 = players[0], players[1]
                draw_board(screen, p1["board"], 100, 80)
                draw_board(screen, p2["board"], 400, 80)
                
                # 🟩 繪製正在掉落的方塊
                for idx, (p, ox) in enumerate([(p1, 100), (p2, 400)], start=1):
                    active = p.get("active")
                    if not active:
                        continue
                    kind = active.get("kind")
                    x, y, rot = active.get("x", 0), active.get("y", 0), active.get("rot", 0)
                    shape = SHAPES.get(kind)
                    if not shape:
                        continue
                    for dx, dy in shape[rot % len(shape)]:
                        rect = pygame.Rect(
                            ox + (x + dx) * CELL,
                            80 + (y + dy) * CELL,
                            CELL - 1,
                            CELL - 1
                        )
                        pygame.draw.rect(screen, COLOR_TABLE.get(kind, (255,255,255)), rect)
                        

                font = pygame.font.SysFont("Microsoft JhengHei", 24)
                text1 = font.render(f"{p1['id']} 分數:{p1['score']} LV:{p1['level']}", True, (230,230,230))
                text2 = font.render(f"{p2['id']} 分數:{p2['score']} LV:{p2['level']}", True, (230,230,230))
                screen.blit(text1, (100, 40))
                screen.blit(text2, (400, 40))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
    print("👋 離開觀戰模式")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python -m game.game_watch <host> <port>")
        sys.exit(1)
    host = sys.argv[1]
    port = int(sys.argv[2])
    asyncio.run(watch_main(host, port))
