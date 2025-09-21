import asyncio
import json
import random
import re
import time
from pathlib import Path
from playwright.async_api import async_playwright, Playwright, TimeoutError, Response

class Config:
    """Configuration constants for the scraper."""
    RANK_URL = "https://buyin.jinritemai.com/dashboard/merch-picking-hall/rank?btm_ppre=a10091.b24215.c68160.d839440_i16852609794&btm_pre=a10091.b71710.c68160.d839440_i1482933506&btm_show_id=ebf82770-5d02-48ed-9f92-c1a75d6fd2f3&pre_universal_page_params_id=&universal_page_params_id=e0b97666-5e57-41ab-850a-5418bb06acad"
    RANK_API_URL_PART = "pc/leaderboard/center/pmt"
    DETAIL_API_URL_PART = "pc/selection/decision/pack_detail"
    DETAIL_PAGE_URL_TEMPLATE = "https://buyin.jinritemai.com/dashboard/merch-picking-library/merch-promoting?id={}"
    STORAGE_STATE_FILE = Path("storage_state.json")
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
    LOGIN_TIMEOUT = 300000  # 5 minutes
    REQUEST_TIMEOUT = 30000  # 30 seconds

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

def _is_rank_data_response(response: Response) -> bool:
    """Check if the response is for the rank data API."""
    return Config.RANK_API_URL_PART in response.url

def _is_detail_core_data_response(response: Response) -> bool:
    """Check if the response is for the detail page core data API."""
    if Config.DETAIL_API_URL_PART not in response.url or response.request.method != "POST":
        return False
    try:
        post_data = response.request.post_data_json
        return post_data.get("data_module") == "core"
    except (json.JSONDecodeError, AttributeError):
        return False

def _is_detail_7day_data_response(response: Response) -> bool:
    """Check if the response is for the detail page 7-day data API."""
    if Config.DETAIL_API_URL_PART not in response.url or response.request.method != "POST":
        return False
    try:
        post_data = response.request.post_data_json
        return (
            post_data.get("data_module") == "dynamic" and
            post_data.get("dynamic_params", {}).get("promotion_data_params", {}).get("time_range") == '7'
        )
    except (json.JSONDecodeError, AttributeError):
        return False

async def get_response_json(response: Response, description: str):
    """Safely get JSON from a response and print it."""
    print(f"\n✅ --- Successfully intercepted {description} ---")
    try:
        data = await response.json()
        # print(json.dumps(data, indent=2, ensure_ascii=False))
        # print(f"--- End of {description} ---")
        return data
    except json.JSONDecodeError:
        print(f"❌ Could not parse {description} response as JSON.")
        print("Received response text:")
        print(await response.text())
        return None


async def cat_run(page, page_detail, cat, max_count=None):
    data_list = []
    try:
        async with page.expect_response(_is_rank_data_response, timeout=Config.REQUEST_TIMEOUT) as response_info:
            await page.locator("div").filter(has_text=re.compile(r"^" + cat + "$")).click()
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(10)
        rank_response = await response_info.value
        rank_data = await get_response_json(rank_response, "Rank Data")

        promotions = rank_data.get("data", {}).get("promotions") if rank_data else []
        if not promotions:
            print("❌ Could not find 'promotions' in rank data. Cannot proceed.")
            return data_list
        # 循环访问详情页
        for index, item in enumerate(promotions):
            print("随机睡眠...等待")
            # 每分钟抓取n个商品
            count_pers = 3
            # 随机睡眠15-20秒
            time.sleep(random.uniform(60/count_pers - 5, 60/count_pers))
            if max_count is not None and index + 1 >= max_count:
                break
            first_product_id = item.get("promotion_id")
            if not first_product_id:
                print("❌ Could not find 'product_id' for the first product. Cannot proceed.")
                continue

            detail_page_url = Config.DETAIL_PAGE_URL_TEMPLATE.format(first_product_id)
            print(f"Found product ID: {first_product_id}")
            print(f"Navigating to detail page: {detail_page_url}")

            # --- Fetch Core Data ---
            async with page_detail.expect_response(_is_detail_core_data_response, timeout=Config.REQUEST_TIMEOUT) as core_response_info:
                await page_detail.goto(detail_page_url, wait_until="domcontentloaded")

            core_response = await core_response_info.value
            detail_data = await get_response_json(core_response, "Detail Page Core Data")
            if not detail_data:
                continue

            # --- Fetch 7-Day Data ---
            print("Clicking '近7天' (Last 7 days) to get 7-day data...")
            try:
                async with page_detail.expect_response(_is_detail_7day_data_response, timeout=Config.REQUEST_TIMEOUT) as seven_day_response_info:
                    await page_detail.get_by_text("近7天", exact=True).click()
                seven_day_response = await seven_day_response_info.value
                seven_data = await get_response_json(seven_day_response, "Detail Page 7-Day Data")
                if not seven_data:
                    continue
                data_list.append({
                    "rank": index,
                    "category": cat,
                    "detail_data": detail_data,
                    "seven_data": seven_data,
                })
            except TimeoutError:
                print(f"❌ Timed out waiting for 7-day data after clicking '近7天'.")
                print("💡 This might happen if the 7-day data was already loaded by default.")
                continue
    except TimeoutError:
        print(f"❌ Timed out waiting for 7-day data after clicking '近7天'.")
        print("💡 This might happen if the 7-day data was already loaded by default.")
    return data_list


