import json
import sqlite3
from pathlib import Path
import re
import os

# 数据库文件路径
DB_FILE = Path(__file__).parent / "data.db"
# 数据目录路径
DATA_DIR = Path(__file__).parent / "data"

def init_db():
    """初始化数据库，创建表"""
    # 删除旧的数据库文件以应用新结构
    if DB_FILE.exists():
        print(f"发现旧的数据库文件 {DB_FILE}，正在删除...")
        os.remove(DB_FILE)

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        # 创建商品表 (新结构)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            date TEXT,
            product_id TEXT,
            promotion_id TEXT,
            category TEXT,
            title TEXT,
            cover TEXT,
            rank INTEGER,
            sold INTEGER,
            douyin_share_text TEXT,
            juliang_url TEXT,
            douyin_url TEXT,
            price REAL,
            commission_rate REAL,
            good_review_rate REAL,
            influencer_count INTEGER,
            shop_experience_score INTEGER,
            product_score INTEGER,
            logistics_score INTEGER,
            seller_score INTEGER,
            shop_name TEXT,
            source_json_filename TEXT,
            creation_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (date, product_id, promotion_id)
        )
        """)
        # 创建推广数据表 (新结构)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS promotion_data (
            date TEXT,
            product_id TEXT,
            promotion_id TEXT,
            time_range TEXT,
            category TEXT,
            type TEXT,
            total_sales_amount REAL,
            total_sales_amount_formatted TEXT,
            window_sales REAL,
            window_sales_formatted TEXT,
            image_text_sales REAL,
            image_text_sales_formatted TEXT,
            live_sales REAL,
            live_sales_formatted TEXT,
            video_sales REAL,
            video_sales_formatted TEXT,
            converting_influencers INTEGER,
            converting_contents INTEGER,
            order_conversion_rate REAL,
            order_conversion_rate_formatted TEXT,
            views INTEGER,
            video_sales_ratio REAL,
            video_view_sales_ratio REAL,
            source_json_filename TEXT,
            creation_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (date, product_id, promotion_id)
        )
        """)
        # 创建推广数据详情表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS promotion_data_detail (
            date TEXT,
            product_id TEXT,
            promotion_id TEXT,
            calculate_time TEXT,
            sales INTEGER,
            pv INTEGER,
            match_num INTEGER,
            order_conversion_rate REAL,
            sales_amount REAL,
            sales_content_num INTEGER,
            match_order_num INTEGER,
            format_order_conversion_rate TEXT,
            format_sales_amount TEXT,
            creation_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (date, product_id, promotion_id, calculate_time)
        )
        """)
        conn.commit()
        print("数据库和表已成功初始化 (新结构)。")

def get_json_value(data, path, default=None):
    """安全地从嵌套字典中获取值"""
    if not path:
        return default
    keys = path.split('.')
    for key in keys:
        if isinstance(data, dict) and key in data:
            data = data[key]
        else:
            return default
    return data

def process_json_file(file_path: Path, conn: sqlite3.Connection):
    """处理单个JSON文件并存入数据库"""
    print(f"正在处理文件: {file_path}")
    try:
        date_str = file_path.parts[-3]
        if not re.match(r'\d{4}-\d{2}-\d{2}', date_str):
            raise IndexError
    except IndexError:
        print(f"无法从路径 {file_path} 中提取日期，跳过。")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 检查视频销量，如果为0则跳过
    video_sales = get_json_value(data, 'thirty_data.data.model.content_data.calculate_data.video_sales', 0)
    if video_sales == 0:
        print(f"视频销量为0，跳过文件: {file_path}")
        return

    cursor = conn.cursor()

    # 提取关键ID
    product_id = get_json_value(data, 'detail_data.data.product_id')
    promotion_id = get_json_value(data, 'detail_data.data.promotion_id')
    source_filename = file_path.name

    if not all([product_id, promotion_id]):
        print(f"文件 {file_path} 缺少 product_id 或 promotion_id，跳过。")
        return

    # 检查商品数据是否存在
    cursor.execute("SELECT 1 FROM products WHERE date = ? AND product_id = ? AND promotion_id = ?",
                   (date_str, product_id, promotion_id))
    if cursor.fetchone():
        print(f"产品数据已存在: {date_str}, {product_id}, {promotion_id}")
    else:
        product_data = (
            date_str,
            product_id,
            promotion_id,
            get_json_value(data, 'category'),
            get_json_value(data, 'detail_data.data.model.product.product_base.title'),
            get_json_value(data, 'detail_data.data.model.product.product_base.cover'),
            get_json_value(data, 'rank', 0),
            get_json_value(data, 'detail_data.data.model.product.product_sales.sell_num', 0), # 已售
            get_json_value(data, 'detail_data.data.model.product.product_kol_info.kol_info.sample_token'),
            None,  # 巨量的url - Not specified
            get_json_value(data, 'detail_data.data.model.product.product_base.detail_url'), # 抖音的url
            get_json_value(data, 'detail_data.data.model.product.product_price.price_label.price', 0) / 100.0,
            get_json_value(data, 'detail_data.data.model.product.product_cos.cos_label.cos.cos_ratio', 0),
            get_json_value(data, 'detail_data.data.model.product.product_comment.good_ratio', 0),
            get_json_value(data, 'detail_data.data.model.product.product_match.author_num', 0), # 带货人数
            get_json_value(data, 'detail_data.data.model.shop.shop_exper_scores.shop_exper_score_label.exper_score.score'),
            get_json_value(data, 'detail_data.data.model.shop.shop_exper_scores.shop_exper_score_label.goods_score.score'),
            get_json_value(data, 'detail_data.data.model.shop.shop_exper_scores.shop_exper_score_label.logistics_score.score'),
            get_json_value(data, 'detail_data.data.model.shop.shop_exper_scores.shop_exper_score_label.service_score.score'),
            get_json_value(data, 'detail_data.data.model.shop.shop_base.shop_name'),
            source_filename
        )
        # The creation_time column is filled by default by the database
        cursor.execute("INSERT INTO products (date, product_id, promotion_id, category, title, cover, rank, sold, douyin_share_text, juliang_url, douyin_url, price, commission_rate, good_review_rate, influencer_count, shop_experience_score, product_score, logistics_score, seller_score, shop_name, source_json_filename) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", product_data)
        print(f"成功插入产品数据: {date_str}, {product_id}, {promotion_id}")

    # 推广数据表使用文件路径中的日期
    promo_date = date_str

    # 检查推广数据是否存在
    cursor.execute("SELECT 1 FROM promotion_data WHERE date = ? AND product_id = ? AND promotion_id = ?",
                   (promo_date, product_id, promotion_id))
    if cursor.fetchone():
        print(f"推广数据已存在: {promo_date}, {product_id}, {promotion_id}")
    else:
        # Extract sales data
        base_path = 'thirty_data.data.model.content_data.calculate_data.'
        window_sales = get_json_value(data, base_path + 'bind_shop_sales', 0)
        image_text_sales = get_json_value(data, base_path + 'image_text_sales', 0)
        live_sales = get_json_value(data, base_path + 'live_sales', 0)
        video_sales = get_json_value(data, base_path + 'video_sales', 0)
        views = get_json_value(data, base_path + 'video_pv', 0)

        # Calculate total sales for ratio
        total_sales_volume = window_sales + image_text_sales + live_sales + video_sales

        # Calculate ratios, handle division by zero
        video_sales_ratio = (video_sales / total_sales_volume) if total_sales_volume > 0 else 0
        video_view_sales_ratio = (views / video_sales) if video_sales > 0 else 0

        promotion_table_data = (
            promo_date,
            product_id,
            promotion_id,
            '30日',  # 时间范围
            get_json_value(data, 'category'), # 商品类目
            '视频',  # 类型
            get_json_value(data, base_path + 'video_sales_amount', 0) / 100.0,
            get_json_value(data, base_path + 'format_video_sales_amount'),
            window_sales,
            get_json_value(data, base_path + 'format_bind_shop_sales'),
            image_text_sales,
            get_json_value(data, base_path + 'format_image_text_sales'),
            live_sales,
            get_json_value(data, base_path + 'format_live_sales'),
            video_sales,
            get_json_value(data, base_path + 'format_video_sales'),
            get_json_value(data, base_path + 'video_match_order_num', 0),
            get_json_value(data, base_path + 'video_sales_content_num', 0),
            get_json_value(data, base_path + 'video_order_conversion_rate', 0),
            get_json_value(data, base_path + 'format_video_order_conversion_rate'),
            views,
            video_sales_ratio,
            video_view_sales_ratio,
            source_filename
        )
        # The creation_time column is filled by default by the database
        cursor.execute("""
            INSERT INTO promotion_data (
                date, product_id, promotion_id, time_range, category, type,
                total_sales_amount, total_sales_amount_formatted,
                window_sales, window_sales_formatted,
                image_text_sales, image_text_sales_formatted,
                live_sales, live_sales_formatted,
                video_sales, video_sales_formatted,
                converting_influencers, converting_contents,
                order_conversion_rate, order_conversion_rate_formatted,
                views, video_sales_ratio, video_view_sales_ratio,
                source_json_filename
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, promotion_table_data)
        print(f"成功插入推广数据: {promo_date}, {product_id}, {promotion_id}")

    # 处理推广数据详情
    calculate_data_list = get_json_value(data, 'thirty_data.data.model.promotion_data.calculate_data_list')
    if calculate_data_list and isinstance(calculate_data_list, list):
        for item in calculate_data_list:
            calculate_time = item.get('calculate_time')
            if not calculate_time:
                continue

            # 检查数据是否存在
            cursor.execute("SELECT 1 FROM promotion_data_detail WHERE date = ? AND product_id = ? AND promotion_id = ? AND calculate_time = ?",
                           (date_str, product_id, promotion_id, str(calculate_time)))
            if cursor.fetchone():
                print(f"推广数据详情已存在: {date_str}, {product_id}, {promotion_id}, {calculate_time}")
                continue

            detail_data = (
                date_str,
                product_id,
                promotion_id,
                str(calculate_time),
                item.get('sales', 0),
                item.get('pv', 0),
                item.get('match_num', 0),
                item.get('order_conversion_rate', 0),
                item.get('sales_amount', 0) / 100.0,
                item.get('sales_content_num', 0),
                item.get('match_order_num', 0),
                item.get('format_order_conversion_rate'),
                item.get('format_sales_amount')
            )
            cursor.execute("""
                INSERT INTO promotion_data_detail (
                    date, product_id, promotion_id, calculate_time, sales, pv, match_num,
                    order_conversion_rate, sales_amount, sales_content_num, match_order_num,
                    format_order_conversion_rate, format_sales_amount
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, detail_data)
            print(f"成功插入推广数据详情: {date_str}, {product_id}, {promotion_id}, {calculate_time}")

def main():
    """主函数"""
    init_db()
    json_files = list(DATA_DIR.rglob('*.json'))
    if not json_files:
        print(f"在 {DATA_DIR} 目录下未找到任何 JSON 文件。")
        return

    with sqlite3.connect(DB_FILE) as conn:
        for file_path in json_files:
            try:
                process_json_file(file_path, conn)
            except Exception as e:
                print(f"处理文件 {file_path} 时发生错误: {e}")
        conn.commit()
    print("\n所有文件处理完毕。")

if __name__ == "__main__":
    main()
