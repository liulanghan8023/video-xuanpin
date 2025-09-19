import os
import json
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from bs4 import BeautifulSoup
import re

STORAGE_STATE_FILE = 'storage_state.json'
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"

def parse_price(price_str):
    if not price_str:
        return 0
    price_str = price_str.replace('¥', '')
    if '万' in price_str:
        price_str = price_str.replace('万', '')
        return float(price_str) * 10000
    return float(price_str)

def parse_sales(sales_str):
    if not sales_str:
        return 0
    if '万' in sales_str:
        sales_str = sales_str.replace('万', '').replace('+', '')
        return int(float(sales_str) * 10000)
    return int(sales_str)

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        context_options = {
            'user_agent': USER_AGENT
        }
        if os.path.exists(STORAGE_STATE_FILE):
            with open(STORAGE_STATE_FILE, 'r', encoding='utf-8') as f:
                try:
                    storage_state = json.load(f)
                    # Merge the loaded state with our options
                    context_options['storage_state'] = storage_state
                    print("已加载保存的登录信息。")
                except json.JSONDecodeError:
                    print("登录信息文件已损坏，将创建新的登录会话。")
        else:
            print("未找到登录信息，请手动登录。")

        context = browser.new_context(**context_options)
        page = context.new_page()

        try:
            print("正在导航到页面...")
            page.goto("https://buyin.jinritemai.com/dashboard/merch-picking-hall/rank?btm_ppre=a0.b0.c0.d0&btm_pre=a10091.b24215.c68160.d839440_i1482933506&btm_show_id=5c7ac95d-1630-4da4-8849-efb657bb97db&pre_universal_page_params_id=&universal_page_params_id=031b9a6c-1026-4f6a-a838-7c18bd578f86", wait_until="domcontentloaded", timeout=60000)
            
            print("页面加载中，等待网络稳定...")
            page.wait_for_load_state('networkidle', timeout=60000)

            print(f"页面标题: {page.title()}")

            # Check for network error message and try reloading once.
            try:
                error_selector = 'text="当前网络不稳定"'
                page.wait_for_selector(error_selector, timeout=5000)
                print("检测到网络不稳定提示，尝试刷新页面...")
                page.reload()
                print("等待页面刷新后网络稳定...")
                page.wait_for_load_state('networkidle', timeout=30000)
                print("页面已刷新。")
            except PlaywrightError:
                # This is the good path: the error message did not appear.
                print("未检测到网络不稳定提示，加载成功。")

            print("\n页面加载成功，正在查找并点击'趋势榜'...")
            try:
                # Use a robust selector based on role and name
                trend_list_tab = page.get_by_role("tab", name="趋势榜")
                trend_list_tab.click()
                print("已成功点击'趋势榜'。")
                
                # After clicking, wait for the content to load
                print("等待趋势榜内容加载...")
                page.wait_for_load_state('networkidle', timeout=30000)
                print("趋势榜内容已加载。")

                print("\n正在查找并点击'本周'按钮...")
                try:
                    # Use a more direct and robust locator
                    this_week_button = page.locator('label:has-text("本周")')
                    
                    # Explicitly wait for the button to be visible
                    print("等待'本周'按钮可见...")
                    this_week_button.wait_for(state='visible', timeout=10000) # 10s timeout
                    
                    this_week_button.click()
                    print("已成功点击'本周'按钮。")

                    # Wait for the data to update
                    print("等待'本周'数据加载...")
                    page.wait_for_load_state('networkidle', timeout=30000)
                    print("'本周'数据已加载。")

                    print("\n正在查找并点击'短视频'按钮...")
                    try:
                        # Apply the same robust pattern here
                        short_video_button = page.locator('label:has-text("短视频")')
                        
                        print("等待'短视频'按钮可见...")
                        short_video_button.wait_for(state='visible', timeout=10000)

                        short_video_button.click()
                        print("已成功点击'短视频'按钮。")

                        print("等待'短视频'数据加载...")
                        page.wait_for_load_state('networkidle', timeout=30000)
                        print("'短视频'数据已加载。")

                        print("\n等待界面渲染...")
                        page.wait_for_timeout(3000) # Extra 3-second wait for UI to settle. 

                        print("开始模拟向上滚动页面...")
                        for i in range(2):
                            print(f"第 {i+1}/2 次向上滚动...")
                            page.keyboard.press("PageUp")
                            page.wait_for_timeout(2000)
                        print("滚动完成。")

                        print("获取商品列表并逐个点击...")
                        items_locator = page.locator("tr.auxo-table-row")
                        count = items_locator.count()
                        print(f"找到 {count} 个商品。")

                        for i in range(count):
                            # Re-fetch locators in each iteration to avoid stale element issues
                            item_locator = page.locator("tr.auxo-table-row").nth(i)
                            name_element = item_locator.locator('div.index_module__title____4ca9')

                            name = "未知名称"
                            if name_element.count() > 0:
                                name = name_element.inner_text().strip()
                            
                            print(f"--- 处理第 {i+1}/{count} 个商品: {name} ---")

                            try:
                                # Context manager to handle the new page
                                with context.expect_page(timeout=10000) as new_page_info:
                                    # Click the element to open the detail page
                                    if name_element.count() > 0:
                                        name_element.click()
                                    else:
                                        item_locator.click()
                                
                                detail_page = new_page_info.value
                                
                                print("  等待详情页加载完成...")
                                detail_page.wait_for_load_state('networkidle', timeout=60000)
                                print(f"  详情页 '{detail_page.title()}' 加载成功。")

                                # Click the "7天" button
                                print("  点击'近7天'按钮...")
                                seven_day_button = detail_page.locator('div.index_module__switchItem____9ac7:has-text("近7天")')
                                if seven_day_button.count() > 0:
                                    seven_day_button.click()
                                    print("  等待数据更新...")
                                    detail_page.wait_for_load_state('networkidle', timeout=30000)
                                    print("  '近7天'数据已加载。")
                                else:
                                    print("  未找到'近7天'按钮。")

                                print("  开始提取详细数据...")
                                
                                # Get the HTML content of the detail page
                                html_content = detail_page.content()

                                # Parse the HTML content with BeautifulSoup
                                soup = BeautifulSoup(html_content, 'html.parser')

                                data = {}

                                # 1. 体验分
                                experience_score_element = soup.find('span', class_='index_module__bigNum____1d3f')
                                if experience_score_element:
                                    data['experience_score'] = int(experience_score_element.text)

                                # 2. 商品评分
                                product_score_element = soup.find('div', class_='index_module__textLine____1d3f', string='商品')
                                if product_score_element:
                                    score_element = product_score_element.find_previous_sibling('div').find('span', class_='index_module__smallNum____1d3f')
                                    if score_element:
                                        data['product_score'] = int(score_element.text)

                                # 3. 物流评分
                                logistics_score_element = soup.find('div', class_='index_module__textLine____1d3f', string='物流')
                                if logistics_score_element:
                                    score_element = logistics_score_element.find_previous_sibling('div').find('span', class_='index_module__smallNum____1d3f')
                                    if score_element:
                                        data['logistics_score'] = int(score_element.text)

                                # 4. 商家评分
                                merchant_score_element = soup.find('div', class_='index_module__textLine____1d3f', string='商家')
                                if merchant_score_element:
                                    score_element = merchant_score_element.find_previous_sibling('div').find('span', class_='index_module__smallNum____1d3f')
                                    if score_element:
                                        data['merchant_score'] = int(score_element.text)

                                # 5. 到手价
                                price_element = soup.find('div', class_='index_module__dataTitle____0bd5', string='到手价')
                                if price_element:
                                    price_content_element = price_element.find_next_sibling('div', class_='index_module__dataContent____0bd5')
                                    if price_content_element:
                                        price_text = price_content_element.contents[0].strip()
                                        price = re.search(r'¥(\d+\.?\d*)', price_text)
                                        old_price_element = price_content_element.find('span', class_='index_module__lineThrough____0bd5')
                                        if old_price_element:
                                            old_price = re.search(r'¥(\d+\.?\d*)', old_price_element.text)
                                            data['original_price'] = parse_price(old_price.group(1)) if old_price else 0
                                        data['price'] = parse_price(price.group(1)) if price else 0

                                # 6. 佣金率|佣金
                                commission_element = soup.find('div', class_='index_module__dataTitle____0bd5', string='佣金')
                                if commission_element:
                                    commission_content_element = commission_element.find_next_sibling('div', class_='index_module__dataContent____0bd5')
                                    if commission_content_element:
                                        commission_rate = commission_content_element.find('span').text.replace('%', '')
                                        commission = commission_content_element.find('span', class_='index_module__smallText____0bd5').text.replace('赚', '')
                                        data['commission_rate'] = float(commission_rate)
                                        data['commission'] = float(commission)

                                # 7. 好评率
                                praise_rate_element = soup.find('div', class_='index_module__dataTitle____0bd5', string='好评率')
                                if praise_rate_element:
                                    praise_rate_content_element = praise_rate_element.find_next_sibling('div', class_='index_module__dataContent____0bd5')
                                    if praise_rate_content_element:
                                        praise_rate = praise_rate_content_element.text.replace('%', '')
                                        data['praise_rate'] = float(praise_rate)

                                # 8. 已售数量
                                sales_element = soup.find('div', class_='index_module__dataTitle____0bd5', string='已售')
                                if sales_element:
                                    sales_content_element = sales_element.find_next_sibling('div', class_='index_module__dataContent____0bd5')
                                    if sales_content_element:
                                        sales_text = sales_content_element.find('div').text
                                        unit = sales_content_element.find('div', class_='index_module__suffix____0bd5').text
                                        if '万' in unit:
                                            data['sales'] = parse_sales(sales_text + '万')
                                        else:
                                            data['sales'] = parse_sales(sales_text)

                                # 9. 带货人数
                                influencer_count_element = soup.find(lambda tag: tag.name == 'div' and 'index_module__dataTitle____0bd5' in tag.get('class', []) and '带货人数' in tag.text)
                                if influencer_count_element:
                                    influencer_count_content_element = influencer_count_element.find_next_sibling('div', class_='index_module__dataContent____0bd5')
                                    if influencer_count_content_element:
                                        count = influencer_count_content_element.find('div').text
                                        data['influencer_count'] = int(count) if count.isdigit() else 0

                                # 13. 图片列表
                                image_list_element = soup.find('div', class_='auxo-carousel')
                                if image_list_element:
                                    images = [img['src'] for img in image_list_element.find_all('img')]
                                    data['image_list'] = images

                                print(json.dumps(data, indent=4, ensure_ascii=False))


                                print("  关闭详情页...")
                                detail_page.close()
                                print("  详情页已关闭。")

                                # Wait a moment for the original page to be ready
                                page.wait_for_timeout(1000)

                            except PlaywrightError as e:
                                print(f"  处理商品 '{name}' 时发生错误: {e}")
                                print("  继续下一个商品。")
                                # Check if a stray page was opened and close it
                                if len(context.pages) > 1:
                                    stray_page = context.pages[-1]
                                    if stray_page != page:
                                        stray_page.close()

                    except PlaywrightError as e_video:
                        print(f"错误：无法找到或点击'短视频'按钮。请检查页面是否已更改。\n详细信息: {e_video}")

                except PlaywrightError as e_week:
                    print(f"错误：无法找到或点击'本周'按钮。请检查页面是否已更改。\n详细信息: {e_week}")

            except PlaywrightError as e_trend:
                print(f"错误：无法找到或点击'趋势榜'。请检查页面是否已更改。\n详细信息: {e_trend}")

            print("\n请在浏览器窗口中操作。完成操作或登录后，请手动关闭浏览器窗口。")
            print("关闭窗口后，程序将自动保存您的登录状态。")

            # Wait for the page to be closed by the user. This is a blocking call.
            page.wait_for_event('close')
            print("检测到页面已关闭。")

        except PlaywrightError as e:
            print(f"操作被中断或浏览器已关闭: {e}")
        finally:
            # This block will execute after the user closes the page, or if an error occurs.
            try:
                storage = context.storage_state()
                with open(STORAGE_STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(storage, f, indent=2)
                print(f"当前登录会话已保存到 {STORAGE_STATE_FILE}。")
            except PlaywrightError as e:
                print(f"无法保存会话状态，浏览器可能已强制关闭: {e}")
            
            print("正在关闭浏览器...")
            browser.close()

if __name__ == "__main__":
    run()
