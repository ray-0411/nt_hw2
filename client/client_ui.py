import asyncio
from client.client_net import LobbyClient
import os
import time
import msvcrt
import subprocess



async def login_phase(client: LobbyClient):
    while True:
        #clear terminal screen
        clear_screen()
        
        print("\n=== 🧩 登入選單 ===")
        print("1. 註冊")
        print("2. 登入")
        print("0. 離開")
        cmd = input("請輸入指令：").strip()

        if cmd == "1":
            name = input("使用者名稱：")
            pw = input("密碼：")
            resp = await client.register(name, pw)
            
            if resp.get("ok"):
                # ✅ 顯示註冊成功訊息
                print(f"✅ 註冊成功！歡迎，{name}！")
                return True
            else:
                # get error message
                error_msg = resp.get("error", "未知錯誤，請稍後再試。")

                if "already exists" in error_msg:
                    print("⚠️ 此使用者名稱已被註冊，請換一個。")
                else:
                    print(f"❌ 註冊失敗：{error_msg}")
            time.sleep(1.5)
            

        elif cmd == "2":
            name = input("使用者名稱：")
            pw = input("密碼：")
            resp = await client.login(name, pw)
            #print("📥", resp)
            
            #login successful
            if resp.get("ok"):
                print(f"✅ 登入成功！歡迎，{resp.get('name', name)}！")
                time.sleep(1)
                return True
            
            #login failed
            else:
                # get error message
                error_msg = resp.get("error", "未知錯誤，請稍後再試。")

                # 依錯誤內容做不同提示
                if error_msg == "User not found.":
                    print("❌ 帳號不存在，請先註冊。")
                elif error_msg == "Invalid password.":
                    print("❌ 密碼錯誤，請再試一次。")
                elif error_msg == "User already logged in elsewhere.":
                    print("⚠️ 該帳號已在其他地方登入。")
                else:
                    print(f"❌ 登入失敗：{error_msg}")
            time.sleep(1.5)

        elif cmd == "0":
            return False
        else:
            print("❌ 請輸入0,1,2。")
        

