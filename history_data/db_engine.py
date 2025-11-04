import os
import pandas as pd
from pathlib import Path
from instock.lib.database_factory import get_database
from instock.lib.clickhouse_config import get_clickhouse_config

# 加载.env文件
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

# 使用统一的ClickHouse配置
CLICKHOUSE_CONFIG = get_clickhouse_config()

current_dir = os.path.dirname(os.path.abspath(__file__))
CODE_MAP_CSV = os.path.join(current_dir, 'code_map.csv')
HISTORY_DIR = os.path.join(current_dir, 'history_stock_data')
if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)
AGG_DATA_DIR = os.path.join(current_dir, 'agg_data')
if not os.path.exists(AGG_DATA_DIR):
    os.makedirs(AGG_DATA_DIR)


def create_clickhouse_client():
    """创建ClickHouse数据库连接客户端 - 使用统一配置"""
    try:
        import clickhouse_connect
        
        # 获取统一配置
        config = get_clickhouse_config()
        
        # 首先连接到默认数据库来创建目标数据库
        temp_client = clickhouse_connect.get_client(
            host=config['host'],
            port=config['port'],
            username=config['username'],
            password=config['password']
        )
        
        # 创建数据库（如果不存在）
        create_db_sql = f"CREATE DATABASE IF NOT EXISTS {config['database']}"
        temp_client.command(create_db_sql)
        print(f"数据库 {config['database']} 已确保存在")
        temp_client.close()
        
        # 连接到目标数据库
        client = clickhouse_connect.get_client(
            host=config['host'],
            port=config['port'],
            username=config['username'],
            password=config['password'],
            database=config['database']
        )
        
        # 测试连接
        result = client.query("SELECT 1")
        print(f"成功连接到ClickHouse数据库: {config['host']}:{config['port']}/{config['database']}")
        return client
    
    except ImportError:
        print("需要安装clickhouse-connect: pip install clickhouse-connect")
        return None
    except Exception as e:
        print(f"连接ClickHouse数据库失败: {str(e)}")
        return None


def create_stock_history_table_clickhouse(client):
    """在ClickHouse中创建股票历史数据表 - 使用统一表结构定义"""
    try:
        from instock.core.tablestructure import TABLE_CN_STOCK_HISTORY_CLICKHOUSE, TABLE_CN_MARKET_DAILY_STATS, TABLE_CN_STOCK_BASIC_INFO
        
        # 删除表如果存在（用于重建）
        drop_sql = f"DROP TABLE IF EXISTS {TABLE_CN_STOCK_HISTORY_CLICKHOUSE['name']}"
        client.command(drop_sql)
        
        # 构建主表创建SQL
        columns = []
        for col_name, col_def in TABLE_CN_STOCK_HISTORY_CLICKHOUSE['columns'].items():
            nullable = "" if not col_def.get('nullable', True) else " NULL"
            columns.append(f"{col_name} {col_def['type']}{nullable}")
        
        create_table_sql = f"""
        CREATE TABLE {TABLE_CN_STOCK_HISTORY_CLICKHOUSE['name']} (
            {', '.join(columns)}
        ) ENGINE = {TABLE_CN_STOCK_HISTORY_CLICKHOUSE['engine']}
        PARTITION BY {TABLE_CN_STOCK_HISTORY_CLICKHOUSE['partition_by']}
        ORDER BY {TABLE_CN_STOCK_HISTORY_CLICKHOUSE['order_by']}
        SETTINGS {TABLE_CN_STOCK_HISTORY_CLICKHOUSE['settings']}
        """
        
        client.command(create_table_sql)
        print(f"✅ 成功创建ClickHouse主表: {TABLE_CN_STOCK_HISTORY_CLICKHOUSE['name']}")
        
        # 创建日度市场统计物化视图
        mv_daily_stats_sql = f"""
        CREATE MATERIALIZED VIEW IF NOT EXISTS {TABLE_CN_MARKET_DAILY_STATS['name']}
        ENGINE = {TABLE_CN_MARKET_DAILY_STATS['engine']}
        PARTITION BY {TABLE_CN_MARKET_DAILY_STATS['partition_by']}
        ORDER BY {TABLE_CN_MARKET_DAILY_STATS['order_by']}
        AS SELECT
            date,
            market,
            count() as stock_count,
            sum(volume) as total_volume,
            sum(amount) as total_amount,
            countIf(p_change > 0) as up_count,
            countIf(p_change < 0) as down_count,
            avg(p_change) as avg_change
        FROM {TABLE_CN_STOCK_HISTORY_CLICKHOUSE['name']}
        GROUP BY date, market
        """
        
        client.command(mv_daily_stats_sql)
        print(f"✅ 成功创建市场日度统计视图: {TABLE_CN_MARKET_DAILY_STATS['name']}")
        
        # 创建股票基础信息物化视图
        mv_stock_info_sql = f"""
        CREATE MATERIALIZED VIEW IF NOT EXISTS {TABLE_CN_STOCK_BASIC_INFO['name']}
        ENGINE = {TABLE_CN_STOCK_BASIC_INFO['engine']}
        ORDER BY {TABLE_CN_STOCK_BASIC_INFO['order_by']}
        AS SELECT
            code,
            market,
            max(date) as last_trading_date,
            min(date) as first_trading_date,
            count() as total_trading_days
        FROM {TABLE_CN_STOCK_HISTORY_CLICKHOUSE['name']}
        GROUP BY code, market
        """
        
        client.command(mv_stock_info_sql)
        print(f"✅ 成功创建股票基础信息视图: {TABLE_CN_STOCK_BASIC_INFO['name']}")
        
        print(f"""
🎉 ClickHouse表结构创建完成！

📊 设计特点：
• 单表设计，按月自动分区 (PARTITION BY {TABLE_CN_STOCK_HISTORY_CLICKHOUSE['partition_by']})
• 主键排序 (ORDER BY {TABLE_CN_STOCK_HISTORY_CLICKHOUSE['order_by']}) 优化时间序列查询
• LowCardinality优化字符串存储
• 物化视图加速常用统计查询

🔍 预期性能提升：
• 存储空间节省 80%+ (列式压缩)
• 查询性能提升 10-100倍
• 无需手动分表管理
• 支持复杂分析查询
        """)
        
        return True
        
    except Exception as e:
        print(f"❌ 创建ClickHouse表时发生错误: {str(e)}")
        return False


def get_database_connection():
    """获取数据库连接 - 使用统一工厂"""
    return get_database()
