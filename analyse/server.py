import sqlite3
import os
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

# 初始化 Flask 应用
app = Flask(__name__)
CORS(app)  # 允许跨域请求，方便开发

# 数据库文件路径
DB_FILE = os.path.join(os.path.dirname(__file__), "data.db")

def get_db_connection():
    """创建并返回一个数据库连接"""
    if not os.path.exists(DB_FILE):
        raise FileNotFoundError(f"数据库文件未找到: {DB_FILE}")
    conn = sqlite3.connect(DB_FILE)
    # 让查询结果以字典形式返回，方便转换为JSON
    conn.row_factory = sqlite3.Row
    return conn

def query_table(table_name, page, per_page, search_term=None, sort_by='creation_time', sort_order='desc'):
    """通用查询函数，支持分页、搜索和排序"""
    try:
        conn = get_db_connection()
    except FileNotFoundError as e:
        return {"error": str(e)}

    cursor = conn.cursor()
    params = []
    where_clauses = []

    if search_term and table_name == 'products':
        like_term = f"%{search_term}%"
        where_clauses.append("(promotion_id LIKE ? OR product_id LIKE ? OR title LIKE ?)")
        params.extend([like_term, like_term, like_term])

    try:
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row['name'] for row in cursor.fetchall()]

        # 安全校验：确保排序字段是合法的列名
        if sort_by not in columns:
            sort_by = 'creation_time'
        # 安全校验：确保排序顺序是 asc 或 desc
        if sort_order.lower() not in ['asc', 'desc']:
            sort_order = 'desc'

        # 构建查询
        base_query = f"FROM {table_name}"
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)

        # 获取总行数
        total_count_query = f'SELECT COUNT(*) {base_query}'
        total_count_cursor = conn.execute(total_count_query, params)
        total_items = total_count_cursor.fetchone()[0]
        total_pages = (total_items + per_page - 1) // per_page

        # 查询分页数据
        offset = (page - 1) * per_page
        order_clause = f"ORDER BY {sort_by} {sort_order.upper()}"
        query = f"SELECT * {base_query} {order_clause} LIMIT ? OFFSET ?"
        data_cursor = conn.execute(query, params + [per_page, offset])
        data = data_cursor.fetchall()
        conn.close()

        data_dicts = [dict(row) for row in data]

        return {
            'columns': columns,
            'data': data_dicts,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages,
            'total_items': total_items
        }
    except sqlite3.OperationalError as e:
        conn.close()
        return {"error": f'表 "{table_name}" 不存在或数据库有问题: {e}'}

def query_single_item(table_name, date, product_id, promotion_id):
    """根据组合键查询单条记录"""
    try:
        conn = get_db_connection()
    except FileNotFoundError as e:
        return {"error": str(e)}

    try:
        query = f"SELECT * FROM {table_name} WHERE date = ? AND product_id = ? AND promotion_id = ?"
        item_cursor = conn.execute(query, (date, product_id, promotion_id))
        item = item_cursor.fetchone()
        conn.close()

        if item:
            return dict(item)
        else:
            return {"error": "Item not found"}
    except sqlite3.OperationalError:
        conn.close()
        return {"error": f'表 "{table_name}" 不存在或查询失败。'}

@app.route('/')
def index():
    """渲染主页"""
    return render_template('index.html')

@app.route('/api/products')
def get_products():
    """提供商品数据的API端点"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 30, type=int)
    search_term = request.args.get('search', None, type=str)
    sort_by = request.args.get('sort_by', 'creation_time', type=str)
    sort_order = request.args.get('sort_order', 'desc', type=str)
    data = query_table('products', page, per_page, search_term, sort_by, sort_order)
    if "error" in data:
        return jsonify(data), 500
    return jsonify(data)



@app.route('/api/product_item')
def get_product_item():
    """获取单条商品数据"""
    date = request.args.get('date')
    product_id = request.args.get('product_id')
    promotion_id = request.args.get('promotion_id')
    if not all([date, product_id, promotion_id]):
        return jsonify({"error": "缺少必须的查询参数: date, product_id, promotion_id"}), 400

    data = query_single_item('products', date, product_id, promotion_id)
    if "error" in data:
        return jsonify(data), 404
    return jsonify(data)



@app.route('/api/promotion_data_detail')
def get_promotion_data_detail():
    """获取推广数据详情的API端点"""
    date = request.args.get('date')
    product_id = request.args.get('product_id')
    promotion_id = request.args.get('promotion_id')
    if not all([date, product_id, promotion_id]):
        return jsonify({"error": "缺少必须的查询参数: date, product_id, promotion_id"}), 400

    try:
        conn = get_db_connection()
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 500

    try:
        query = "SELECT * FROM promotion_data_detail WHERE date = ? AND product_id = ? AND promotion_id = ? ORDER BY calculate_time"
        cursor = conn.execute(query, (date, product_id, promotion_id))
        data = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(data)
    except sqlite3.OperationalError as e:
        conn.close()
        return jsonify({"error": f'查询失败: {e}'}), 500

if __name__ == '__main__':
    # 检查模板文件是否存在
    if not os.path.exists(os.path.join(os.path.dirname(__file__), 'templates', 'index.html')):
        print("错误: 'templates/index.html' 文件未找到。")
        print("请确保前端文件存在于正确的位置。")
    else:
        print("启动Flask服务...")
        print("请在浏览器中打开 http://127.0.0.1:5001")
        app.run(host='0.0.0.0', port=5001, debug=True)