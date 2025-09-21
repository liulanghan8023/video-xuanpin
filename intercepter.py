import asyncio
import json
import random
from pathlib import Path
from playwright.async_api import async_playwright, Playwright, TimeoutError


# --- Anti-detection script ---
INIT_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', {get: () => false});
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en', 'en-GB']});
    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
    );
    try {
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
          if (parameter === 37445) { # VENDOR
            return 'Intel Open Source Technology Center';
          }
          if (parameter === 37446) { # RENDERER
            return 'Mesa DRI Intel(R) Ivybridge Mobile ';
          }
          return getParameter(parameter);
        };
    } catch (e) {
        console.log('Could not spoof WebGL');
    }
"""

# --- 配置常量 ---
# 目标榜单页面URL
RANK_URL = "https://buyin.jinritemai.com/dashboard/merch-picking-hall/rank?btm_ppre=a10091.b24215.c68160.d839440_i16852609794&btm_pre=a10091.b71710.c68160.d839440_i1482933506&btm_show_id=ebf82770-5d02-48ed-9f92-c1a75d6fd2f3&pre_universal_page_params_id=&universal_page_params_id=e0b97666-5e57-41ab-850a-5418bb06acad"
# 榜单数据接口URL关键字
RANK_API_URL_PART = "pc/leaderboard/center/pmt"
# 详情页数据接口URL关键字
DETAIL_API_URL_PART = "pc/selection/decision/pack_detail"
# 详情页URL模板
DETAIL_PAGE_URL_TEMPLATE = "https://buyin.jinritemai.com/dashboard/merch-picking-library/merch-promoting?id={}"
# Cookie/会话状态保存文件
STORAGE_STATE_FILE = Path("storage_state.json")

# 用于详情页数据拦截的全局事件和存储
detail_core_data_event = asyncio.Event()
detail_7day_data_event = asyncio.Event()
detail_core_data_storage = {}
detail_7day_data_storage = {}

async def handle_detail_api_route(route):
    request = route.request
    try:
        response = await route.fetch()
        response_body_bytes = await response.body()
        response_json = json.loads(response_body_bytes)

        if request.method == "POST":
            request_body_json = request.post_data_json
            data_module = request_body_json.get("data_module")

            if data_module == "core":
                print("\n✅ --- 截获到详情页核心数据请求 ---")
                detail_core_data_storage["request_body"] = request_body_json
                detail_core_data_storage["response_body"] = response_json
                print("请求体:")
                print(json.dumps(request_body_json, indent=2, ensure_ascii=False))
                print("----------------------------------")
                detail_core_data_event.set()

            elif data_module == "dynamic":
                dynamic_params = request_body_json.get("dynamic_params", {})
                promotion_data_params = dynamic_params.get("promotion_data_params", {})
                time_range = promotion_data_params.get("time_range")

                if time_range == 7:
                    print("\n✅ --- 截获到详情页近7天数据请求 ---")
                    detail_7day_data_storage["request_body"] = request_body_json
                    detail_7day_data_storage["response_body"] = response_json
                    print("请求体:")
                    print(json.dumps(request_body_json, indent=2, ensure_ascii=False))
                    print("------------------------------------")
                    detail_7day_data_event.set()
        
        await route.fulfill(status=response.status, headers=response.headers, body=response_body_bytes)

    except Exception as e:
        print(f"❌ 路由处理程序中出错: {e}")
        await route.continue_()

def handle_request(route, request):
    print(request.post_data_json)
    print(request.url)
    print(request.method)
    route.continue_()

async def run(playwright: Playwright):
    """主执行函数"""
    
    storage_state = str(STORAGE_STATE_FILE.absolute()) if STORAGE_STATE_FILE.exists() else None
    if storage_state:
        print(f"检测到会话文件 {STORAGE_STATE_FILE}，将尝试使用它免登录。")
    else:
        print("未找到本地会话文件，将进行首次登录。")

    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(
        storage_state=storage_state,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
    )
    await context.add_init_script(INIT_SCRIPT)
    page = await context.new_page()

    try:
        print(f"正在打开榜单页面: {RANK_URL}")
        await page.goto(RANK_URL, wait_until="domcontentloaded")

        if "login" in page.url:
            print("检测到需要登录，请在弹出的浏览器窗口中手动登录。")
            print("登录成功后，脚本将自动从当前页面继续执行...")
            await page.wait_for_url(lambda url: "login" not in url, timeout=300000)
            print("登录成功，继续执行脚本。")

        await page.wait_for_timeout(random.randint(1000, 2500))
        print("点击 '趋势榜'...")
        await page.get_by_text("趋势榜", exact=True).click()

        await page.wait_for_timeout(random.randint(1000, 2500))
        print("点击 '短视频'，并等待榜单数据加载...")
        async with page.expect_response(lambda r: RANK_API_URL_PART in r.url, timeout=30000) as response_info:
            print("点击 '短视频'...")
            await page.get_by_text("短视频", exact=True).click()

        rank_response = await response_info.value
        print("\n✅ --- 成功截获到榜单数据 ---")
        try:
            rank_data = await rank_response.json()
            print(json.dumps(rank_data, indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            print("❌ 无法将榜单数据响应解析为JSON。")
            print("收到的响应内容:")
            print(await rank_response.text())
            rank_data = {} 
        print("--- 榜单数据结束 ---")

        promotions = rank_data.get("data", {}).get("promotions")
        if promotions:
            # 只处理第一个商品
            first_product_id = promotions[0]["product_id"]
            detail_page_url = DETAIL_PAGE_URL_TEMPLATE.format(first_product_id)
            
            print(f"成功解析到商品ID: {first_product_id}")
            print(f"正在打开详情页: {detail_page_url}")
            
            # 在导航到详情页之前设置路由拦截
            # await page.route(lambda url: DETAIL_API_URL_PART in url, handle_detail_api_route)
            # page.on(lambda url: DETAIL_API_URL_PART in url, handle_request)
            async with page.expect_response(lambda r: DETAIL_API_URL_PART in r.url and r.request.post_data_json.get("data_module") == 'core', timeout=30000) as response_info:
                await page.goto(detail_page_url, wait_until="domcontentloaded")
            print("等待详情页核心数据加载...")
            rank_respons1e = await response_info.value
            print( rank_respons1e.request.post_data_json)
            rank_dat1a = await rank_respons1e.json()
            # 等待核心数据被拦截并处理
            print("\n✅ --- 成功截获到详情页核心数据响应 ---")
            print(json.dumps(rank_dat1a, indent=2, ensure_ascii=False))
            # 步骤6: 点击 "近7天" 并等待拦截详情页数据
            print("等待详情页加载并点击 '近7天'...")
            try:
                # 确保页面网络空闲，所有初始请求已完成，避免时序问题
                await page.wait_for_load_state('networkidle')

                # and r.request.post_data_json.get("dynamic_params", {}).get("promotion_data_params", {}).get("time_range") == 7
                async with page.expect_response(lambda r: DETAIL_API_URL_PART in r.url and r.request.post_data_json.get(
                        "data_module") == 'dynamic' and r.request.post_data_json.get("dynamic_params", {}).get("promotion_data_params", {}).get("time_range") == '7' , timeout=30000) as response_info:
                    await page.get_by_text("近7天", exact=True).click()
                    print("点击了 '近7天'...")

                rank_respons1e = await response_info.value
                print(rank_respons1e.request.post_data_json)
                rank_dat1a = await rank_respons1e.json()
                # 等待近7天数据被拦截并处理
                print("\n✅ --- 成功截获到详情页近7天数据响应 ---")
                print(json.dumps(rank_dat1a, indent=2, ensure_ascii=False))
                print("--- 详情页近7天数据结束 ---\n")
            except TimeoutError:
                print(f"❌ 操作超时：在点击“近7天”后，30秒内未捕获到包含 '{DETAIL_API_URL_PART}' 的网络请求。")
                print("💡 可能原因：详情页默认显示的就是“近7天”数据，导致点击后没有发出新的网络请求。")
            finally:
                pass
                # 移除路由拦截，避免影响后续操作
                # await page.unroute(lambda url: DETAIL_API_URL_PART in url, handle_detail_api_route)

        else:
            print("❌ 未能从榜单数据中找到 'promotions' 列表，无法继续。")

    except TimeoutError:
        print("❌ 操作超时，请检查网络或页面元素是否已更改。")
    except Exception as e:
        print(f"❌ 脚本执行出错: {e}")
    finally:
        print("正在保存当前会话状态 (cookies)...")
        await context.storage_state(path=STORAGE_STATE_FILE)
        print(f"会话状态已成功保存到: {STORAGE_STATE_FILE}")
        
        await context.close()
        await browser.close()
        print("浏览器已关闭。")


async def main():
    """异步主入口"""
    async with async_playwright() as playwright:
        await run(playwright)


if __name__ == "__main__":
    print("开始执行 Playwright 抓取脚本...")
    try:
        import playwright
    except ImportError:
        print("错误：未找到 'playwright' 库。")
        print("请先通过 pip 安装：pip install playwright")
        print("然后运行：playwright install")
        exit(1)
        
    asyncio.run(main())