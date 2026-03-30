import os
import time
import random
import requests
import sqlite3

# ==========================================
# 专家配置区：请将您在公众平台抓包获取的凭证填入下方
# ==========================================
# 1. 在此处粘贴您通过浏览器 Network 面板获取的完整 Cookie 字符串
MP_COOKIE = "dddddddd"

# 2. 在此处粘贴您提取的 token (一串纯数字)
MP_TOKEN = "ddddddd"

# 您要抓取的目标公众号的 fakeid (也就是 __biz，这里已经为您填好)
TARGET_FAKEID = "dddddd"
# ==========================================

def init_database(db_path="gzh_history_mp.db"):
    """
    初始化 SQLite 数据库，建立专门用于官方接口数据结构的文章表
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS article_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            article_url TEXT UNIQUE NOT NULL,
            publish_time TEXT NOT NULL,
            cover_url TEXT
        )
    ''')
    # 建立 URL 唯一索引，实现增量抓取和秒级去重
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_article_url ON article_list(article_url)')
    conn.commit()
    conn.close()
    print("💾 数据库初始化完成: gzh_history_mp.db")

def fetch_mp_history(fakeid, begin, token, cookie, db_path="gzh_history_mp.db"):
    """
    调用公众号后台 list_ex 接口获取 JSON 数据并持久化入库
    """
    url = "https://mp.weixin.qq.com/cgi-bin/appmsg"
    
    # 伪装为标准桌面浏览器
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Cookie": cookie,
        "Referer": "https://mp.weixin.qq.com/"
    }
    
    # 官方接口标准参数矩阵
    params = {
        "action": "list_ex",
        "begin": str(begin),  # 翻页偏移量，每次递增 5
        "count": "5",         # 官方限制每次最多返回 5 条推文数据
        "fakeid": fakeid,
        "type": "9",          # 9 代表图文消息
        "query": "",
        "token": token,
        "lang": "zh_CN",
        "f": "json",
        "ajax": "1"
    }

    print(f"📡 正在请求分页数据: begin={begin} ...")
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code != 200:
            print(f"❌ 网络���求异常，状态码: {response.status_code}")
            return False

        res_json = response.json()

        # 解析微信官方接口的返回码 (base_resp -> ret)
        base_resp = res_json.get("base_resp", {})
        ret = base_resp.get("ret", 0)

        # 风控拦截诊断机制
        if ret == 200013 or ret == 200040:
            print("⚠️ [频控触发] 您抓取的速度过快，已被微信服务器暂时限制！")
            print("💡 专家建议：目前已无法继续拉取。请停止脚本，等待 30-60 分钟后再继续抓取（您的数据库已自动保存进度，下次不会重复抓取）。")
            return False
        elif ret != 0:
            print(f"❌ 接口返回身份验证错误，错误码: {ret}")
            print("💡 提示：大概率是您的 Cookie 已失效，或者 token 填写错误，请重新登录网页后台抓取。")
            return False

        # 提取核心数据列表
        app_msg_list = res_json.get("app_msg_list", [])
        if not app_msg_list:
            print("⚠️ 本页没有解析到文章数据，已到达该公众号的历史最底端。")
            return False

        saved_count = 0
        conn = sqlite3.connect(db_path, timeout=15.0)
        cursor = conn.cursor()

        for msg in app_msg_list:
            title = msg.get("title", "").strip()
            article_url = msg.get("link", "").strip()
            cover_url = msg.get("cover", "").strip()
            update_time = msg.get("update_time", 0)

            # 将 Unix 时间戳转换为直观的字符串
            publish_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(update_time))

            if title and article_url:
                try:
                    cursor.execute('''
                        INSERT INTO article_list (title, article_url, publish_time, cover_url)
                        VALUES (?, ?, ?, ?)
                    ''', (title, article_url, publish_time, cover_url))
                    saved_count += 1
                    print(f"✅ 入库成功: 《{title}》 [{publish_time}]")
                except sqlite3.IntegrityError:
                    print(f"⏭️ 数据库去重: 《{title}》 已存在，跳过。")

        conn.commit()
        conn.close()

        print(f"📄 begin={begin} 抓取完毕，共新增入库 {saved_count} 篇文章。")
        return True

    except Exception as e:
        print(f"❌ 解析或入库发生严重异常: {str(e)}")
        return False

def main():
    init_database()

    # 安全锁：确保用户已经填入凭证，避免无效发包触发风控
    if "在此处粘贴" in MP_COOKIE or "在此处粘贴" in MP_TOKEN:
        print("🛑 致命错误: 您的超级通行证尚未配置！")
        print("请按指南登录 mp.weixin.qq.com 获取您自己的 Cookie 和 token，并填入代码第 11 行和 14 行。")
        return

    print(f"🚀 开始通过官方后台管道，全量采集公众号假名: {TARGET_FAKEID}")

    # 官方接口分页参数 begin 每次递增 5（因为 count=5）
    begin = 0
    page_num = 1

    while True:
        print(f"\n--- 正在准备抓取第 {page_num} 页 (begin={begin}) ---")
        has_more = fetch_mp_history(TARGET_FAKEID, begin, MP_TOKEN, MP_COOKIE)

        if not has_more:
            print("\n🎉 探测结束：数据已全部到底，或触发了安全频率管控。脚本安全退出。")
            break

        begin += 5
        page_num += 1

        # 【极其关键的防封禁机制】
        # 官方后台对接口调用频率极其敏感！严禁低于 3 秒的连续高频请求。
        sleep_time = random.uniform(5.0, 12.0)
        print(f"⏳ 隐蔽系统启动，随机休眠 {sleep_time:.2f} 秒，模拟人类翻页速度...")
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()