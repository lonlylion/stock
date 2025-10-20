#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

import os.path
import sys

cpath_current = os.path.dirname(os.path.dirname(__file__))
cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
sys.path.append(cpath)
import instock.lib.run_template as runt
import instock.core.tablestructure as tbs
import instock.lib.database as mdb
from instock.lib.database_factory import get_database, execute_sql, insert_db_from_df
import instock.core.stockfetch as stf
from instock.lib.simple_logger import get_logger
logger = get_logger(__name__)


# 每日股票大宗交易
def save_after_close_stock_blocktrade_data(date):
    try:
        data = stf.fetch_stock_blocktrade_data(date)
        if data is None or len(data.index) == 0:
            return

        table_name = tbs.TABLE_CN_STOCK_BLOCKTRADE['name']
        # 删除老数据。
        if mdb.checkTableIsExist(table_name):
            del_sql = f"DELETE FROM `{table_name}` where `date` = '{date}'"
            execute_sql(del_sql)
            cols_type = None
        else:
            cols_type = tbs.get_field_types(tbs.TABLE_CN_STOCK_BLOCKTRADE['columns'])

        insert_db_from_df(data, table_name, cols_type, False, "`date`,`code`")
    except Exception as e:
        logger.error(f"basic_data_after_close_daily_job.save_stock_blocktrade_data处理异常：{e}")

# 每日尾盘抢筹
def save_after_close_stock_chip_race_end_data(date):
    try:
        data = stf.fetch_stock_chip_race_end(date)
        if data is None or len(data.index) == 0:
            return

        table_name = tbs.TABLE_CN_STOCK_CHIP_RACE_END['name']
        # 删除老数据。
        if mdb.checkTableIsExist(table_name):
            del_sql = f"DELETE FROM `{table_name}` where `date` = '{date}'"
            execute_sql(del_sql)
            cols_type = None
        else:
            cols_type = tbs.get_field_types(tbs.TABLE_CN_STOCK_CHIP_RACE_END['columns'])

        insert_db_from_df(data, table_name, cols_type, False, "`date`,`code`")
    except Exception as e:
        logger.error(f"basic_data_after_close_daily_job.save_after_close_stock_chip_race_end_data：{e}")

def main():
    runt.run_with_args(save_after_close_stock_blocktrade_data)
    runt.run_with_args(save_after_close_stock_chip_race_end_data)


# main函数入口
if __name__ == '__main__':
    main()
