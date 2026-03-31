import os
import re
import requests
import argparse
import sqlite3
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

def init_db(db_path="images_list.db"):
    """
    初始化并无损升级 SQLite 数据库结构。
    引入状态机字段：images_downloaded，用于区分“仅有元数据”和“图片已下载完成”。
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. 创建图片记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS images_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_name TEXT NOT NULL,
            image_url TEXT UNIQUE NOT NULL,
            article_title TEXT NOT NULL,
            download_time TEXT NOT NULL
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_image_url ON images_record(image_url)')
    
    # 2. 创建文章记录表 (对齐历史接口结构)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS article_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            article_url TEXT UNIQUE NOT NULL,
            publish_time TEXT NOT NULL,
            cover_url TEXT
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_article_url ON article_list(article_url)')
    
    # 3. 【专家级：自动迁移】检查是否缺少 images_downloaded 字段，没有则无损添加
    cursor.execute("PRAGMA table_info(article_list)")
    columns = [info[1] for info in cursor.fetchall()]
    if "images_downloaded" not in columns:
        cursor.execute("ALTER TABLE article_list ADD COLUMN images_downloaded INTEGER DEFAULT 0")
        print("⚙️ 数据库表结构已自动升级: 成功添加 images_downloaded 状态字段。")
    
    conn.commit()
    conn.close()

def get_extension_from_url(url):
    match = re.search(r'\.([a-zA-Z]+)(\?|$)', url)
    return f".{match.group(1)}" if match else ".jpg"

def download_image(url, save_dir="downloaded_images", title="", date="", index=0, db_path="images_list.db"):
    try:
        conn_check = sqlite3.connect(db_path, timeout=15.0)
        cursor_check = conn_check.cursor()
        cursor_check.execute("SELECT image_name FROM images_record WHERE image_url = ?", (url,))
        result = cursor_check.fetchone()
        conn_check.close()
        
        if result:
            print(f"⏭️ 数据库已存在该图片记录，跳过: {url}")
            return
    except Exception as e:
        print(f"⚠️ 图片数据库读取异常: {str(e)}")
        return

    save_dir_path = os.path.join(os.getcwd(), save_dir)
    if not os.path.exists(save_dir_path):
        os.makedirs(save_dir_path, exist_ok=True)
        
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.34(0x16082222) NetType/WIFI Language/zh_CN",
            "Referer": "https://mp.weixin.qq.com/",
        }
        response = requests.get(url, headers=headers, stream=True, timeout=15)
        if response.status_code == 200:
            ext = get_extension_from_url(url)
            clean_title = re.sub(r'[^\w\s-]', '', title).strip()
            clean_title = re.sub(r'[\s]+', '_', clean_title)
            timestamp = date.replace("-", "")
            image_filename = f"{clean_title}_{timestamp}_{index}{ext}"
            filepath = os.path.join(save_dir_path, image_filename)
            
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
                    
            print(f"✅ 图片下载成功: {filepath}")
            
            try:
                conn_insert = sqlite3.connect(db_path, timeout=15.0)
                cursor_insert = conn_insert.cursor()
                cursor_insert.execute('''
                    INSERT INTO images_record (image_name, image_url, article_title, download_time)
                    VALUES (?, ?, ?, ?)
                ''', (image_filename, url, title, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn_insert.commit()
                conn_insert.close()
            except sqlite3.IntegrityError:
                if 'conn_insert' in locals():
                    conn_insert.close()
                
        else:
            print(f"❌ 图片下载失败: {url} (状态码: {response.status_code})")
    except Exception as e:
        print(f"❌ 图片下载网络异常: {url} ({str(e)})")

def extract_article_date(html_content):
    pattern = r'create_time.*?(\d{4}-\d{2}-\d{2})'
    match = re.search(pattern, html_content)
    if match:
        return match.group(1)
    pattern2 = r'var createTime = [\'\"]?(\d{4}-\d{2}-\d{2})'
    match2 = re.search(pattern2, html_content)
    return match2.group(1) if match2 else datetime.now().strftime("%Y-%m-%d")

def is_large_image(img_url):
    return "640" in img_url and "!wx_fmt" not in img_url

def process_single_article(url, db_path="images_list.db"):
    # 核心重构：判断是跳过、更新还是新插入
    is_existing_record = False
    try:
        conn_check = sqlite3.connect(db_path, timeout=15.0)
        cursor_check = conn_check.cursor()
        cursor_check.execute("SELECT images_downloaded FROM article_list WHERE article_url = ?", (url,))
        result = cursor_check.fetchone()
        conn_check.close()
        
        if result:
            is_existing_record = True
            # 状态为 1 说明彻底下完了，直接跳过
            if result[0] == 1:
                print(f"⏭️ 数据库标记该文章图片已处理完毕，安全跳过: ({url})")
                return
            # 状态为 0 说明是只爬了元数据，继续放行往下走
    except Exception as e:
        print(f"⚠️ 文章数据库读取异常: {str(e)}")

    print(f"\n🚀 开始提取文章图片: {url}")
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.34(0x16082222) NetType/WIFI Language/zh_CN",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        html_content = response.text
        date = extract_article_date(html_content)
        
        soup = BeautifulSoup(html_content, "html.parser")
        title_element = soup.find("h1")
        title = title_element.get_text().strip() if title_element else "无标题"
        print(f"📝 文章标题: {title} | 📅 日期: {date}")
        
        images = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-echo")
            if src and not src.startswith("data:") and is_large_image(src):
                absolute_url = urljoin(url, src)
                if absolute_url not in images:
                    images.append(absolute_url)
        
        if not images:
            print("⚠️ 未发现符合大图标准的图片。")
        else:
            print(f"⚙️ 开启并发下载，共发现 {len(images)} 张目标图片...")
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = []
                for idx, img_url in enumerate(images):
                    futures.append(executor.submit(download_image, img_url, "downloaded_images", title, date, idx, db_path))
                
                for future in as_completed(futures):
                    future.result()
                
        # 任务闭环：持久化状态机
        try:
            conn_state = sqlite3.connect(db_path, timeout=15.0)
            cursor_state = conn_state.cursor()
            if is_existing_record:
                # 记录是从外部导入的，仅更新下载状态为 1
                cursor_state.execute('''
                    UPDATE article_list SET images_downloaded = 1 WHERE article_url = ?
                ''', (url,))
                print(f"💾 状态更新完成：文章《{title}》已标记为“已处理”。")
            else:
                # 用户通过命令单独传入的新链接，插入完整数据且状态标记为 1
                cursor_state.execute('''
                    INSERT INTO article_list (title, article_url, publish_time, cover_url, images_downloaded)
                    VALUES (?, ?, ?, ?, ?)
                ''', (title, url, date, "", 1))
                print(f"💾 新记录保存完成：文章《{title}》入库并标记为“已处理”。")
            conn_state.commit()
            conn_state.close()
        except Exception as e:
            print(f"❌ 状态标记写入失败: {str(e)}")
                
    except Exception as e:
        print(f"❌ 文章整体处理异常: {url} 错误信息: {str(e)}")

def main():
    db_path = "images_list.db"
    init_db(db_path)

    parser = argparse.ArgumentParser(description="微信公众号图片批量并发爬虫工具")
    parser.add_argument("-u", "--url", help="抓取单个公众号文章地址")
    parser.add_argument("-f", "--file", help="包含多个公众号文章地址的文本文件（每行一个URL）")
    parser.add_argument("-a", "--auto", action="store_true", help="强制从数据库自动读取未提取图片的文章列表")
    args = parser.parse_args()

    urls_to_process = []
    
    if args.url:
        urls_to_process.append(args.url)
    elif args.file:
        if os.path.exists(args.file):
            with open(args.file, "r", encoding="utf-8") as file:
                for line in file:
                    cleaned = line.strip()
                    if cleaned and cleaned.startswith("http"):
                        urls_to_process.append(cleaned)
        else:
            print(f"❌ 找不到指定的文件: {args.file}")
            return
    else:
        # 如果什么参数都不传，或者使用了 -a，确认进入【全自动数据库消费者模式】
        print("🔄 未检测到外部 URL，自动进入【数据库挂机处理模式】...")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # 捞出所有被历史爬虫塞进来，但是还没下载过图片的数据
        cursor.execute("SELECT article_url FROM article_list WHERE images_downloaded = 0 OR images_downloaded IS NULL")
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            print("🎉 太棒了！数据库中所有文章的图片都已下载完毕，当前无待办任务。")
            return
            
        print(f"📦 雷达扫描完毕：从数据库中调取到 {len(rows)} 篇待提取图片的文章！开始执行流水线...\n")
        for row in rows:
            urls_to_process.append(row[0])

    for i, target_url in enumerate(urls_to_process):
        print(f"\n--- [进度 {i+1}/{len(urls_to_process)}] ---")
        process_single_article(target_url, db_path)

if __name__ == "__main__":
    main()