async def lobby_phase(client: LobbyClient):
    while True:
        clear_screen()
        
        print(f"\n🎮 玩家：{client.username}")
        print("1. 顯示線上使用者")
        print("2. 顯示房間清單")
        print("3. 建立房間")
        print("4. 加入房間")
        print("5. 查看邀請")
        print("6. 登出")
        cmd = input("請輸入指令：").strip()

        if cmd == "1":
            clear_screen()
            
            resp = await client.list_online_users()
            users = resp.get("users", [])

            print("\n📋 線上使用者清單：")
            if not users:
                print("（目前沒有使用者在線上）")
            else:
                # 過濾掉自己
                others = [name for uid, name in users if uid != client.user_id]

                if not others:
                    print("（目前只有你在線上）")
                else:
                    for i, name in enumerate(others, start=1):
                        print(f"{i}. {name}")

            input("\n🔙 按下 Enter 鍵返回選單...")

        elif cmd == "2":
            clear_screen()
            
            resp = await client.list_rooms(only_available="space")
            rooms = resp.get("rooms", [])

            print("\n📋 可加入的房間清單：")
            if not rooms:
                print("（目前沒有可加入的房間）")
            else:
                # 逐筆列出
                for i, r in enumerate(rooms, start=1):
                    print(f"{i}. {r['name']}（房主：{r['host']}，類型：{r['visibility']}）")

            input("\n🔙 按下 Enter 鍵返回選單...")

        elif cmd == "3":
            finish = False
            
            while True:
                clear_screen()
                
                print("\n🏠 建立新房間(輸入0結束創房)")

                # 房間名稱
                name = input("請輸入房間名稱：").strip()
                if name == "0":
                    finish = True
                    break
                elif not name:
                    print("❌ 房間名稱不能為空！")
                    time.sleep(1)
                    continue
                else:
                    break
            
            if finish:
                continue

            # 房間可見性
            while True:
                clear_screen()
                print("\n🏠 建立新房間(輸入0結束創房)")
                print(f"房間名稱：{name}\n")
                
                visibility = input("請選擇房間類型（1=公開 / 2=私有）：").strip()
                if visibility == "1":
                    visibility = "public"
                    password = None
                    break
                elif visibility == "2":
                    visibility = "private"
                    password = input("請輸入房間密碼：").strip()
                    if not password:
                        print("❌ 密碼不能為空！")
                        time.sleep(1)
                        continue
                    break
                elif visibility == "0":
                    finish = True
                    break
                else:
                    print("⚠️ 請輸入 1 或 2。")
            
            if finish:
                continue
            
            # ✅ 建立房間
            resp = await client.create_room(name, visibility=visibility, password=password)

            # 顯示結果
            if resp.get("ok"):
                print(f"✅ 房間「{name}」建立成功！（類型：{visibility}）")
                time.sleep(1)
                
                await room_wait_phase(client, resp["room_id"], name)
            else:
                print(f"❌ 建立失敗：{resp.get('error', '未知錯誤')}")
                time.sleep(1)
                continue

            input("\n🔙 按下 Enter 鍵返回選單...")

        elif cmd == "4":
            finish = False
            while True:
                clear_screen()
                print("\n🚪 加入房間")

                # 先列出房間清單
                resp = await client.list_rooms(only_available="space")
                rooms = resp.get("rooms", [])

                if not rooms:
                    print("（目前沒有可加入的房間）")
                    input("\n🔙 按下 Enter 鍵返回選單...")
                    finish = True
                    break
                
                print("\n📋 可加入的房間清單：")
                for i, r in enumerate(rooms, start=1):
                    print(f"   {i}. {r['name']}（房主：{r['host']}，類型：{r['visibility']}）")
                
                try:
                    choice = int(input("\n請輸入要加入的房間 ID（0 返回）：").strip())
                    if choice == 0:
                        finish = True
                        break
                except ValueError:
                    print("⚠️ 請輸入有效的房間 ID。")
                    time.sleep(1)
                    continue
                
                if 1 <= choice <= len(rooms):
                    target_room = rooms[choice - 1]
                    rid = target_room["id"]
                else:
                    print("❌ 沒有這個房間。")
                    time.sleep(1)
                    continue

                # 判斷是否需要密碼
                password = None
                if target_room["visibility"] == "private":
                    password = input("請輸入房間密碼（輸入 0 返回）：").strip()
                    if password == "0":
                        finish = True
                        break
                    elif not password:
                        print("⚠️ 密碼不能為空。")
                        time.sleep(1)
                        continue

                # 如果選擇的房間沒問題就跳出迴圈
                break

            if finish:
                continue

            # ✅ 發送 join 請求
            resp = await client.join_room(rid, password)
            if resp and resp.get("ok"):
                print(f"✅ 成功加入房間：{target_room['name']} (ID={rid})")
                time.sleep(1)
                # 這裡可選擇進入房內等待畫面
                await asyncio.sleep(1) 
                await guest_wait_phase(client, rid, target_room["name"])
            else:
                print(f"❌ 加入失敗：{resp.get('error', '未知錯誤')}")
                input("\n🔙 按下 Enter 鍵返回選單...")

        elif cmd == "5":
            await invite_manage_phase(client)

        elif cmd == "6":
            resp = await client.logout()
            username = resp.get('name', '玩家')
            if resp.get("ok"):
                print(f"👋 登出成功，再見 {username}！")
            else:
                print(f"⚠️ 登出失敗：{resp.get('error', '未知錯誤')}")

            time.sleep(1)
            return


        else:
            print("❌ 無效指令。")


