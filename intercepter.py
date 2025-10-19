import asyncio
import datetime
import json
import os
import random
import re
import time
from pathlib import Path
from playwright.async_api import async_playwright, Playwright, TimeoutError, Response
from playwright_stealth import Stealth


class Config:
    """Configuration constants for the scraper."""
    RANK_URL = "https://buyin.jinritemai.com/dashboard/merch-picking-hall/rank?btm_ppre=a10091.b24215.c68160.d839440_i16852609794&btm_pre=a10091.b71710.c68160.d839440_i1482933506&btm_show_id=ebf82770-5d02-48ed-9f92-c1a75d6fd2f3&pre_universal_page_params_id=&universal_page_params_id=e0b97666-5e57-41ab-850a-5418bb06acad"
    RANK_API_URL_PART = "pc/leaderboard/center/pmt"
    DETAIL_API_URL_PART = "pc/selection/decision/pack_detail"
    DETAIL_PAGE_URL_TEMPLATE = "https://buyin.jinritemai.com/dashboard/merch-picking-library/merch-promoting?id={}"
    STORAGE_STATE_FILE = Path("storage_state.json")
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
    LOGIN_TIMEOUT = 3000000  # 5 minutes
    REQUEST_TIMEOUT = 300000  # 30 seconds

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

def _is_detail_30day_data_response(response: Response) -> bool:
    """Check if the response is for the detail page 30-day data API."""
    if Config.DETAIL_API_URL_PART not in response.url or response.request.method != "POST":
        return False
    try:
        post_data = response.request.post_data_json
        return post_data.get("data_module") == "pc-non-core"
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

def sleep_catch(catch_per_minute):
    # 每分钟抓取n个商品
    sleep_time = random.uniform(60 / catch_per_minute - 10, 60 / catch_per_minute + 10)
    print(f"随机睡眠...等待{sleep_time}s")
    time.sleep(sleep_time)


async def cat_run(page, page_detail, cat, max_count=None, catch_per_minute=3, point_id=None):
    data_list = []
    try:
        if not point_id:
            async with page.expect_response(_is_rank_data_response, timeout=Config.REQUEST_TIMEOUT) as response_info:
                await page.locator("div").filter(has_text=re.compile(r"^" + cat + "$")).click()

            rank_response = await response_info.value
            rank_data = await get_response_json(rank_response, "Rank Data")

            promotions = rank_data.get("data", {}).get("promotions") if rank_data else []
            if not promotions:
                print("❌ Could not find 'promotions' in rank data. Cannot proceed.")
                return data_list
        else:
            promotions = [{"promotion_id": point_id}]
        # 今日的日期
        today = time.strftime("%Y-%m-%d", time.localtime())
        # 存储地址
        cache_dir = f"data/{today}/{cat}"
        # 目录不存在则创建
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        # 循环访问详情页
        for index, item in enumerate(promotions):
            print(f"抓取{index}：{datetime.datetime.now()}")
            # 随机睡眠15-20秒
            if max_count is not None and index + 1 > max_count:
                print(f"已抓取指定数量的商品，停止抓取:{datetime.datetime.now()}")
                break
            first_product_id = item.get("promotion_id")
            if not first_product_id:
                print("❌ Could not find 'product_id' for the first product. Cannot proceed.")
                continue
            # 存储文件地址
            file_path = f"{cache_dir}/{first_product_id}.json"
            if os.path.exists(file_path):
                print(f"数据已存在，跳过：{file_path}")
                continue

            # if index != 0:
            #     # 每分钟抓取n个商品
            #     sleep_time = random.uniform(60 / catch_per_minute - 10, 60 / catch_per_minute + 10)
            #     print(f"随机睡眠...等待{sleep_time}s")
            #     time.sleep(sleep_time)

            detail_page_url = Config.DETAIL_PAGE_URL_TEMPLATE.format(first_product_id)
            print(f"Found product ID: {first_product_id}")
            print(f"Navigating to detail page: {detail_page_url}")

            try:
                # --- Fetch Core and 30-Day Data ---
                print("Waiting for detail page core and 30-day data...")
                async with page_detail.expect_response(_is_detail_core_data_response,
                                                       timeout=Config.REQUEST_TIMEOUT) as core_response_info, \
                        page_detail.expect_response(_is_detail_30day_data_response,
                                                    timeout=Config.REQUEST_TIMEOUT) as thirty_day_response_info:
                    await page_detail.goto(detail_page_url, wait_until="domcontentloaded")

                core_response = await core_response_info.value
                detail_data = await get_response_json(core_response, "Detail Page Core Data")

                thirty_day_response = await thirty_day_response_info.value
                thirty_data = await get_response_json(thirty_day_response, "Detail Page 30-Day Data")

                if not detail_data or not thirty_data:
                    print("❌ Could not get both core and 30-day data.")
                    sleep_catch(catch_per_minute)
                    continue

                if "请稍后再试" in json.dumps(detail_data, ensure_ascii=False) or "请稍后再试" in json.dumps(thirty_data,
                                                                                                        ensure_ascii=False):
                    # 出现限制，退出操作
                    print(f"出现限制，退出操作，当前时间：{datetime.datetime.now()}")
                    break

                save_data = {
                    "rank": index,
                    "category": cat,
                    "detail_data": detail_data,
                    "thirty_data": thirty_data,
                }
                data_list.append(save_data)
                print("数据保存中...:" + file_path)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(json.dumps(save_data, indent=4, ensure_ascii=False))
                print("数据保存完毕")

                sleep_catch(catch_per_minute)

            except TimeoutError:
                print(f"❌ Timed out waiting for core or 30-day data.")
                sleep_catch(catch_per_minute)
                continue
    except TimeoutError:
        print(f"❌ Timed out waiting for 30-day data after clicking '近30天'.")
        print("💡 This might happen if the 30-day data was already loaded by default.")
    return data_list


