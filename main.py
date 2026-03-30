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
    初始化 SQLite 数据库，创建图片记录表、文章记录表和查询索引
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 创建图片记录表
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
    
    # 创建文章记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_title TEXT NOT NULL,
            article_url TEXT UNIQUE NOT NULL,
            article_date TEXT NOT NULL,
            scrape_time TEXT NOT NULL
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_article_url ON articles_record(article_url)')
    
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
            print(f"⏭️ 数据库已存在该图片记录，跳过下载: {url}")
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
                print(f"⚠️ 多线程并发时捕获到重复图片URL，忽略插入: {url}")
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
    # 在进行任何网络请求前，先查询文章记录表
    try:
        conn_check = sqlite3.connect(db_path, timeout=15.0)
        cursor_check = conn_check.cursor()
        cursor_check.execute("SELECT article_title FROM articles_record WHERE article_url = ?", (url,))
        result = cursor_check.fetchone()
        conn_check.close()
        
        if result:
            print(f"⏭️ 数据库已存在该文章记录，跳过解析: 《{result[0]}》 ({url})")
            return
    except Exception as e:
        print(f"⚠️ 文章数据库读取异常: {str(e)}")

    print(f"🚀 开始解析文章: {url}")
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.34(0x16082222) NetType/WIFI Language/zh_CN",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        html_content = response.text
        date = extract_article_date(html_content)
        print(f"📅 文章日期: {date}")
        
        soup = BeautifulSoup(html_content, "html.parser")
        title_element = soup.find("h1")
        title = title_element.get_text().strip() if title_element else "无标题"
        print(f"📝 文章标题: {title}")
        
        content_element = soup.find("div", class_="rich_media_content")
        content = content_element.get_text() if content_element else "无内容"
        print(f"📄 文章内容摘录: {content[:100]}...")
        
        images = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-echo")
            if src and not src.startswith("data:") and is_large_image(src):
                absolute_url = urljoin(url, src)
                if absolute_url not in images:
                    images.append(absolute_url)
                    print(f"🔍 发现大尺寸图片链接: {absolute_url}")
        
        print(f"⚙️ 开始并发下载《{title}》中的 {len(images)} 张图片...")
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for idx, img_url in enumerate(images):
                futures.append(executor.submit(download_image, img_url, "downloaded_images", title, date, idx, db_path))
            
            for future in as_completed(futures):
                future.result()
                
        # 所有解析和并发下载任务派发/执行完毕后，持久化文章记录
        try:
            conn_insert = sqlite3.connect(db_path, timeout=15.0)
            cursor_insert = conn_insert.cursor()
            cursor_insert.execute('''
                INSERT INTO articles_record (article_title, article_url, article_date, scrape_time)
                VALUES (?, ?, ?, ?)
            ''', (title, url, date, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn_insert.commit()
            conn_insert.close()
            print(f"💾 文章信息已持久化保存: 《{title}》")
        except sqlite3.IntegrityError:
            print(f"⚠️ 捕获到重复文章URL，忽略插入: {url}")
            if 'conn_insert' in locals():
                conn_insert.close()
                
    except Exception as e:
        print(f"❌ 文章处理异常: {url} 错误信息: {str(e)}")

def main():
    db_path = "images_list.db"
    init_db(db_path)

    parser = argparse.ArgumentParser(description="微信公众号图片批量并发爬虫工具")
    parser.add_argument("-u", "--url", help="抓取单个公众号文章地址")
    parser.add_argument("-f", "--file", help="包含多个公众号文章地址的文本文件（每行一个URL）")
    args = parser.parse_args()

    urls_to_process = []
    
    if args.url:
        urls_to_process.append(args.url)
    elif args.file:
        if os.path.exists(args.file):
            with open(args.file, "r", encoding="utf-8") as file:
                for line in file:
                    cleaned_url = line.strip()
                    if cleaned_url and cleaned_url.startswith("http"):
                        urls_to_process.append(cleaned_url)
        else:
            print(f"❌ 找不到指定的文件: {args.file}")
            return
    else:
        print("⚠️ 未提供参数。请使用 -u 指定单个URL，或使用 -f 指定包含多个URL的文本文件。")
        parser.print_help()
        return

    for target_url in urls_to_process:
        process_single_article(target_url, db_path)

if __name__ == "__main__":
    main()