async def room_wait_phase(client, room_id, room_name):
    """房主等待其他玩家加入的階段（非阻塞鍵盤輸入版）"""
    guest_joined = False
    guest_name = None
    stop_flag = False
    last_guest_state = None
    press_button = 0
    last_refresh = 0

    async def check_guest_join():
        """背景任務：每秒檢查房間狀態"""
        nonlocal guest_joined, guest_name, stop_flag
        while not stop_flag:
            try:
                # 向伺服器查詢房間狀態
                resp = await client._req("Room", "status", {"room_id": room_id})
                if resp and resp.get("ok"):
                    guest_joined = resp.get("guest_joined", False)
                    guest_name = resp.get("guest_name", None)
                else:
                    guest_joined = False
                    guest_name = None
            except Exception as e:
                # 不中斷 loop，只印出錯誤
                print(f"⚠️ 無法檢查房間狀態：{e}")
            await asyncio.sleep(1)

    # 啟動背景檢查任務
    listener = asyncio.create_task(check_guest_join())

    try:
        while True:
            if (guest_joined != last_guest_state) or (time.time() - last_refresh > 10) \
                or press_button == 2:
                clear_screen()
                press_button = 0
                print(f"\n🏠 房間等待中：{room_name} (ID={room_id})")
                if guest_joined:
                    print(f"🎉 玩家 {guest_name} 已加入！")
                    print("【1】開始遊戲")
                    print("【2】踢出玩家")
                    print("【3】解散房間")
                else:
                    print("（等待其他玩家加入...）")
                    print("【1】顯示線上使用者")
                    print("【2】發送邀請")
                    print("【3】離開並關閉房間")
                #print("\n💡 畫面會在狀態改變時更新")
                last_refresh = time.time()
                last_guest_state = guest_joined

            # 🔹 非阻塞鍵盤讀取
            if msvcrt.kbhit():
                key = msvcrt.getch().decode("utf-8", errors="ignore")

                # --- 已有 guest 的選單 ---
                if guest_joined:
                    if key == "1":  # 開始遊戲
                        print("🚀 開始遊戲！")
                        resp = await client._req("Game", "start", {"room_id": room_id})

                        if resp.get("ok"):
                            host = resp.get("game_host")
                            port = resp.get("game_port")
                            print(f"🎮 啟動遊戲客戶端連線到 {host}:{port}")

                            print(f"🧩 啟動參數：['python', '-m', 'game.game_server', '{port}']")
                            subprocess.run(["python", "-m", "game.client_game", host, str(port)])
                            await client.close_room(room_id)
                        else:
                            print(f"⚠️ 無法啟動遊戲：{resp.get('error')}")

                        stop_flag = True
                        break

                    elif key == "2":  # 踢出玩家
                        print(f"👢 已將 {guest_name} 踢出。")
                        await client._req("Room", "kick", {"room_id": room_id})
                        guest_joined = False
                        guest_name = None
                        await asyncio.sleep(1)

                    elif key == "3":  # 解散
                        resp = await client.close_room(room_id)
                        if resp.get("ok"):
                            print(f"👋 已關閉房間「{room_name}」")
                        else:
                            print(f"⚠️ 關閉失敗：{resp.get('error', '未知錯誤')}")
                        stop_flag = True
                        break

                # --- 沒 guest 的選單 ---
                else:
                    if key == "1":
                        clear_screen()
                        press_button = 1
                        resp = await client.list_online_users()
                        users = resp.get("users", [])
                        others = [name for uid, name in users if uid != client.user_id]
                        print("\n📋 可邀請的玩家：")
                        if not others:
                            print("（目前沒有其他玩家在線上）")
                        else:
                            for i, name in enumerate(others, start=1):
                                print(f"   {i}. {name}")
                        input("\n🔙 按下 Enter 鍵返回...")
                        press_button = 2

                    elif key == "2":
                        clear_screen()
                        press_button = 1
                        resp = await client.list_online_users()
                        users = resp.get("users", [])
                        others = [(uid, name) for uid, name in users if uid != client.user_id]
                        if not others:
                            print("⚠️ 目前沒有其他線上玩家可邀請。")
                            await asyncio.sleep(1)
                            press_button = 2
                            continue

                        print("\n📨 選擇要邀請的玩家：")
                        for i, (_, name) in enumerate(others, start=1):
                            print(f"   {i}. {name}")

                        choice = input("輸入編號（0 取消）：").strip()
                        if choice == "0":
                            press_button = 2
                            continue
                        try:
                            index = int(choice) - 1
                            target_id, target_name = others[index]
                            resp = await client.send_invite(target_id, room_id)
                            if resp.get("ok"):
                                print(f"✅ 已發送邀請給 {target_name}")
                            else:
                                print(f"❌ 邀請失敗：{resp.get('error')}")
                                input("\n🔙 按下 Enter 鍵返回...")
                        except (ValueError, IndexError):
                            print("⚠️ 無效輸入。")
                        await asyncio.sleep(1)
                        press_button = 2

                    elif key == "3":
                        resp = await client.close_room(room_id)
                        if resp.get("ok"):
                            print(f"👋 已關閉房間「{room_name}」")
                        else:
                            print(f"⚠️ 關閉失敗：{resp.get('error', '未知錯誤')}")
                        stop_flag = True
                        break

            await asyncio.sleep(0.05)  # 稍微讓出 CPU

    finally:
        stop_flag = True
        listener.cancel()


