import os
import json
from playwright.sync_api import sync_playwright, Error

# --- 配置 ---
# 目标网址
TARGET_URL = "https://buyin.jinritemai.com/dashboard/merch-picking-hall/rank?btm_ppre=a10091.b24215.c68160.d839440_i16852609794&btm_pre=a10091.b71710.c68160.d839440_i1482933506&btm_show_id=ebf82770-5d02-48ed-9f92-c1a75d6fd2f3&pre_universal_page_params_id=&universal_page_params_id=e0b97666-5e57-41ab-850a-5418bb06acad"
# 要拦截的API地址
INTERCEPT_URL = "https://buyin.jinritemai.com/pc/leaderboard/center/pmt"
# 登录状态存储文件
STORAGE_STATE_FILE = 'storage_state.json'
# 浏览器用户代理
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"


def handle_response(response):
    """监听并打印指定URL的响应数据"""
    if INTERCEPT_URL in response.url:
        print(f"--- 截获到响应来自: {response.url} ---")
        try:
            # 获取响应的JSON数据
            body = response.json()
            # 美化后打印到控制台
            print(json.dumps(body, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"无法将响应体解析为JSON: {e}")
        print("----------------------------------------------------")

def run_browser():
    """
    启动Playwright，处理登录状态、请求拦截和用户交互。
    """
    with sync_playwright() as p:
        # 检查是否存在已保存的登录状态
        storage_state = None
        if os.path.exists(STORAGE_STATE_FILE):
            try:
                with open(STORAGE_STATE_FILE, 'r', encoding='utf-8') as f:
                    storage_state = json.load(f)
                print(f"成功加载已保存的登录状态: {STORAGE_STATE_FILE}")
            except (json.JSONDecodeError, IOError) as e:
                print(f"读取登录状态文件失败: {e}。将启动新的登录会话。")
                storage_state = None

        # 启动浏览器
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            storage_state=storage_state,
            user_agent=USER_AGENT
        )
        page = context.new_page()

        # 设置请求拦截
        # 注意：这里我们监听 'response' 事件，如果需要修改请求或响应，需要使用 page.route
        page.on("response", handle_response)

        print(f"正在导航到: {TARGET_URL}")
        try:
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            print("页面加载完成。")
            print("\n>>> 浏览器已打开，您可以进行操作（如首次登录）。 <<<")
            print(">>> 操作完成后，请直接关闭浏览器窗口以继续执行。 <<<")
            
            # 暂停脚本，将控制权交给用户
            # 当用户关闭浏览器时，page.pause()会结束，代码会继续执行
            page.pause()

        except Error as e:
            print(f"Playwright操作失败: {e}")
        finally:
            # 在浏览器关闭后执行
            print("浏览器窗口已关闭，正在保存当前会话状态...")
            try:
                # 保存当前上下文的存储状态（包含最新的cookies）
                updated_storage_state = context.storage_state()
                with open(STORAGE_STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(updated_storage_state, f, indent=2)
                print(f"会话状态已成功保存到: {STORAGE_STATE_FILE}")
            except Error as e:
                print(f"保存会话状态失败: {e}")
            
            # 清理资源
            context.close()
            browser.close()
            print("浏览器已关闭。")


if __name__ == "__main__":
    run_browser()