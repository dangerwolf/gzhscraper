import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

def get_extension_from_url(url):
    match = re.search(r'\.([a-zA-Z]+)(\?|$)', url)
    return f".{match.group(1)}" if match else ".jpg"

def download_image(url, save_dir="downloaded_images", title="", date=""):
    save_dir_path = os.path.join(os.getcwd(), save_dir)
    if not os.path.exists(save_dir_path):
        os.makedirs(save_dir_path)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.34(0x16082222) NetType/WIFI Language/zh_CN",
            "Referer": "https://mp.weixin.qq.com/",
        }
        response = requests.get(url, headers=headers, stream=True)
        if response.status_code == 200:
            ext = get_extension_from_url(url)
            clean_title = re.sub(r'[^\w\s-]', '', title).strip()
            clean_title = re.sub(r'[\s]+', '_', clean_title)
            timestamp = date.replace("-", "")
            filename = os.path.join(save_dir_path, f"{clean_title}_{timestamp}_{len(os.listdir(save_dir_path))}{ext}")
            with open(filename, "wb") as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            print(f"✅ 图片下载成功: {filename}")
        else:
            print(f"❌ 图片下载失败: {url} (状态码: {response.status_code})")
    except Exception as e:
        print(f"❌ 图片下载异常: {url} ({str(e)})")

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

def main():
    url = "<这里替换成你指定的gzh的文章地址>"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.34(0x16082222) NetType/WIFI Language/zh_CN",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    response = requests.get(url, headers=headers)
    html_content = response.text
    date = extract_article_date(html_content)
    print(f"📅 文章日期: {date}")
    soup = BeautifulSoup(html_content, "html.parser")
    title = soup.find("h1").get_text() if soup.find("h1") else "无标题"
    print("📝 文章标题:", title)
    content = soup.find("div", class_="rich_media_content").get_text() if soup.find("div", class_="rich_media_content") else "无内容"
    print("📄 文章内容:", content[:200] + "...")
    images = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-echo")
        if src and not src.startswith("data:") and is_large_image(src):
            absolute_url = urljoin(url, src)
            images.append(absolute_url)
            print("🔍 发现大尺寸图片链接:", absolute_url)
    for img_url in images:
        download_image(img_url, save_dir="downloaded_images", title=title, date=date)

if __name__ == "__main__":
    main()
