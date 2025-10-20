#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

import json
import os
import sys
import time
import uuid

import pandas as pd
from datetime import datetime, timedelta
from abc import ABC
import tornado.gen
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor

# 添加项目路径
cpath_current = os.path.dirname(os.path.dirname(__file__))
cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
sys.path.append(cpath)

import instock.web.base as webBase
import instock.lib.database as mdb
from instock.lib.database_factory import get_database, DatabaseType
from instock.lib.simple_logger import get_logger

# 获取logger
logger = get_logger(__name__)

# 导入历史数据处理模块
history_data_path = os.path.join(cpath, 'history_data')
sys.path.append(history_data_path)

# 全局变量用于存储导入的模块
db_engine_module = None
bao_module = None

def import_history_modules():
    """动态导入历史数据模块"""
    global db_engine_module, bao_module
    try:
        import importlib.util
        
        # 导入db_engine模块
        db_engine_path = os.path.join(history_data_path, 'db_engine.py')
        if os.path.exists(db_engine_path):
            spec = importlib.util.spec_from_file_location("db_engine", db_engine_path)
            db_engine_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(db_engine_module)
        
        # 导入bao模块
        bao_path = os.path.join(history_data_path, 'bao.py')
        if os.path.exists(bao_path):
            spec = importlib.util.spec_from_file_location("bao", bao_path)
            bao_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bao_module)
            
        return True
    except Exception as e:
        logger.warning(f"无法导入历史数据模块: {e}")
        return False

# 尝试导入模块
modules_loaded = import_history_modules()

__author__ = 'AI Assistant'
__date__ = '2025/9/5'


class DataDownloadPageHandler(webBase.BaseHandler, ABC):
    """数据下载页面处理器"""
    
    @tornado.gen.coroutine
    def get(self):
        try:
            import instock.lib.trade_time as trd
            run_date, run_date_nph = trd.get_trade_date_last()
            date_now_str = run_date.strftime("%Y-%m-%d")
            
            # 记录页面访问日志
            client_ip = self.request.remote_ip
            user_agent = self.request.headers.get('User-Agent', 'Unknown')
            logger.info(f"数据下载页面访问 - IP: {client_ip}, User-Agent: {user_agent}")
            
            self.render("data_download.html",
                       date_now=date_now_str,
                       leftMenu=webBase.GetLeftMenu(self.request.uri))
                       
        except Exception as e:
            logger.error(f"数据下载页面加载失败: {str(e)}")
            self.write(f"页面加载失败: {str(e)}")


