import re
import requests

def get_gzh_history_url(article_url):
    print(f"🚀 正在解析文章源码寻找公众号凭证: {article_url}")
    
    # 升级请求头，模拟真实的浏览器行为，避免被判定为僵尸脚本
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    try:
        # 使用 Session 自动处理微信可能抛出的前置 302 重定向
        session = requests.Session()
        response = session.get(article_url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"❌ 请求失败，状态码: {response.status_code}")
            return None
            
        html_content = response.text
        print(f"📦 成功获取网页源码，总长度: {len(html_content)} 字符")
        
        # 爬虫诊断：标准的微信文章源码通常在 20,000 字符以上
        if len(html_content) < 5000:
            print("⚠️ 警告：获取到的网页源码极短，您的IP可能触发了微信的风控拦截、验证码，或者链接已失效。")
            print(f"📄 源码前200字符诊断: {html_content[:200]}")
        
        # 核心：多重正则提取矩阵
        biz_value = None
        
        # 策略1：精确定位 JS 全局变量定义 (如 var biz = "MzI4MjkzMTcwNQ==";)
        match1 = re.search(r'(?:var|window\.)?\s*biz\s*=\s*["\']([^"\']+)["\']', html_content)
        
        # 策略2：匹配 meta 标签或其他超链接中携带的 __biz 参数，兼容转义符
        match2 = re.search(r'__biz=([a-zA-Z0-9=]+)(?:&|&amp;|\\x26)', html_content)
        
        # 策略3：匹配 JS 对象字典里的键值对 (如 "__biz" : "MzI4...")
        match3 = re.search(r'__biz[\'"]?\s*:\s*["\']([a-zA-Z0-9=]+)["\']', html_content)

        if match1:
            biz_value = match1.group(1)
            print("✅ [策略1] 成功在 JS 全局变量中提取到 __biz")
        elif match2:
            biz_value = match2.group(1)
            print("✅ [策略2] 成功在内置资源链接中提取到 __biz")
        elif match3:
            biz_value = match3.group(1)
            print("✅ [策略3] 成功在 JSON 配置字典中提取到 __biz")
            
        if biz_value:
            print(f"🔑 公众号唯一标识 (__biz): {biz_value}")
            history_url = f"https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz={biz_value}&scene=124#wechat_redirect"
            return history_url
        else:
            print("❌ 所有正则提取策略均失败。")
            # 出于工程严谨，将未识别的源码写入本地用于专家排查
            with open("debug_wechat_html.txt", "w", encoding="utf-8") as f:
                f.write(html_content)
            print("💾 已将返回的异常 HTML 源码保存至当前目录下的 debug_wechat_html.txt，请打开该文件检查是否被微信风控。")
            return None
            
    except Exception as e:
        print(f"❌ 发生网络异常: {str(e)}")
        return None

if __name__ == "__main__":
    test_url = "https://mp.weixin.qq.com/s/<ddddddd>" #这里要进行修改
    history_link = get_gzh_history_url(test_url)
    
    if history_link:
        print(f"🎯 构造出的公众号历史文章主页地址为:\n{history_link}")