async def guest_wait_phase(client, room_id, room_name):
    """加入者等待房主開始遊戲（無需重整畫面）"""
    stop_flag = False

    async def check_room_status():
        """背景任務：定期檢查房間狀態"""
        nonlocal stop_flag
        while not stop_flag:
            try:
                resp = await client._req("Room", "status", {"room_id": room_id})
                if not resp or not resp.get("ok"):
                    print("\n❌ 房間已被解散。")
                    await asyncio.sleep(1)
                    stop_flag = True
                    break

                status = resp.get("status")
                guest_id = resp.get("guest_id")

                if not guest_id:
                    print("\n👢 你已被房主踢出房間。")
                    await asyncio.sleep(1)
                    stop_flag = True
                    break

                if status == "play":
                    print("\n🚀 房主已開始遊戲！")
                    
                    game_host = resp.get("game_host")
                    game_port = resp.get("game_port")
                    
                    if game_host and game_port:
                        print(f"🎮 連線到遊戲伺服器 {game_host}:{game_port} ...")

                        print(f"🧩 啟動參數：['python', '-m', 'game.game_server', '{game_port}']")
                        subprocess.run(["python","-m","game.client_game", game_host, str(game_port)])
                        input("\n🔙 按下 Enter 鍵返回選單...")
                    else:
                        print("⚠️ 無法取得遊戲伺服器資訊 (host/port)")
                    
                    stop_flag = True
                    break

            except Exception as e:
                print(f"⚠️ 無法檢查房間狀態：{e}")
                stop_flag = True
                break

            await asyncio.sleep(1)

    # 顯示一次畫面
    clear_screen()
    print(f"\n🚪 加入房間：{room_name} (ID={room_id})")
    print("⏳ 等待房主開始遊戲...")
    print("\n【1】離開房間")
    
    listener = asyncio.create_task(check_room_status())

    try:
        while not stop_flag:
            if msvcrt.kbhit():
                key = msvcrt.getch().decode("utf-8", errors="ignore")
                if key == "1":
                    resp = await client.leave_room(room_id)
                    if resp.get("ok"):
                        print("👋 你已離開房間。")
                        stop_flag = True
                        await asyncio.sleep(1)
                    else:
                        print(f"⚠️ 離開失敗：{resp.get('error', '未知錯誤')}")
                    stop_flag = True
                    break

            await asyncio.sleep(0.05)
    finally:
        stop_flag = True
        listener.cancel()


async def invite_manage_phase(client):
    """邀請管理介面：顯示、回應邀請"""
    while True:
        clear_screen()
        print("📨 邀請清單\n")

        resp = await client.list_invites()
        if not resp.get("ok"):
            print("⚠️ 無法取得邀請列表。")
            await asyncio.sleep(1.5)
            return

        invites = resp.get("invites", [])
        if not invites:
            print("📭 目前沒有邀請。")
            input("\n🔙 按下 Enter 鍵返回主選單...")
            return

        # 顯示邀請列表
        for i, inv in enumerate(invites, start=1):
            print(f"{i}. 來自 {inv['from_name']} → 房間：{inv['room_name']} (ID={inv['room_id']})")

        print("\n輸入格式：『邀請編號 y/n』")
        print("例如：1 y ＝ 同意邀請編號 1，2 n ＝ 拒絕邀請編號 2")
        print("輸入 0 返回主選單。")

        cmd = input("\n👉 請輸入指令：").strip()
        if cmd == "0":
            print("🔙 返回主選單...")
            await asyncio.sleep(1)
            return

        try:
            idx, choice = cmd.split()
            index = int(idx) - 1  # 🟩 使用者輸入從 1 開始，list 是從 0 開始
            if index < 0 or index >= len(invites):
                print("⚠️ 無效的邀請編號。")
                await asyncio.sleep(1)
                continue

            invite_id = invites[index]["invite_id"]  # 🟩 取出真正的 invite_id
            accept = choice.lower() == "y"
        except Exception:
            print("⚠️ 格式錯誤，請重新輸入。")
            await asyncio.sleep(1)
            continue

        # 傳送回應
        resp2 = await client.respond_invite(invite_id, accept)
        if resp2.get("ok"):
            msg = resp2.get("msg", "✅ 已處理邀請。")
            
            
            if accept and "room_id" in resp2:
                print(f"{msg} 正在加入房間...")
                room_id = resp2["room_id"]
                room_name = f"房間 {room_id}"  # 伺服器可能沒傳名稱，可以先用 ID 顯示
                await asyncio.sleep(1)
                await guest_wait_phase(client, room_id, room_name)
                break
        else:
            msg = f"⚠️ {resp2.get('error', '無法處理邀請。')}"
            print(msg)
            input("\n按 Enter 鍵繼續...")
        

async def main():
    client = LobbyClient()
    await client.connect()
    print("✅ 已連線到 Lobby Server")

    while True:
        logged_in = await login_phase(client)
        if not logged_in:
            break  # 使用者選擇離開
        await lobby_phase(client)

    await client.close()
    print("🛑 已關閉連線")

def clear_screen():
    # Windows
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")

if __name__ == "__main__":
    asyncio.run(main())