async def run(playwright: Playwright):
    """Main execution function."""
    # !!! 重要提示 !!!
    # 1. 请将下面的 <YOUR_WINDOWS_USERNAME> 替换为您的实际 Windows 用户名。
    # 2. 在运行脚本之前，请确保已关闭所有 Chrome 浏览器实例。
    user_data_dir = r"C:\Users\gsma\AppData\Local\Google\Chrome\User Data"
    # 您的Chrome浏览器可执行文件路径
    executable_path = r"C:\Users\gsma\AppData\Local\Google\Chrome\Application\chrome.exe"

    context = await playwright.chromium.launch_persistent_context(
        user_data_dir,
        headless=False,
        executable_path=executable_path,
        user_agent=Config.USER_AGENT,
        # args=['--profile-directory=Default'] # 如果您有多个配置文件，可以指定使用某一个
    )

    await context.add_init_script(INIT_SCRIPT)
    # 持久化上下文通常会有一个默认的空白页面，我们获取第一个实际的页面
    page = context.pages[0] if context.pages else await context.new_page()

    try:
        print(f"Navigating to rank page: {Config.RANK_URL}")
        await page.goto(Config.RANK_URL, wait_until="domcontentloaded")

        # 如果您在浏览器中已经登录，则可能不需要此登录检查
        if "login" in page.url:
            print("Login required. Please log in in the browser window.")
            print("Waiting for successful login...")
            await page.wait_for_url(lambda url: "login" not in url, timeout=Config.LOGIN_TIMEOUT)
            print("Login successful. Continuing script.")

        await page.wait_for_timeout(random.randint(1000, 2500))
        print("Clicking '趋势榜' (Trend Rank)...")
        await page.get_by_text("趋势榜", exact=True).click()

        await page.wait_for_timeout(random.randint(1000, 2500))

        # 选择过滤条件
        print("Clicking '短视频' (Short Video) and waiting for rank data...")
        await page.locator("div").filter(has_text=re.compile(r"^体验分$")).click()
        await page.get_by_role("menuitem", name="≥85").click()
        await page.get_by_text("短视频", exact=True).click()

        # 新开一个界面，给详情用
        page_detail = await context.new_page()
        # 循环选择类目，触发加载
        for cat in [
            # "服饰内衣",
            # "美妆",
            # "食品饮料",
            "个护家清",
            "鞋靴箱包",
            # "钟表配饰",
            "母婴宠物",
            # "图书教育",
            # "智能家居",
            # "3C数码产品",
            # "运动户外",
            # "玩具乐器",
            # "生鲜"
        ]:
            print("触发类目", cat)
            try:
                data_list = await cat_run(page, page_detail, cat, 2)
                if data_list:
                    print("数据保存中...")
                    with open("data/" + cat + ".json", "w", encoding="utf-8") as f:
                        f.write(json.dumps(data_list, ensure_ascii=False))
                    print("数据保存完毕")
            except Exception as e:
                continue
            time.sleep(0.5)
    except TimeoutError:
        print("❌ Operation timed out. Please check your network or if the page structure has changed.")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
    finally:
        print("Script finished. Closing browser context.")
        # 因为我们使用的是持久化上下文，所以不需要保存存储状态。
        # 我们只关闭上下文，而不是整个浏览器。
        await context.close()
        print("Browser context closed.")


async def main():
    """Async main entry point."""
    async with async_playwright() as playwright:
        await run(playwright)


if __name__ == "__main__":
    print("Starting Playwright data scraping script...")
    try:
        import playwright
    except ImportError:
        print("Error: 'playwright' library not found.")
        print("Please install it via pip: pip install playwright")
        print("And then run: playwright install")
        exit(1)
        
    asyncio.run(main())