class DataDownloadApiHandler(webBase.BaseHandler, ABC):
    """数据下载API处理器"""
    
    executor = ThreadPoolExecutor(max_workers=4)
    
    # 存储后台任务状态
    tasks = {}
    
    def write_json(self, data):
        """返回JSON响应"""
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.write(json.dumps(data, ensure_ascii=False, default=str))
    
    @tornado.gen.coroutine
    def post(self):
        """处理数据下载请求"""
        client_ip = self.request.remote_ip
        try:
            action = self.get_argument("action", "")
            logger.info(f"API请求 - IP: {client_ip}, Action: {action}")
            
            if action == "check_data":
                yield self.handle_check_data()
            elif action == "download_data":
                yield self.handle_download_data()
            elif action == "get_task_status":
                yield self.handle_get_task_status()
            elif action == "supplement_data":
                yield self.handle_supplement_data()
            else:
                logger.warning(f"未知的操作类型 - IP: {client_ip}, Action: {action}")
                self.write_json({
                    "success": False,
                    "message": "未知的操作类型"
                })
                
        except Exception as e:
            logger.error(f"API请求处理失败 - IP: {client_ip}, Error: {str(e)}")
            self.write_json({
                "success": False,
                "message": f"请求处理失败: {str(e)}"
            })
    
    @tornado.gen.coroutine
    def handle_check_data(self):
        """检查数据完整性"""
        client_ip = self.request.remote_ip
        try:
            check_scope = self.get_argument("check_scope", "single")
            start_date = self.get_argument("start_date", "")
            end_date = self.get_argument("end_date", "")
            
            logger.info(f"数据完整性检查请求 - IP: {client_ip}, Scope: {check_scope}, "
                       f"Date Range: {start_date} to {end_date}")
            
            if not start_date or not end_date:
                logger.warning(f"数据检查参数不完整 - IP: {client_ip}")
                self.write_json({
                    "success": False,
                    "message": "请填写完整的时间范围"
                })
                return
            
            if check_scope == "single":
                # 单个股票检查
                stock_code = self.get_argument("stock_code", "").strip()
                
                logger.info(f"单个股票数据检查 - IP: {client_ip}, Stock: {stock_code}")
                
                if not stock_code:
                    self.write_json({
                        "success": False,
                        "message": "请填写股票代码"
                    })
                    return
                
                if not self._validate_stock_code(stock_code):
                    logger.warning(f"股票代码格式错误 - IP: {client_ip}, Stock: {stock_code}")
                    self.write_json({
                        "success": False,
                        "message": "股票代码格式不正确，请输入6位数字代码"
                    })
                    return
                
                # 单个股票检查逻辑（保持原有逻辑）
                result = yield self._check_data_completeness(stock_code, start_date, end_date)
                
                if result.get('success'):
                    logger.info(f"单个股票检查完成 - IP: {client_ip}, Stock: {stock_code}, "
                               f"Completeness: {result.get('completeness', 0)}%")
                else:
                    logger.error(f"单个股票检查失败 - IP: {client_ip}, Stock: {stock_code}, "
                                f"Error: {result.get('message', 'Unknown error')}")
                
                self.write_json(result)
                
            else:
                # 批量检查
                market = self.get_argument("market", "ALL") if check_scope == "market" else "ALL"
                
                logger.info(f"批量数据检查开始 - IP: {client_ip}, Scope: {check_scope}, Market: {market}")
                
                result = yield self._check_batch_data_completeness(check_scope, market, start_date, end_date)
                
                if result.get('success'):
                    summary = result.get('summary', {})
                    logger.info(f"批量数据检查完成 - IP: {client_ip}, "
                               f"Total: {summary.get('total_stocks', 0)}, "
                               f"Complete: {summary.get('complete_stocks', 0)}, "
                               f"Missing: {summary.get('partial_missing', 0) + summary.get('severe_missing', 0)}")
                else:
                    logger.error(f"批量数据检查失败 - IP: {client_ip}, "
                                f"Error: {result.get('message', 'Unknown error')}")
                
                self.write_json(result)
                
        except Exception as e:
            logger.error(f"数据检查异常 - IP: {client_ip}, Error: {str(e)}")
            self.write_json({
                "success": False,
                "message": f"数据检查失败: {str(e)}"
            })
    
    @tornado.gen.coroutine
    def handle_download_data(self):
        """处理数据下载请求"""
        client_ip = self.request.remote_ip
        try:
            stock_code = self.get_argument("stock_code", "").strip()
            start_date = self.get_argument("start_date", "")
            end_date = self.get_argument("end_date", "")
            write_to_db = self.get_argument("write_to_db", "false") == "true"
            
            logger.info(f"数据下载请求 - IP: {client_ip}, Stock: {stock_code}, "
                       f"Date Range: {start_date} to {end_date}, WriteDB: {write_to_db}")
            
            if not stock_code or not start_date or not end_date:
                logger.warning(f"数据下载参数不完整 - IP: {client_ip}")
                self.write_json({
                    "success": False,
                    "message": "请填写完整的股票代码和时间范围"
                })
                return
            
            # 生成任务ID
            task_id = str(uuid.uuid4())
            
            # 创建任务记录
            self.tasks[task_id] = {
                "status": "pending",
                "progress": 0,
                "message": "任务已创建，等待处理...",
                "created_at": datetime.now(),
                "stock_code": stock_code,
                "start_date": start_date,
                "end_date": end_date,
                "write_to_db": write_to_db,
                "download_url": None,
                "client_ip": client_ip
            }
            
            logger.info(f"数据下载任务创建 - IP: {client_ip}, TaskID: {task_id}")
            
            # 启动后台下载任务
            yield self._start_download_task(task_id, stock_code, start_date, end_date, write_to_db)
            
            self.write_json({
                "success": True,
                "task_id": task_id,
                "message": "下载任务已启动，请稍后查看进度"
            })
            
        except Exception as e:
            logger.error(f"数据下载请求处理失败 - IP: {client_ip}, Error: {str(e)}")
            self.write_json({
                "success": False,
                "message": f"下载请求处理失败: {str(e)}"
            })
    
    @tornado.gen.coroutine
    def handle_get_task_status(self):
        """获取任务状态"""
        try:
            task_id = self.get_argument("task_id", "")
            
            if task_id in self.tasks:
                task = self.tasks[task_id]
                self.write_json({
                    "success": True,
                    "task": task
                })
            else:
                self.write_json({
                    "success": False,
                    "message": "任务不存在"
                })
                
        except Exception as e:
            self.write_json({
                "success": False,
                "message": f"获取任务状态失败: {str(e)}"
            })
    
    @tornado.gen.coroutine
    def handle_supplement_data(self):
        """处理数据补齐请求"""
        client_ip = self.request.remote_ip
        try:
            # 检查是单个股票补齐还是批量补齐
            check_scope = self.get_argument("check_scope", "").strip()
            
            if check_scope in ['all', 'market']:
                # 批量补齐
                market = self.get_argument("market", "ALL")
                start_date = self.get_argument("start_date", "")
                end_date = self.get_argument("end_date", "")
                missing_stocks = json.loads(self.get_argument("missing_stocks", "[]"))
                
                logger.info(f"批量数据补齐请求 - IP: {client_ip}, Scope: {check_scope}, "
                           f"Market: {market}, Missing Stocks: {len(missing_stocks)}")
                
                if not start_date or not end_date or not missing_stocks:
                    logger.warning(f"批量数据补齐参数不完整 - IP: {client_ip}")
                    self.write_json({
                        "success": False,
                        "message": "缺少必要参数：时间范围或缺失股票列表"
                    })
                    return
                
                # 生成任务ID
                task_id = str(uuid.uuid4())
                
                # 创建批量补齐任务记录
                self.tasks[task_id] = {
                    "status": "pending",
                    "progress": 0,
                    "message": "批量数据补齐任务已创建，等待处理...",
                    "created_at": datetime.now(),
                    "check_scope": check_scope,
                    "market": market,
                    "start_date": start_date,
                    "end_date": end_date,
                    "missing_stocks": missing_stocks,
                    "type": "batch_supplement",
                    "client_ip": client_ip
                }
                
                logger.info(f"批量数据补齐任务创建 - IP: {client_ip}, TaskID: {task_id}")
                
                # 启动批量补齐任务
                yield self._start_batch_supplement_task(task_id, check_scope, market, start_date, end_date, missing_stocks)
                
            else:
                # 单个股票补齐
                stock_code = self.get_argument("stock_code", "").strip()
                missing_dates = json.loads(self.get_argument("missing_dates", "[]"))
                
                logger.info(f"单个股票数据补齐请求 - IP: {client_ip}, Stock: {stock_code}, "
                           f"Missing Dates Count: {len(missing_dates)}")
                
                if not stock_code or not missing_dates:
                    logger.warning(f"单个股票数据补齐参数不完整 - IP: {client_ip}")
                    self.write_json({
                        "success": False,
                        "message": "缺少必要参数：股票代码或缺失日期"
                    })
                    return
                
                # 生成任务ID
                task_id = str(uuid.uuid4())
                
                # 创建单个补齐任务记录
                self.tasks[task_id] = {
                    "status": "pending",
                    "progress": 0,
                    "message": "数据补齐任务已创建，等待处理...",
                    "created_at": datetime.now(),
                    "stock_code": stock_code,
                    "missing_dates": missing_dates,
                    "type": "supplement",
                    "client_ip": client_ip
                }
                
                logger.info(f"单个股票数据补齐任务创建 - IP: {client_ip}, TaskID: {task_id}")
                
                # 启动单个补齐任务
                yield self._start_supplement_task(task_id, stock_code, missing_dates)
            
            self.write_json({
                "success": True,
                "task_id": task_id,
                "message": "数据补齐任务已启动"
            })
            
        except Exception as e:
            logger.error(f"数据补齐请求处理失败 - IP: {client_ip}, Error: {str(e)}")
            self.write_json({
                "success": False,
                "message": f"数据补齐请求处理失败: {str(e)}"
            })
    
    def _validate_stock_code(self, stock_code):
        """验证股票代码格式"""
        return stock_code.isdigit() and len(stock_code) == 6
    
    def _get_market_from_code(self, stock_code):
        """根据股票代码判断市场"""
        if stock_code.startswith('6'):
            return 'SH'
        elif stock_code.startswith(('0', '3')):
            return 'SZ'
        elif stock_code.startswith(('8', '4')):
            return 'BJ'
        else:
            return 'SZ'  # 默认深圳
    
    @run_on_executor
    def _check_data_completeness(self, stock_code, start_date, end_date):
        """检查数据完整性（在后台线程中执行）- 考虑上市时间"""
        try:
            market = self._get_market_from_code(stock_code)
            
            # 使用trade_time模块获取交易日期范围
            import instock.lib.trade_time as trd
            from instock.core.singleton_trade_date import stock_trade_date
            
            # 直接从预置的交易日数据中筛选指定范围的交易日
            all_trade_dates = stock_trade_date().get_data()
            if all_trade_dates is None:
                raise Exception("无法获取交易日数据，请检查trade_date配置")
            
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            # 尝试获取股票上市日期
            ipo_date = None
            try:
                # 动态导入tushare模块获取上市日期
                tushare_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'history_data')
                sys.path.append(tushare_path)
                
                import importlib.util
                tushare_spec = importlib.util.spec_from_file_location("tushare_all", os.path.join(tushare_path, "tushare_all.py"))
                if tushare_spec and tushare_spec.loader:
                    tushare_all = importlib.util.module_from_spec(tushare_spec)
                    tushare_spec.loader.exec_module(tushare_all)
                    
                    fetcher = tushare_all.StockDataFetcher()
                    exchange_map = {'SH': 'SSE', 'SZ': 'SZSE', 'BJ': 'BSE'}
                    exchange = exchange_map.get(market.upper())
                    
                    stock_basic = fetcher.get_stock_list(exchange)
                    if stock_basic is not None and not stock_basic.empty:
                        stock_info = stock_basic[stock_basic['symbol'] == stock_code]
                        if not stock_info.empty:
                            list_date = stock_info.iloc[0]['list_date']
                            if pd.notna(list_date) and str(list_date) != 'nan':
                                ipo_date = datetime.strptime(str(list_date), '%Y%m%d').date()
                                
                                logger.info(f"获取到股票 {stock_code} 上市日期: {ipo_date}")
            except Exception as e:
                logger.warning(f"获取股票 {stock_code} 上市日期失败: {e}")
            
            # 计算实际的预期交易日
            if ipo_date:
                # 如果有上市日期，使用上市日期和查询开始日期的较大值
                actual_start_date = max(start_date_obj, ipo_date)
                if actual_start_date > end_date_obj:
                    # 股票上市时间晚于查询结束时间
                    return {
                        "success": True,
                        "stock_code": stock_code,
                        "market": market,
                        "start_date": start_date,
                        "end_date": end_date,
                        "ipo_date": ipo_date.strftime('%Y-%m-%d'),
                        "total_expected": 0,
                        "existing_count": 0,
                        "missing_count": 0,
                        "completeness": 100.0,
                        "missing_dates": [],
                        "has_missing": False,
                        "note": "股票上市时间晚于查询期间"
                    }
            else:
                # 如果没有上市日期，使用查询开始日期
                actual_start_date = start_date_obj
                logger.warning(f"股票 {stock_code} 无上市日期信息，使用查询开始日期")
            
            # 筛选出指定日期范围内的交易日
            expected_dates = [
                date.strftime('%Y-%m-%d') for date in all_trade_dates 
                if actual_start_date <= date <= end_date_obj
            ]
            
            # 检查ClickHouse中的现有数据
            missing_dates = []
            existing_count = 0
            
            try:
                if db_engine_module:
                    client = db_engine_module.create_clickhouse_client()
                    if client:
                        # 查询现有数据
                        query = """
                        SELECT date 
                        FROM cn_stock_history 
                        WHERE code = %s 
                          AND market = %s 
                          AND date >= %s 
                          AND date <= %s
                        ORDER BY date
                        """
                        
                        result = client.query(query, [stock_code, market.lower(), actual_start_date.strftime('%Y-%m-%d'), end_date])
                        
                        # 处理ClickHouse查询结果
                        existing_dates = []
                        if hasattr(result, 'result_rows'):
                            existing_dates = [row[0].strftime('%Y-%m-%d') if hasattr(row[0], 'strftime') else str(row[0]) for row in result.result_rows]
                        elif hasattr(result, 'data'):
                            existing_dates = [row[0].strftime('%Y-%m-%d') if hasattr(row[0], 'strftime') else str(row[0]) for row in result.data]
                        else:
                            try:
                                existing_dates = [row[0].strftime('%Y-%m-%d') if hasattr(row[0], 'strftime') else str(row[0]) for row in result]
                            except (TypeError, AttributeError):
                                existing_dates = []
                        
                        existing_count = len(existing_dates)
                        
                        # 找出缺失的日期
                        missing_dates = [date for date in expected_dates if date not in existing_dates]
                        
                        client.close()
                        
                else:
                    logger.warning("db_engine模块未加载，无法检查数据库")
                    missing_dates = expected_dates
                    
            except Exception as e:
                logger.error(f"检查ClickHouse数据时出错: {e}")
                # 如果ClickHouse查询失败，假设所有数据都缺失
                missing_dates = expected_dates
            
            total_expected = len(expected_dates)
            missing_count = len(missing_dates)
            completeness = ((total_expected - missing_count) / total_expected * 100) if total_expected > 0 else 0
            
            result = {
                "success": True,
                "stock_code": stock_code,
                "market": market,
                "start_date": start_date,
                "end_date": end_date,
                "total_expected": total_expected,
                "existing_count": existing_count,
                "missing_count": missing_count,
                "completeness": round(completeness, 2),
                "missing_dates": missing_dates[:10],  # 只返回前10个缺失日期作为示例
                "has_missing": missing_count > 0
            }
            
            # 如果有上市日期信息，添加到结果中
            if ipo_date:
                result["ipo_date"] = ipo_date.strftime('%Y-%m-%d')
                result["actual_start_date"] = actual_start_date.strftime('%Y-%m-%d')
                if actual_start_date > start_date_obj:
                    result["note"] = f"已根据上市日期 {ipo_date.strftime('%Y-%m-%d')} 调整计算起始日期"
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "message": f"数据完整性检查失败: {str(e)}"
            }
    
    @run_on_executor
    def _check_batch_data_completeness(self, check_scope, market, start_date, end_date):
        """批量检查数据完整性（在后台线程中执行）- 性能优化版本"""
        start_time = time.time()
        try:
            # 使用trade_time模块获取交易日期范围
            import instock.lib.trade_time as trd
            from instock.core.singleton_trade_date import stock_trade_date
            
            # 直接从预置的交易日数据中筛选指定范围的交易日
            all_trade_dates = stock_trade_date().get_data()
            if all_trade_dates is None:
                raise Exception("无法获取交易日数据，请检查trade_date配置")
            
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            # 筛选出指定日期范围内的交易日
            expected_dates = [
                date.strftime('%Y-%m-%d') for date in all_trade_dates 
                if start_date_obj <= date <= end_date_obj
            ]
            
            total_expected_days = len(expected_dates)
            logger.info(f"预期交易日数量: {total_expected_days} - Date Range: {start_date} to {end_date}")
            
            # 获取股票列表及上市日期
            stock_list = self._get_stock_list_with_ipo_date(market)
            
            if not stock_list:
                return {
                    "success": False,
                    "message": "未找到股票列表"
                }
            
            logger.info(f"开始批量数据完整性检查 - Market: {market}, Stock Count: {len(stock_list)}")
            
            # 批量检查数据完整性
            results = []
            summary = {
                "total_stocks": len(stock_list),
                "complete_stocks": 0,
                "partial_missing": 0,
                "severe_missing": 0
            }
            
            try:
                if db_engine_module:
                    client = db_engine_module.create_clickhouse_client()
                    if client:
                        # 批量查询所有股票的数据统计（不过滤，保留所有历史数据查询能力）
                        if market == "ALL":
                            batch_query = """
                            SELECT code, market, COUNT(*) as count
                            FROM cn_stock_history 
                            WHERE date >= %s AND date <= %s
                            GROUP BY code, market
                            """
                            batch_result = client.query(batch_query, [start_date, end_date])
                        else:
                            batch_query = """
                            SELECT code, market, COUNT(*) as count
                            FROM cn_stock_history 
                            WHERE market = %s AND date >= %s AND date <= %s
                            GROUP BY code, market
                            """
                            batch_result = client.query(batch_query, [market.lower(), start_date, end_date])
                        
                        # 处理批量查询结果，建立股票代码到数据条数的映射
                        stock_data_count = {}
                        if hasattr(batch_result, 'result_rows'):
                            for row in batch_result.result_rows:
                                code, market_name, count = row[0], row[1].upper(), row[2]
                                stock_data_count[f"{code}_{market_name}"] = count
                        elif hasattr(batch_result, 'data'):
                            for row in batch_result.data:
                                code, market_name, count = row[0], row[1].upper(), row[2]
                                stock_data_count[f"{code}_{market_name}"] = count
                        else:
                            try:
                                for row in batch_result:
                                    code, market_name, count = row[0], row[1].upper(), row[2]
                                    stock_data_count[f"{code}_{market_name}"] = count
                            except (TypeError, IndexError):
                                logger.error(f"批量查询结果格式错误 - Market: {market}")
                                stock_data_count = {}
                        
                        logger.info(f"批量查询完成 - Market: {market}, 查询到 {len(stock_data_count)} 只股票的数据")
                        
                        # 遍历股票列表，从缓存的查询结果中获取数据
                        for stock_info in stock_list:
                            stock_code = stock_info['code']
                            stock_market = stock_info['market']
                            ipo_date = stock_info.get('ipo_date')
                            stock_key = f"{stock_code}_{stock_market}"
                            
                            try:
                                # 计算该股票的实际预期交易日数量
                                if ipo_date:
                                    # 如果有上市日期，计算从上市日期到查询结束日期的交易日数量
                                    stock_start_date = max(start_date_obj, ipo_date)
                                    if stock_start_date <= end_date_obj:
                                        # 筛选该股票实际应有的交易日
                                        stock_expected_dates = [
                                            date for date in expected_dates 
                                            if datetime.strptime(date, '%Y-%m-%d').date() >= stock_start_date
                                        ]
                                        stock_expected_days = len(stock_expected_dates)
                                    else:
                                        # 股票上市时间晚于查询结束时间，跳过
                                        continue
                                else:
                                    # 如果没有上市日期信息，使用全部交易日（保持原逻辑）
                                    stock_expected_days = total_expected_days
                                    logger.warning(f"股票 {stock_code} 无上市日期信息，使用全部交易日")
                                
                                # 从缓存的查询结果中获取数据条数
                                existing_count = stock_data_count.get(stock_key, 0)
                                
                                missing_count = stock_expected_days - existing_count
                                completeness = ((stock_expected_days - missing_count) / stock_expected_days * 100) if stock_expected_days > 0 else 0
                                
                                # 分类统计
                                if completeness >= 99:
                                    summary["complete_stocks"] += 1
                                elif completeness >= 50:
                                    summary["partial_missing"] += 1
                                else:
                                    summary["severe_missing"] += 1
                                
                                # 只保存缺失数据的股票详情
                                if missing_count > 0:
                                    result_item = {
                                        "code": stock_code,
                                        "market": stock_market,
                                        "total_expected": stock_expected_days,
                                        "existing_count": existing_count,
                                        "missing_count": missing_count,
                                        "completeness": round(completeness, 2)
                                    }
                                    
                                    # 如果有上市日期，添加到结果中
                                    if ipo_date:
                                        result_item["ipo_date"] = ipo_date.strftime('%Y-%m-%d')
                                    
                                    results.append(result_item)
                                    
                            except Exception as e:
                                logger.warning(f"处理股票 {stock_code} 数据时出错: {e}")
                                # 假设严重缺失
                                summary["severe_missing"] += 1
                                results.append({
                                    "code": stock_code,
                                    "market": stock_market,
                                    "total_expected": total_expected_days,
                                    "existing_count": 0,
                                    "missing_count": total_expected_days,
                                    "completeness": 0
                                })
                        
                        client.close()
                        logger.info(f"批量检查处理完成 - Market: {market}, Total: {len(stock_list)}, "
                                   f"Complete: {summary['complete_stocks']}, "
                                   f"Missing: {summary['partial_missing'] + summary['severe_missing']}")
                    else:
                        raise Exception("无法连接到ClickHouse数据库")
                else:
                    raise Exception("数据库引擎模块未加载")
                    
            except Exception as e:
                return {
                    "success": False,
                    "message": f"批量检查失败: {str(e)}"
                }
            
            # 按缺失程度排序（缺失最严重的在前）
            results.sort(key=lambda x: x['completeness'])
            
            total_time = time.time() - start_time
            logger.info(f"批量检查完成 - Total Time: {total_time:.2f}s, Stocks: {len(stock_list)}")
            
            return {
                "success": True,
                "check_scope": check_scope,
                "market": market,
                "start_date": start_date,
                "end_date": end_date,
                "summary": summary,
                "details": results,
                "total_expected_days": total_expected_days,
                "performance": {
                    "total_time": round(total_time, 2),
                    "stocks_per_second": round(len(stock_list) / total_time, 2) if total_time > 0 else 0
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"批量数据完整性检查失败: {str(e)}"
            }
    
    def _get_stock_list_with_ipo_date(self, market):
        """
        获取股票列表及上市日期
        
        过滤策略：
        1. 本地数据库：保留所有历史股票数据
        2. tushare过滤：只排除退市股票（list_status='L'），保留正常上市股票
        3. ST股票：暂不关注，不做特殊处理
        4. 目标：退市股票不参与数据完整性校验，但历史数据保留
        """
        try:
            logger.info(f"开始获取股票列表及上市日期 - Market: {market}")
            
            # 先尝试从ClickHouse获取基础股票列表
            stock_list = self._get_stock_list(market)
            if not stock_list:
                return []
            
            # 尝试从tushare获取上市日期信息
            try:
                # 动态导入tushare模块
                tushare_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'history_data')
                sys.path.append(tushare_path)
                
                import importlib.util
                tushare_spec = importlib.util.spec_from_file_location("tushare_all", os.path.join(tushare_path, "tushare_all.py"))
                if tushare_spec and tushare_spec.loader:
                    tushare_all = importlib.util.module_from_spec(tushare_spec)
                    tushare_spec.loader.exec_module(tushare_all)
                    
                    fetcher = tushare_all.StockDataFetcher()
                
                # 获取股票基础信息（包含上市日期）
                if market == "ALL":
                    stock_basic = fetcher.get_stock_list()
                else:
                    exchange_map = {'SH': 'SSE', 'SZ': 'SZSE', 'BJ': 'BSE'}
                    exchange = exchange_map.get(market.upper())
                    stock_basic = fetcher.get_stock_list(exchange)
                
                if stock_basic is not None and not stock_basic.empty:
                    # 只过滤退市股票（list_status != 'L'），不关注ST股票
                    if 'list_status' in stock_basic.columns:
                        before_filter = len(stock_basic)
                        # 只保留正常上市状态的股票（排除退市D和暂停上市P）
                        stock_basic = stock_basic[stock_basic['list_status'] == 'L']
                        filtered_count = before_filter - len(stock_basic)
                        if filtered_count > 0:
                            logger.info(f"过滤掉退市/暂停上市股票 {filtered_count} 只")
                    
                    logger.info(f"过滤退市股票后剩余 {len(stock_basic)} 只正常上市股票")
                    
                    # 创建上市日期映射
                    ipo_date_map = {}
                    for _, row in stock_basic.iterrows():
                        symbol = row['symbol']  # 6位股票代码
                        list_date = row['list_date']  # 上市日期 YYYYMMDD格式
                        
                        # 转换上市日期格式
                        try:
                            if pd.notna(list_date) and str(list_date) != 'nan':
                                ipo_date = datetime.strptime(str(list_date), '%Y%m%d').date()
                                ipo_date_map[symbol] = ipo_date
                        except (ValueError, TypeError):
                            # 如果日期格式有问题，记录警告
                            logger.warning(f"股票 {symbol} 上市日期格式错误: {list_date}")
                    
                    logger.info(f"获取到 {len(ipo_date_map)} 只正常上市股票的上市日期信息")
                    
                    # 为股票列表添加上市日期，只排除退市股票
                    enhanced_stock_list = []
                    for stock in stock_list:
                        stock_code = stock['code']
                        ipo_date = ipo_date_map.get(stock_code)
                        
                        # 只添加有上市日期信息且正常上市的股票（自然排除了退市股票）
                        if ipo_date:
                            enhanced_stock_list.append({
                                'code': stock_code,
                                'market': stock['market'],
                                'ipo_date': ipo_date
                            })
                    
                    logger.info(f"完成股票列表增强（已排除退市股票） - Total: {len(enhanced_stock_list)}")
                    return enhanced_stock_list
                else:
                    logger.warning("从tushare获取股票基础信息失败，使用无上市日期的列表")
                    
            except Exception as e:
                logger.warning(f"获取tushare上市日期失败: {e}，使用无上市日期的列表")
            
            # 如果无法获取上市日期，返回不含上市日期的股票列表
            return [{
                'code': stock['code'],
                'market': stock['market'],
                'ipo_date': None
            } for stock in stock_list]
            
        except Exception as e:
            logger.error(f"获取股票列表及上市日期异常 - Market: {market}, Error: {str(e)}")
            return []
    
    def _get_stock_list(self, market):
        """
        获取股票列表（不含上市日期）
        
        策略说明：
        1. 本地数据库：保留所有历史数据，不做过滤
        2. 用于数据完整性校验的股票列表：通过tushare过滤退市股票
        3. ST股票：暂不关注，不做特殊处理
        """
        try:
            logger.info(f"开始获取股票列表 - Market: {market}")
            
            if db_engine_module:
                # 先尝试从数据库获取股票列表
                client = db_engine_module.create_clickhouse_client()
                if client:
                    try:
                        # 从数据库获取所有股票列表（不过滤，保留历史数据）
                        if market == "ALL":
                            query = "SELECT DISTINCT code, market FROM cn_stock_history ORDER BY market, code"
                            result = client.query(query)
                        else:
                            query = "SELECT DISTINCT code, market FROM cn_stock_history WHERE market = %s ORDER BY code"
                            result = client.query(query, [market.lower()])
                        
                        # 处理ClickHouse查询结果
                        stock_list = []
                        if hasattr(result, 'result_rows'):
                            # clickhouse_connect 返回的是 QueryResult 对象
                            for row in result.result_rows:
                                stock_list.append({"code": row[0], "market": row[1].upper()})
                        elif hasattr(result, 'data'):
                            # 其他可能的结果格式
                            for row in result.data:
                                stock_list.append({"code": row[0], "market": row[1].upper()})
                        else:
                            # 如果是直接的列表格式
                            try:
                                for row in result:
                                    stock_list.append({"code": row[0], "market": row[1].upper()})
                            except TypeError:
                                logger.warning(f"无法解析ClickHouse查询结果格式 - Market: {market}")
                        
                        client.close()
                        
                        if stock_list:
                            logger.info(f"从数据库获取股票列表成功（包含所有历史股票） - Market: {market}, Count: {len(stock_list)}")
                            return stock_list
                        else:
                            logger.warning(f"数据库中无股票数据 - Market: {market}")
                    
                    except Exception as e:
                        logger.error(f"ClickHouse查询失败 - Market: {market}, Error: {str(e)}")
                        client.close()
            
            # 如果数据库中没有数据，从code_map.csv读取
            import pandas as pd
            import os
            
            history_data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'history_data')
            code_map_path = os.path.join(history_data_path, 'code_map.csv')
            
            logger.info(f"尝试从CSV文件获取股票列表 - Path: {code_map_path}")
            
            if os.path.exists(code_map_path):
                df = pd.read_csv(code_map_path)
                
                if market != "ALL":
                    df = df[df['market'].str.upper() == market.upper()]
                
                stock_list = []
                for _, row in df.iterrows():
                    stock_list.append({
                        "code": str(row['code']).zfill(6),
                        "market": str(row['market']).upper()
                    })
                
                logger.info(f"从CSV文件获取股票列表成功 - Market: {market}, Count: {len(stock_list)}")
                return stock_list
            else:
                logger.error(f"CSV文件不存在 - Path: {code_map_path}")
            
            logger.warning(f"获取股票列表失败 - Market: {market}")
            return []
            
        except Exception as e:
            logger.error(f"获取股票列表异常 - Market: {market}, Error: {str(e)}")
            return []
    
    @run_on_executor  
    def _start_download_task(self, task_id, stock_code, start_date, end_date, write_to_db):
        """启动下载任务（在后台线程中执行）"""
        client_ip = self.tasks[task_id].get('client_ip', 'Unknown')
        try:
            logger.info(f"后台下载任务开始 - TaskID: {task_id}, IP: {client_ip}, Stock: {stock_code}")
            
            # 更新任务状态
            self.tasks[task_id]["status"] = "running"
            self.tasks[task_id]["message"] = "正在从数据库查询数据..."
            self.tasks[task_id]["progress"] = 10
            
            market = self._get_market_from_code(stock_code)
            
            # 从ClickHouse查询数据
            if not db_engine_module:
                raise Exception("数据库引擎模块未加载")
                
            client = db_engine_module.create_clickhouse_client()
            if not client:
                raise Exception("无法连接到ClickHouse数据库")
            
            logger.info(f"数据库连接成功 - TaskID: {task_id}, Stock: {stock_code}")
            
            self.tasks[task_id]["message"] = "正在查询数据..."
            self.tasks[task_id]["progress"] = 30
            
            query = """
            SELECT date, code, market, open, high, low, close, preclose, 
                   volume, amount, adjustflag, turn, tradestatus, p_change, isST
            FROM cn_stock_history 
            WHERE code = %s 
              AND market = %s 
              AND date >= %s 
              AND date <= %s
            ORDER BY date
            """
            
            # 使用query_df方法直接获取DataFrame，避免处理QueryResult对象
            try:
                result = client.query_df(query, [stock_code, market.lower(), start_date, end_date])
            except AttributeError:
                # 如果没有query_df方法，则手动处理查询结果
                query_result = client.query(query, [stock_code, market.lower(), start_date, end_date])
                
                # 处理查询结果并转换为DataFrame
                if hasattr(query_result, 'result_rows'):
                    rows = query_result.result_rows
                elif hasattr(query_result, 'data'):
                    rows = query_result.data
                else:
                    rows = list(query_result) if query_result else []
                
                # 创建DataFrame
                columns = ['date', 'code', 'market', 'open', 'high', 'low', 'close', 'preclose', 
                          'volume', 'amount', 'adjustflag', 'turn', 'tradestatus', 'p_change', 'isST']
                result = pd.DataFrame(rows, columns=columns)
            
            client.close()
            
            if result.empty:
                error_msg = f"未找到股票代码 {stock_code} 在指定时间范围内的数据"
                logger.warning(f"数据查询为空 - TaskID: {task_id}, {error_msg}")
                raise Exception(error_msg)
            
            logger.info(f"数据查询成功 - TaskID: {task_id}, Records: {len(result)}")
            
            self.tasks[task_id]["message"] = "正在生成CSV文件..."
            self.tasks[task_id]["progress"] = 60
            
            # 生成CSV文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{stock_code}_{market}_{start_date}_{end_date}_{timestamp}.csv"
            
            # 确保下载目录存在
            download_dir = os.path.join(os.path.dirname(__file__), "downloads")
            if not os.path.exists(download_dir):
                os.makedirs(download_dir)
            
            filepath = os.path.join(download_dir, filename)
            result.to_csv(filepath, index=False, encoding='utf-8-sig')
            
            logger.info(f"CSV文件生成完成 - TaskID: {task_id}, File: {filename}")
            
            self.tasks[task_id]["message"] = "CSV文件生成完成"
            self.tasks[task_id]["progress"] = 80
            
            # 如果需要写入数据库
            if write_to_db:
                self.tasks[task_id]["message"] = "正在写入数据库..."
                logger.info(f"开始数据库写入 - TaskID: {task_id}")
                self._write_to_database(result, task_id)
            
            # 设置下载链接
            download_url = f"/instock/download/{filename}"
            
            self.tasks[task_id]["status"] = "completed"
            self.tasks[task_id]["message"] = f"数据下载完成，共 {len(result)} 条记录"
            self.tasks[task_id]["progress"] = 100
            self.tasks[task_id]["download_url"] = download_url
            self.tasks[task_id]["filename"] = filename
            self.tasks[task_id]["record_count"] = len(result)
            
            logger.info(f"下载任务完成 - TaskID: {task_id}, IP: {client_ip}, "
                       f"Records: {len(result)}, File: {filename}")
            
        except Exception as e:
            error_msg = f"下载失败: {str(e)}"
            logger.error(f"下载任务失败 - TaskID: {task_id}, IP: {client_ip}, Error: {str(e)}")
            
            self.tasks[task_id]["status"] = "failed"
            self.tasks[task_id]["message"] = error_msg
            self.tasks[task_id]["progress"] = 0
    
    @run_on_executor
    def _start_supplement_task(self, task_id, stock_code, missing_dates):
        """启动数据补齐任务（在后台线程中执行）"""
        client_ip = self.tasks[task_id].get('client_ip', 'Unknown')
        try:
            logger.info(f"数据补齐任务开始 - TaskID: {task_id}, IP: {client_ip}, "
                       f"Stock: {stock_code}, Missing Count: {len(missing_dates)}")
            
            self.tasks[task_id]["status"] = "running"
            self.tasks[task_id]["message"] = "正在补齐缺失数据..."
            self.tasks[task_id]["progress"] = 10
            
            market = self._get_market_from_code(stock_code)
            
            # 根据市场选择数据源
            if market in ['SH', 'SZ']:
                # 使用baostock数据源
                logger.info(f"使用baostock补齐数据 - TaskID: {task_id}, Market: {market}")
                success = self._supplement_data_baostock(stock_code, market, missing_dates, task_id)
            else:
                # 其他市场使用akshare或tushare
                logger.info(f"使用其他数据源补齐数据 - TaskID: {task_id}, Market: {market}")
                success = self._supplement_data_others(stock_code, market, missing_dates, task_id)
            
            if success:
                self.tasks[task_id]["status"] = "completed"
                self.tasks[task_id]["message"] = "数据补齐完成"
                self.tasks[task_id]["progress"] = 100
                logger.info(f"数据补齐成功 - TaskID: {task_id}, IP: {client_ip}")
            else:
                self.tasks[task_id]["status"] = "failed"
                self.tasks[task_id]["message"] = "数据补齐失败"
                logger.error(f"数据补齐失败 - TaskID: {task_id}, IP: {client_ip}")
                
        except Exception as e:
            error_msg = f"数据补齐失败: {str(e)}"
            logger.error(f"数据补齐任务异常 - TaskID: {task_id}, IP: {client_ip}, Error: {str(e)}")
            
            self.tasks[task_id]["status"] = "failed"
            self.tasks[task_id]["message"] = error_msg
    
    @run_on_executor
    def _start_batch_supplement_task(self, task_id, check_scope, market, start_date, end_date, missing_stocks):
        """启动批量数据补齐任务（在后台线程中执行）"""
        client_ip = self.tasks[task_id].get('client_ip', 'Unknown')
        try:
            logger.info(f"批量数据补齐任务开始 - TaskID: {task_id}, IP: {client_ip}, "
                       f"Scope: {check_scope}, Market: {market}, Stocks: {len(missing_stocks)}")
            
            self.tasks[task_id]["status"] = "running"
            self.tasks[task_id]["message"] = "正在批量补齐缺失数据..."
            self.tasks[task_id]["progress"] = 10
            
            total_stocks = len(missing_stocks)
            processed_stocks = 0
            success_count = 0
            
            # 按市场分组处理
            sh_stocks = [stock for stock in missing_stocks if stock['market'] == 'SH']
            sz_stocks = [stock for stock in missing_stocks if stock['market'] == 'SZ']
            bj_stocks = [stock for stock in missing_stocks if stock['market'] == 'BJ']
            
            logger.info(f"股票分组统计 - TaskID: {task_id}, SH: {len(sh_stocks)}, SZ: {len(sz_stocks)}, BJ: {len(bj_stocks)}")
            
            # 检查是否有不支持的市场
            if bj_stocks:
                logger.warning(f"检测到 {len(bj_stocks)} 只北京交易所股票，目前暂不支持补齐")
                self.tasks[task_id]["message"] = f"跳过 {len(bj_stocks)} 只不支持的北京交易所股票，处理沪深股票..."
            
            # 处理沪深股票（使用baostock）和北京股票（使用tushare）
            huashen_stocks = sh_stocks + sz_stocks
            for stock_group, market_name, data_source in [(huashen_stocks, '沪深', 'baostock'), (bj_stocks, '北京', 'tushare')]:
                if not stock_group:
                    continue
                    
                logger.info(f"开始处理{market_name}市场股票 - TaskID: {task_id}, Count: {len(stock_group)}, Source: {data_source}")
                
                for stock in stock_group:
                    try:
                        self.tasks[task_id]["message"] = f"正在补齐 {stock['code']}.{stock['market']} 数据..."
                        progress = 10 + (processed_stocks / total_stocks * 80)
                        self.tasks[task_id]["progress"] = int(progress)
                        
                        # 为每个股票生成缺失日期列表
                        # 这里简化处理，使用整个时间范围
                        # 实际应用中可以查询具体的缺失日期
                        market_code = stock['market'].upper()
                        stock_code = stock['code']
                        
                        if market_code in ['SH', 'SZ']:
                            # 使用baostock补齐
                            success = self._supplement_single_stock_baostock(stock_code, market_code, start_date, end_date)
                        elif market_code == 'BJ':
                            # 使用tushare补齐
                            success = self._supplement_single_stock_others(stock_code, market_code, start_date, end_date)
                        else:
                            # 其他市场暂不支持
                            logger.warning(f"股票 {stock_code}.{market_code} 市场暂不支持补齐 - TaskID: {task_id}")
                            success = False
                        
                        if success:
                            success_count += 1
                            logger.info(f"股票 {stock_code}.{market_code} 补齐成功 - TaskID: {task_id}")
                        else:
                            logger.warning(f"股票 {stock_code}.{market_code} 补齐失败 - TaskID: {task_id}")
                        
                        processed_stocks += 1
                        
                    except Exception as e:
                        logger.error(f"股票 {stock['code']}.{stock['market']} 补齐异常 - TaskID: {task_id}, Error: {str(e)}")
                        processed_stocks += 1
            
            # 完成任务
            huashen_count = len(sh_stocks) + len(sz_stocks)
            bj_count = len(bj_stocks)
            
            if bj_count > 0 and huashen_count > 0:
                # 有沪深和北京股票
                if success_count == total_stocks:
                    self.tasks[task_id]["status"] = "completed"
                    self.tasks[task_id]["message"] = f"批量数据补齐完成，成功补齐 {success_count}/{total_stocks} 只股票（含 {huashen_count} 只沪深股票和 {bj_count} 只北京股票）"
                elif success_count > 0:
                    self.tasks[task_id]["status"] = "completed"
                    self.tasks[task_id]["message"] = f"批量数据补齐部分完成，成功补齐 {success_count}/{total_stocks} 只股票（沪深 + 北京市场）"
                else:
                    self.tasks[task_id]["status"] = "failed"
                    self.tasks[task_id]["message"] = f"批量数据补齐失败，0/{total_stocks} 只股票补齐成功"
            elif bj_count > 0:
                # 只有北京股票
                if success_count == bj_count:
                    self.tasks[task_id]["status"] = "completed"
                    self.tasks[task_id]["message"] = f"批量数据补齐完成，成功补齐 {success_count}/{bj_count} 只北京股票"
                elif success_count > 0:
                    self.tasks[task_id]["status"] = "completed"
                    self.tasks[task_id]["message"] = f"批量数据补齐部分完成，成功补齐 {success_count}/{bj_count} 只北京股票"
                else:
                    self.tasks[task_id]["status"] = "failed"
                    self.tasks[task_id]["message"] = f"批量数据补齐失败，0/{bj_count} 只北京股票补齐成功"
            else:
                # 只有沪深股票
                if success_count == total_stocks:
                    self.tasks[task_id]["status"] = "completed"
                    self.tasks[task_id]["message"] = f"批量数据补齐完成，成功补齐 {success_count}/{total_stocks} 只沪深股票"
                elif success_count > 0:
                    self.tasks[task_id]["status"] = "completed"
                    self.tasks[task_id]["message"] = f"批量数据补齐部分完成，成功补齐 {success_count}/{total_stocks} 只沪深股票"
                else:
                    self.tasks[task_id]["status"] = "failed"
                    self.tasks[task_id]["message"] = f"批量数据补齐失败，0/{total_stocks} 只沪深股票补齐成功"
            
            self.tasks[task_id]["progress"] = 100
            self.tasks[task_id]["success_count"] = success_count
            self.tasks[task_id]["total_count"] = total_stocks
            
            logger.info(f"批量数据补齐任务完成 - TaskID: {task_id}, IP: {client_ip}, "
                       f"Success: {success_count}/{total_stocks}")
            
        except Exception as e:
            error_msg = f"批量数据补齐失败: {str(e)}"
            logger.error(f"批量数据补齐任务异常 - TaskID: {task_id}, IP: {client_ip}, Error: {str(e)}")
            
            self.tasks[task_id]["status"] = "failed"
            self.tasks[task_id]["message"] = error_msg
    
    def _supplement_data_baostock(self, stock_code, market, missing_dates, task_id):
        """使用baostock补齐数据"""
        try:
            logger.info(f"开始baostock数据补齐 - TaskID: {task_id}, Stock: {stock_code}, Market: {market}")
            
            # 动态导入baostock
            try:
                import baostock as bs
            except ImportError:
                error_msg = "baostock模块未安装，请运行: pip install baostock"
                logger.error(f"baostock模块导入失败 - TaskID: {task_id}, Error: {error_msg}")
                raise Exception(error_msg)
            
            # 登录baostock
            lg = bs.login()
            if lg.error_code != '0':
                error_msg = f"baostock登录失败: {lg.error_msg}"
                logger.error(f"baostock登录失败 - TaskID: {task_id}, Error: {error_msg}")
                raise Exception("baostock登录失败")
            
            logger.info(f"baostock登录成功 - TaskID: {task_id}")
            
            try:
                # 计算补齐范围
                min_date = min(missing_dates)
                max_date = max(missing_dates)
                
                logger.info(f"数据补齐范围 - TaskID: {task_id}, Date Range: {min_date} to {max_date}")
                
                self.tasks[task_id]["message"] = f"正在从baostock获取数据: {min_date} 到 {max_date}"
                self.tasks[task_id]["progress"] = 30
                
                # 查询数据
                bao_code = f"{market.lower()}.{stock_code}"
                rs = bs.query_history_k_data_plus(
                    bao_code,
                    "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST",
                    start_date=min_date,
                    end_date=max_date,
                    frequency="d",
                    adjustflag="3"
                )
                
                if rs.error_code != '0':
                    error_msg = f"baostock数据查询失败: {rs.error_msg}"
                    logger.error(f"baostock查询失败 - TaskID: {task_id}, Error: {error_msg}")
                    raise Exception(error_msg)
                
                # 收集数据
                data_list = []
                while (rs.error_code == '0') & rs.next():
                    data_list.append(rs.get_row_data())
                
                if not data_list:
                    error_msg = "未获取到数据"
                    logger.warning(f"baostock无数据 - TaskID: {task_id}")
                    raise Exception(error_msg)
                
                logger.info(f"baostock数据获取成功 - TaskID: {task_id}, Records: {len(data_list)}")
                
                # 转换为DataFrame
                df = pd.DataFrame(data_list, columns=rs.fields)
                
                self.tasks[task_id]["message"] = "正在处理和写入数据..."
                self.tasks[task_id]["progress"] = 70
                
                # 处理数据格式
                df = self._process_dataframe_for_clickhouse(df, market)
                
                logger.info(f"数据处理完成 - TaskID: {task_id}, Processed Records: {len(df)}")
                
                # 写入ClickHouse
                if db_engine_module:
                    client = db_engine_module.create_clickhouse_client()
                    if client:
                        client.insert_df('cn_stock_history', df)
                        client.close()
                        
                        logger.info(f"ClickHouse写入成功 - TaskID: {task_id}, Records: {len(df)}")
                        self.tasks[task_id]["message"] = f"成功补齐 {len(df)} 条数据"
                        return True
                    else:
                        error_msg = "无法连接到ClickHouse数据库"
                        logger.error(f"ClickHouse连接失败 - TaskID: {task_id}")
                        raise Exception(error_msg)
                else:
                    error_msg = "数据库引擎模块未加载"
                    logger.error(f"数据库模块未加载 - TaskID: {task_id}")
                    raise Exception(error_msg)
                    
            finally:
                bs.logout()
                logger.info(f"baostock登出完成 - TaskID: {task_id}")
                
        except Exception as e:
            error_msg = f"baostock数据补齐失败: {str(e)}"
            logger.error(f"baostock补齐异常 - TaskID: {task_id}, Error: {str(e)}")
            self.tasks[task_id]["message"] = error_msg
            return False
    
    def _supplement_single_stock_others(self, stock_code, market, start_date, end_date):
        """使用其他数据源（tushare）补齐单个股票数据"""
        try:
            logger.info(f"尝试使用tushare数据源补齐股票 {stock_code}.{market}")
            
            if market == 'BJ':
                # 北京交易所使用tushare数据源
                return self._supplement_data_tushare(stock_code, market, start_date, end_date)
            else:
                logger.warning(f"暂不支持 {market} 市场股票 {stock_code} 的数据补齐")
                return False
                
        except Exception as e:
            logger.error(f"其他数据源补齐失败 - Stock: {stock_code}.{market}, Error: {str(e)}")
            return False
    
    def _supplement_data_others(self, stock_code, market, missing_dates, task_id):
        """使用其他数据源（tushare）补齐数据"""
        try:
            if market == 'BJ':
                # 北京交易所使用tushare数据源
                min_date = min(missing_dates)
                max_date = max(missing_dates)
                return self._supplement_data_tushare(stock_code, market, min_date, max_date, task_id)
            else:
                self.tasks[task_id]["message"] = f"暂不支持 {market} 市场数据补齐"
                return False
        except Exception as e:
            self.tasks[task_id]["message"] = f"数据补齐失败: {str(e)}"
            return False
    
    def _supplement_data_tushare(self, stock_code, market, start_date, end_date, task_id=None):
        """使用tushare补齐数据"""
        try:
            logger.info(f"开始tushare数据补齐 - Stock: {stock_code}, Market: {market}, Date Range: {start_date} to {end_date}")
            
            # 动态导入tushare模块
            try:
                tushare_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'history_data')
                sys.path.append(tushare_path)
                
                import importlib.util
                tushare_spec = importlib.util.spec_from_file_location("tushare_all", os.path.join(tushare_path, "tushare_all.py"))
                if tushare_spec and tushare_spec.loader:
                    tushare_all = importlib.util.module_from_spec(tushare_spec)
                    tushare_spec.loader.exec_module(tushare_all)
                else:
                    raise ImportError("无法加载tushare_all模块")
            except Exception as e:
                error_msg = f"tushare模块导入失败: {str(e)}"
                logger.error(f"tushare模块导入失败 - Error: {error_msg}")
                if task_id:
                    self.tasks[task_id]["message"] = error_msg
                raise Exception(error_msg)
            
            # 创建数据获取器
            try:
                fetcher = tushare_all.StockDataFetcher()
            except Exception as e:
                error_msg = f"tushare初始化失败: {str(e)}，请检查TUSHARE_TOKEN环境变量"
                logger.error(f"tushare初始化失败 - Error: {error_msg}")
                if task_id:
                    self.tasks[task_id]["message"] = error_msg
                raise Exception(error_msg)
            
            logger.info(f"tushare初始化成功")
            
            if task_id:
                self.tasks[task_id]["message"] = f"正在从tushare获取数据: {start_date} 到 {end_date}"
                self.tasks[task_id]["progress"] = 30
            
            # 构造tushare股票代码格式
            ts_code = f"{stock_code}.{market}"
            
            # 转换日期格式为tushare需要的YYYYMMDD格式
            start_date_ts = start_date.replace('-', '')
            end_date_ts = end_date.replace('-', '')
            
            logger.info(f"查询tushare数据 - ts_code: {ts_code}, start: {start_date_ts}, end: {end_date_ts}")
            
            # 获取数据
            df = fetcher.fetch_stock_daily(ts_code, start_date_ts, end_date_ts)
            
            if df is None or df.empty:
                error_msg = f"tushare未获取到数据"
                logger.warning(f"tushare无数据 - ts_code: {ts_code}")
                if task_id:
                    self.tasks[task_id]["message"] = error_msg
                raise Exception(error_msg)
            
            logger.info(f"tushare数据获取成功 - Records: {len(df)}")
            
            if task_id:
                self.tasks[task_id]["message"] = "正在处理和写入数据..."
                self.tasks[task_id]["progress"] = 70
            
            # 处理数据格式转换为ClickHouse表结构
            df_processed = self._process_tushare_dataframe_for_clickhouse(df, stock_code, market)
            
            logger.info(f"tushare数据处理完成 - Processed Records: {len(df_processed)}")
            
            # 写入ClickHouse
            if db_engine_module:
                client = db_engine_module.create_clickhouse_client()
                if client:
                    client.insert_df('cn_stock_history', df_processed)
                    client.close()
                    
                    logger.info(f"ClickHouse写入成功 - Records: {len(df_processed)}")
                    if task_id:
                        self.tasks[task_id]["message"] = f"成功补齐 {len(df_processed)} 条数据"
                    return True
                else:
                    error_msg = "无法连接到ClickHouse数据库"
                    logger.error(f"ClickHouse连接失败")
                    if task_id:
                        self.tasks[task_id]["message"] = error_msg
                    raise Exception(error_msg)
            else:
                error_msg = "数据库引擎模块未加载"
                logger.error(f"数据库模块未加载")
                if task_id:
                    self.tasks[task_id]["message"] = error_msg
                raise Exception(error_msg)
                
        except Exception as e:
            error_msg = f"tushare数据补齐失败: {str(e)}"
            logger.error(f"tushare补齐异常 - Error: {str(e)}")
            if task_id:
                self.tasks[task_id]["message"] = error_msg
            return False
    
    def _process_tushare_dataframe_for_clickhouse(self, df, stock_code, market):
        """处理tushare数据格式使其符合ClickHouse表结构"""
        try:
            # tushare返回的列名映射
            # tushare列: ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
            # ClickHouse列: date, code, market, open, high, low, close, preclose, volume, amount, adjustflag, turn, tradestatus, p_change, isST
            
            df_new = pd.DataFrame()
            
            # 基础字段映射
            df_new['date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d').dt.date
            df_new['code'] = stock_code
            df_new['market'] = market.lower()
            df_new['open'] = pd.to_numeric(df['open'], errors='coerce').fillna(0)
            df_new['high'] = pd.to_numeric(df['high'], errors='coerce').fillna(0)
            df_new['low'] = pd.to_numeric(df['low'], errors='coerce').fillna(0)
            df_new['close'] = pd.to_numeric(df['close'], errors='coerce').fillna(0)
            df_new['preclose'] = pd.to_numeric(df['pre_close'], errors='coerce').fillna(0)
            df_new['volume'] = pd.to_numeric(df['vol'], errors='coerce').fillna(0)  # 成交量(手)
            df_new['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)  # 成交额(千元)
            
            # 涨跌幅
            if 'pct_chg' in df.columns:
                df_new['p_change'] = pd.to_numeric(df['pct_chg'], errors='coerce').fillna(0)
            else:
                df_new['p_change'] = 0
            
            # 设置默认值字段
            df_new['adjustflag'] = 3  # 复权标志，默认后复权
            df_new['turn'] = 0  # 换手率，tushare basic数据中没有，设为0
            df_new['tradestatus'] = 1  # 交易状态，默认正常交易
            df_new['isST'] = 0  # ST标志，默认非ST
            
            # 确保列顺序与表结构一致
            expected_columns = [
                'date', 'code', 'market', 'open', 'high', 'low', 'close', 'preclose',
                'volume', 'amount', 'adjustflag', 'turn', 'tradestatus', 'p_change', 'isST'
            ]
            
            df_result = df_new[expected_columns]
            
            # 按日期升序排列
            df_result = df_result.sort_values('date').reset_index(drop=True)
            
            logger.info(f"tushare数据格式转换完成 - 原始: {len(df)} 条, 处理后: {len(df_result)} 条")
            
            return df_result
            
        except Exception as e:
            raise Exception(f"tushare数据格式转换失败: {str(e)}")
    
    def _supplement_single_stock_baostock(self, stock_code, market, start_date, end_date):
        """使用baostock补齐单个股票数据（用于批量补齐）"""
        try:
            logger.info(f"开始单个股票baostock数据补齐 - Stock: {stock_code}, Market: {market}")
            
            # 动态导入baostock
            try:
                import baostock as bs
            except ImportError:
                logger.error(f"baostock模块未安装")
                return False
            
            # 登录baostock
            lg = bs.login()
            if lg.error_code != '0':
                logger.error(f"baostock登录失败: {lg.error_msg}")
                return False
            
            try:
                # 查询数据
                bao_code = f"{market.lower()}.{stock_code}"
                rs = bs.query_history_k_data_plus(
                    bao_code,
                    "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",
                    adjustflag="3"
                )
                
                if rs.error_code != '0':
                    logger.error(f"baostock数据查询失败: {rs.error_msg}")
                    return False
                
                # 收集数据
                data_list = []
                while (rs.error_code == '0') & rs.next():
                    data_list.append(rs.get_row_data())
                
                if not data_list:
                    logger.warning(f"baostock无数据 - Stock: {stock_code}")
                    return False
                
                # 转换为DataFrame
                df = pd.DataFrame(data_list, columns=rs.fields)
                
                # 处理数据格式
                df_processed = self._process_dataframe_for_clickhouse(df, market)
                
                # 写入ClickHouse
                if db_engine_module:
                    client = db_engine_module.create_clickhouse_client()
                    if client:
                        client.insert_df('cn_stock_history', df_processed)
                        client.close()
                        
                        logger.info(f"单个股票baostock补齐成功 - Stock: {stock_code}, Records: {len(df_processed)}")
                        return True
                    else:
                        logger.error(f"ClickHouse连接失败 - Stock: {stock_code}")
                        return False
                else:
                    logger.error(f"数据库模块未加载 - Stock: {stock_code}")
                    return False
                    
            finally:
                bs.logout()
                
        except Exception as e:
            logger.error(f"单个股票baostock补齐异常 - Stock: {stock_code}, Error: {str(e)}")
            return False
    
    def _process_dataframe_for_clickhouse(self, df, market):
        """处理DataFrame使其符合ClickHouse表结构"""
        try:
            # 处理日期列
            df['date'] = pd.to_datetime(df['date']).dt.date
            
            # 添加市场信息并清理代码
            df['market'] = market.lower()
            df['code'] = df['code'].str.replace(r'^(sh\.|sz\.|bj\.)', '', regex=True)
            
            # 重命名列
            if 'pctChg' in df.columns:
                df.rename(columns={'pctChg': 'p_change'}, inplace=True)
            
            # 处理数值列
            numeric_columns = ['open', 'high', 'low', 'close', 'preclose', 'volume', 'amount', 
                              'adjustflag', 'turn', 'tradestatus', 'p_change', 'isST']
            
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            # 确保列顺序
            expected_columns = [
                'date', 'code', 'market', 'open', 'high', 'low', 'close', 'preclose',
                'volume', 'amount', 'adjustflag', 'turn', 'tradestatus', 'p_change', 'isST'
            ]
            
            for col in expected_columns:
                if col not in df.columns:
                    if col == 'market':
                        df[col] = market.lower()
                    else:
                        df[col] = 0
            
            return df[expected_columns]
            
        except Exception as e:
            raise Exception(f"数据处理失败: {str(e)}")
    
    def _write_to_database(self, df, task_id):
        """写入数据库"""
        try:
            # 检查数据唯一性，避免重复写入
            # 这里可以根据需要实现更复杂的去重逻辑
            
            if db_engine_module:
                client = db_engine_module.create_clickhouse_client()
                if client:
                    # 使用REPLACE模式写入，自动处理重复数据
                    client.insert_df('cn_stock_history', df)
                    client.close()
                    
                    self.tasks[task_id]["message"] += f"，已写入数据库"
                else:
                    self.tasks[task_id]["message"] += f"，数据库写入失败"
            else:
                self.tasks[task_id]["message"] += f"，数据库模块未加载"
                
        except Exception as e:
            self.tasks[task_id]["message"] += f"，数据库写入失败: {str(e)}"


class FileDownloadHandler(webBase.BaseHandler, ABC):
    """文件下载处理器"""
    
    @tornado.gen.coroutine
    def get(self, filename):
        """处理文件下载"""
        client_ip = self.request.remote_ip
        try:
            logger.info(f"文件下载请求 - IP: {client_ip}, File: {filename}")
            
            download_dir = os.path.join(os.path.dirname(__file__), "downloads")
            filepath = os.path.join(download_dir, filename)
            
            if not os.path.exists(filepath):
                logger.warning(f"文件不存在 - IP: {client_ip}, File: {filename}")
                self.set_status(404)
                self.write("文件不存在")
                return
            
            # 获取文件大小
            file_size = os.path.getsize(filepath)
            logger.info(f"开始文件下载 - IP: {client_ip}, File: {filename}, Size: {file_size} bytes")
            
            # 设置下载headers
            self.set_header('Content-Type', 'application/octet-stream')
            self.set_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.set_header('Content-Length', str(file_size))
            
            # 读取文件内容
            bytes_sent = 0
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    self.write(chunk)
                    bytes_sent += len(chunk)
            
            self.finish()
            logger.info(f"文件下载完成 - IP: {client_ip}, File: {filename}, Sent: {bytes_sent} bytes")
            
        except Exception as e:
            logger.error(f"文件下载失败 - IP: {client_ip}, File: {filename}, Error: {str(e)}")
            self.set_status(500)
            self.write(f"下载失败: {str(e)}")
