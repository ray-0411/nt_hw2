import asyncio
from client.client_net import LobbyClient
import os
import time



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
        print(f"\n🎮 玩家：{client.username}")
        print("1. 顯示線上使用者")
        print("2. 顯示房間清單")
        print("3. 建立房間")
        print("4. 加入房間")
        print("5. 離開房間")
        print("6. 查詢邀請")
        print("7. 登出")
        cmd = input("請輸入指令：").strip()

        if cmd == "1":
            resp = await client.list_online_users()
            print("📋 線上使用者：", resp.get("users"))

        elif cmd == "2":
            resp = await client.list_rooms()
            print("📋 房間清單：", resp.get("rooms"))

        elif cmd == "3":
            name = input("房間名稱：")
            resp = await client.create_room(name)
            print("✅ 建立結果：", resp)

        elif cmd == "4":
            rid = int(input("輸入要加入的房間 ID："))
            resp = await client.join_room(rid)
            print("✅ 加入結果：", resp)

        elif cmd == "5":
            resp = await client.leave_room()
            print("✅ 離開結果：", resp)

        elif cmd == "6":
            resp = await client.list_invites()
            print("📬 邀請：", resp.get("invites"))

        elif cmd == "7":
            resp = await client.logout()
            print("👋", resp)
            return

        else:
            print("❌ 無效指令。")

async def main():
    client = LobbyClient()
    await client.connect()
    print("✅ 已連線到 Lobby Server")

    logged_in = await login_phase(client)
    if logged_in:
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
