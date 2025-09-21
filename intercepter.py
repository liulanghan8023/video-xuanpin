import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, Playwright, TimeoutError

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

async def run(playwright: Playwright):
    """主执行函数"""
    
    # 步骤0: 如果存在本地Cookie文件，则加载，实现免登录
    storage_state = str(STORAGE_STATE_FILE.absolute()) if STORAGE_STATE_FILE.exists() else None
    if storage_state:
        print(f"检测到会话文件 {STORAGE_STATE_FILE}，将尝试使用它免登录。")
    else:
        print("未找到本地会话文件，将进行首次登录。")

    # 启动浏览器，可以设置 headless=True 实现无头模式
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(storage_state=storage_state)
    page = await context.new_page()

    try:
        # 步骤1: 打开目标网址
        print(f"正在打开榜单页面: {RANK_URL}")
        await page.goto(RANK_URL, wait_until="domcontentloaded")

        # 如果页面跳转到了登录页，则等待用户手动登录
        if "login" in page.url:
            print("检测到需要登录，请在弹出的浏览器窗口中手动登录。")
            print("登录成功后，脚本将自动从当前页面继续执行...")
            # 等待页面URL不再包含login，超时设置为5分钟
            await page.wait_for_url(lambda url: "login" not in url, timeout=300000)
            print("登录成功，继续执行脚本。")

        # 步骤2: 找到并点击 "趋势榜"
        print("点击 '趋势榜'...")
        # 根据HTML结构，直接通过文本来定位更可靠
        await page.get_by_text("趋势榜", exact=True).click()

        # 步骤3 & 4: 点击 "本周" 和 "短视频"，并等待相应的网络请求
        print("点击 '短视频'，并等待榜单数据加载...")
        # 使用 page.expect_response 作为上下文管理器，可以精准捕获在 'with' 代码块内触发的网络响应
        async with page.expect_response(lambda r: RANK_API_URL_PART in r.url, timeout=30000) as response_info:
            # 根据新的HTML结构，使用 get_by_text 点击对应的标签

            
            print("点击 '短视频'...")
            await page.get_by_text("短视频", exact=True).click()

        rank_response = await response_info.value
        print("\n✅ --- 成功截获到榜单数据 ---")
        rank_data = await rank_response.json()
        # 使用 json.dumps 美化输出
        print(json.dumps(rank_data, indent=2, ensure_ascii=False))
        print("--- 榜单数据结束 ---\n")



        # 步骤5: 解析数据，构造并访问详情页
        promotions = rank_data.get("data", {}).get("promotions")
        if promotions:
            # 只处理第一个商品
            first_product_id = promotions[0]["product_id"]
            detail_page_url = DETAIL_PAGE_URL_TEMPLATE.format(first_product_id)
            
            print(f"成功解析到商品ID: {first_product_id}")
            print(f"正在打开详情页: {detail_page_url}")
            await page.goto(detail_page_url, wait_until="domcontentloaded")

            # 步骤6: 点击 "近7天" 并拦截详情页数据
            print("等待详情页加载并点击 '近7天'...")
            try:
                # 确保页面网络空闲，所有初始请求已完成，避免时序问题
                await page.wait_for_load_state('networkidle')
                # 使用 page.expect_response 作为上下文管理器，可以精准捕获在 'with' 代码块内触发的网络响应
                async with page.expect_response(lambda r: DETAIL_API_URL_PART in r.url, timeout=30000) as detail_response_info:
                    await page.get_by_text("近7天", exact=True).click()

                detail_response = await detail_response_info.value
                print("\n✅ --- 成功截获到详情页数据 ---")
                detail_data = await detail_response.json()
                print(json.dumps(detail_data, indent=2, ensure_ascii=False))
                print("--- 详情页数据结束 ---\n")

            except TimeoutError:
                print(f"❌ 操作超时：在点击“近7天”后，30秒内未捕获到包含 '{DETAIL_API_URL_PART}' 的网络请求。")
                print("💡 可能原因：详情页默认显示的就是“近7天”数据，导致点击后没有发出新的网络请求。")

        else:
            print("❌ 未能从榜单数据中找到 'promotions' 列表，无法继续。")

    except TimeoutError:
        print("❌ 操作超时，请检查网络或页面元素是否已更改。")
    except Exception as e:
        print(f"❌ 脚本执行出错: {e}")
    finally:
        # 步骤0 (保存): 无论成功与否，都保存当前会话状态，以便下次运行
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
    # 检查依赖
    try:
        import playwright
    except ImportError:
        print("错误：未找到 'playwright' 库。")
        print("请先通过 pip 安装：pip install playwright")
        print("然后运行：playwright install")
        exit(1)
        
    asyncio.run(main())