async def get_chrome(playwright, mode, remote_config):
    if mode == "remote":
        """Main execution function."""
        # !!! 重要提示 !!!
        # 1. 请将下面的 <YOUR_WINDOWS_USERNAME> 替换为您的实际 Windows 用户名。
        # 2. 在运行脚本之前，请确保已关闭所有 Chrome 浏览器实例。

        user_data_dir = remote_config["user_data_dir"]
        executable_path = remote_config["executable_path"]

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
        browser = None
    else:
        storage_state = str(Config.STORAGE_STATE_FILE.absolute()) if Config.STORAGE_STATE_FILE.exists() else None
        if storage_state:
            print(f"Found session file at {Config.STORAGE_STATE_FILE}, attempting to reuse it.")
        else:
            print("No local session file found, proceeding with a new session (may require login).")

        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(
            storage_state=storage_state,
            user_agent=Config.USER_AGENT
        )
        await context.add_init_script(INIT_SCRIPT)
        page = await context.new_page()

    # 处理防止检测
    stealth = Stealth()
    await stealth.apply_stealth_async(page)
    return browser, page, context

async def run(cats, playwright: Playwright, mode, remote_config, catch_num, catch_per_minute, point_id):
    browser, page, context = await get_chrome(playwright, mode, remote_config)
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
        # 处理防止检测
        stealth = Stealth()
        await stealth.apply_stealth_async(page_detail)
        # 循环选择类目，触发加载
        for cat in cats:
            print("触发类目", cat)
            try:
                data_list = await cat_run(page, page_detail, cat, catch_num, catch_per_minute, point_id)
            except Exception as e:
                continue
    except TimeoutError:
        print("❌ Operation timed out. Please check your network or if the page structure has changed.")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
    finally:
        print("Script finished. Closing browser context.")
        if mode != "remote":
            print("Saving current session state (cookies, etc.)...")
            await context.storage_state(path=Config.STORAGE_STATE_FILE)
            print(f"Session state saved to: {Config.STORAGE_STATE_FILE}")
            await context.close()
            await browser.close()
            print("Browser closed.")
        else:
            # 因为我们使用的是持久化上下文，所以不需要保存存储状态。
            # 我们只关闭上下文，而不是整个浏览器。
            await context.close()
            print("Browser context closed.")


async def main():
    user_data_dir = r"C:\Users\gsma\AppData\Local\Google\Chrome\User Data"
    executable_path = r"C:\Users\gsma\AppData\Local\Google\Chrome\Application\chrome.exe"
    # 每个榜单抓取的数据量
    catch_num = 18
    # 没分钟抓几个
    catch_per_minute = 0.1
    cats = [
        # "服饰内衣",
        # "美妆",
        # "食品饮料",
        # 一个账号一个，然后2分钟一次请求
        "个护家清",
        ## "鞋靴箱包",
        # "钟表配饰",
        ## "母婴宠物",
        # "图书教育",
        # "智能家居",
        # "3C数码产品",
        # "运动户外",
        # "玩具乐器",
        # "生鲜"
    ]
    async with async_playwright() as playwright:
        await run(cats, playwright, "remote", {
            "user_data_dir": user_data_dir,
            "executable_path": executable_path,
        }, catch_num, catch_per_minute, None)


async def main_point():
    user_data_dir = r"C:\Users\gsma\AppData\Local\Google\Chrome\User Data"
    executable_path = r"C:\Users\gsma\AppData\Local\Google\Chrome\Application\chrome.exe"
    # 每个榜单抓取的数据量
    catch_num = 18
    # 没分钟抓几个
    catch_per_minute = 0.1
    point_id = "3775472243623199049"
    # 指定抓去一个
    cats = ["个护家清"]
    async with async_playwright() as playwright:
        await run(cats, playwright, "remote", {
            "user_data_dir": user_data_dir,
            "executable_path": executable_path,
        }, catch_num, catch_per_minute, point_id)


if __name__ == "__main__":
    print("Starting Playwright data scraping script...")
    try:
        import playwright
    except ImportError:
        print("Error: 'playwright' library not found.")
        print("Please install it via pip: pip install playwright")
        print("And then run: playwright install")
        exit(1)

    # asyncio.run(main())
    asyncio.run(main_point())
