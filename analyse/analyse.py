
import json
import sqlite3
from pathlib import Path
import re

# 数据库文件路径
DB_FILE = Path(__file__).parent / "data.db"
# 数据目录路径
DATA_DIR = Path(__file__).parent / "data"

def init_db():
    """初始化数据库，创建表"""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        # 创建商品表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            date TEXT,
            product_id TEXT,
            promotion_id TEXT,
            rank_type TEXT,
            category TEXT,
            title TEXT,
            rank INTEGER,
            sales_volume INTEGER,
            influencer_count INTEGER,
            juliang_url TEXT,
            douyin_url TEXT,
            price REAL,
            commission_rate REAL,
            good_review_rate REAL,
            shop_experience_score INTEGER,
            product_score INTEGER,
            logistics_score INTEGER,
            seller_score INTEGER,
            shop_name TEXT,
            PRIMARY KEY (date, product_id, promotion_id)
        )
        """)
        # 创建推广数据表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS promotion_data (
            date TEXT,
            product_id TEXT,
            promotion_id TEXT,
            time_range TEXT,
            type TEXT,
            sales_amount REAL,
            total_sales_volume INTEGER,
            converting_influencers INTEGER,
            converting_contents INTEGER,
            conversion_rate_start REAL,
            conversion_rate_end REAL,
            views INTEGER,
            PRIMARY KEY (date, product_id, promotion_id)
        )
        """)
        conn.commit()

def get_json_value(data, path, default=None):
    """安全地从嵌套字典中获取值"""
    keys = path.split('.')
    for key in keys:
        if isinstance(data, dict) and key in data:
            data = data[key]
        else:
            return default
    return data

def parse_conversion_rate(rate_str):
    """解析'7.5%~10%'这样的转化率字符串"""
    if not rate_str or '%' not in rate_str:
        return None, None
    parts = rate_str.replace('%', '').split('~')
    try:
        start = float(parts[0])
        end = float(parts[1]) if len(parts) > 1 else start
        return start, end
    except (ValueError, IndexError):
        return None, None

def process_json_file(file_path: Path, conn: sqlite3.Connection):
    """处理单个JSON文件并存入数据库"""
    print(f"正在处理文件: {file_path}")
    # 从路径中提取日期
    try:
        date_str = file_path.parts[-3]
        if not re.match(r'\d{4}-\d{2}-\d{2}', date_str):
             date_str = get_json_value(data, 'seven_data.data.model.promotion_data.calculate_data.calculate_time')
             date_str = str(date_str)
             date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    except IndexError:
        print(f"无法从路径 {file_path} 中提取日期，跳过。")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    cursor = conn.cursor()

    # 提取并插入商品表数据
    product_id = get_json_value(data, 'detail_data.data.product_id')
    promotion_id = get_json_value(data, 'detail_data.data.promotion_id')

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
            get_json_value(data, 'detail_data.data.model.product.product_rec_reason.recommend_info.extra.cur_rank_type'),
            get_json_value(data, 'category'),
            get_json_value(data, 'detail_data.data.model.product.product_base.title'),
            get_json_value(data, 'detail_data.data.model.product.product_rec_reason.recommend_info.extra.cur_rank', 0),
            get_json_value(data, 'detail_data.data.model.product.product_sales.sell_num', 0),
            get_json_value(data, 'detail_data.data.model.product.product_match.author_num', 0),
            None, # 巨量的url - Not found in JSON
            get_json_value(data, 'detail_data.data.model.product.product_base.detail_url'),
            get_json_value(data, 'detail_data.data.model.product.product_price.price_label.price', 0) / 100.0,
            get_json_value(data, 'detail_data.data.model.product.product_cos.cos_label.cos.cos_ratio', 0),
            get_json_value(data, 'detail_data.data.model.product.product_comment.good_ratio', 0),
            get_json_value(data, 'detail_data.data.model.shop.shop_exper_scores.shop_exper_score_label.exper_score.score'),
            get_json_value(data, 'detail_data.data.model.shop.shop_exper_scores.shop_exper_score_label.goods_score.score'),
            get_json_value(data, 'detail_data.data.model.shop.shop_exper_scores.shop_exper_score_label.logistics_score.score'),
            get_json_value(data, 'detail_data.data.model.shop.shop_exper_scores.shop_exper_score_label.service_score.score'),
            get_json_value(data, 'detail_data.data.model.shop.shop_base.shop_name')
        )
        cursor.execute("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", product_data)
        print(f"成功插入产品数据: {date_str}, {product_id}, {promotion_id}")

    # 提取并插入推广数据表数据
    promo_date_int = get_json_value(data, 'seven_data.data.model.promotion_data.calculate_data.calculate_time')
    if promo_date_int:
        promo_date_str = str(promo_date_int)
        promo_date = f"{promo_date_str[:4]}-{promo_date_str[4:6]}-{promo_date_str[6:]}"
    else:
        promo_date = date_str # Fallback to file path date

    # 检查推广数据是否存在
    cursor.execute("SELECT 1 FROM promotion_data WHERE date = ? AND product_id = ? AND promotion_id = ?",
                   (promo_date, product_id, promotion_id))
    if cursor.fetchone():
        print(f"推广数据已存在: {promo_date}, {product_id}, {promotion_id}")
    else:
        rate_start, rate_end = parse_conversion_rate(get_json_value(data, 'seven_data.data.model.promotion_data.calculate_data.format_order_conversion_rate'))
        promotion_table_data = (
            promo_date,
            product_id,
            promotion_id,
            '7日', # 时间范围
            '视频', # 类型
            get_json_value(data, 'seven_data.data.model.promotion_data.calculate_data.sales_amount', 0) / 100.0,
            get_json_value(data, 'seven_data.data.model.promotion_data.calculate_data.sales', 0),
            get_json_value(data, 'seven_data.data.model.promotion_data.calculate_data.match_order_num', 0),
            get_json_value(data, 'seven_data.data.model.promotion_data.calculate_data.sales_content_num', 0),
            rate_start,
            rate_end,
            get_json_value(data, 'seven_data.data.model.promotion_data.calculate_data.pv', 0)
        )
        cursor.execute("INSERT INTO promotion_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", promotion_table_data)
        print(f"成功插入推广数据: {promo_date}, {product_id}, {promotion_id}")


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
