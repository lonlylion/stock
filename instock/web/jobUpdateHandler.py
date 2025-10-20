#!/usr/local/bin/python3
# -*- coding: utf-8 -*-
import os.path
import sys
import json
import time
import threading
from abc import ABC
import tornado.web

# 在项目运行时，临时将项目路径添加到环境变量
cpath_current = os.path.dirname(os.path.dirname(__file__))
cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
if cpath not in sys.path:
    sys.path.append(cpath)
job_path = os.path.join(cpath, 'instock', 'job')
if job_path not in sys.path:
    sys.path.append(job_path)

import instock.lib.torndb as torndb
import instock.lib.database as mdb
from instock.lib.database_factory import get_database, db_config, DatabaseType
import instock.web.base as webBase
from instock.job import (
    basic_data_daily_job,
    basic_data_other_daily_job,
    basic_data_after_close_daily_job,
    indicators_data_daily_job,
    klinepattern_data_daily_job,
    strategy_data_daily_job,
    backtest_data_daily_job,
    selection_data_daily_job,
    execute_daily_job,
)
from instock.lib.simple_logger import get_logger

# 获取logger
logger = get_logger(__name__)

# 全局变量，用于跟踪任务状态和防止频繁点击
_update_tasks = {}
_task_lock = threading.Lock()

# Job执行映射
JOB_EXECUTORS = {
    'basic_data': {
        'name': '基础数据更新',
        'callable': basic_data_daily_job.main,
        'message': '正在更新基础数据...'
    },
    'basic_data_other': {
        'name': '其他基础数据',
        'callable': basic_data_other_daily_job.main,
        'message': '正在更新其他基础数据...'
    },
    'basic_data_after_close': {
        'name': '收盘后数据',
        'callable': basic_data_after_close_daily_job.main,
        'message': '正在更新收盘后数据...'
    },
    'indicators': {
        'name': '技术指标计算',
        'callable': indicators_data_daily_job.main,
        'message': '正在计算技术指标...'
    },
    'indicators_buy': {
        'name': '买入信号指标',
        'callable': indicators_data_daily_job.main,
        'message': '正在筛选买入信号指标...'
    },
    'indicators_sell': {
        'name': '卖出信号指标',
        'callable': indicators_data_daily_job.main,
        'message': '正在筛选卖出信号指标...'
    },
    'kline_pattern': {
        'name': 'K线形态识别',
        'callable': klinepattern_data_daily_job.main,
        'message': '正在识别K线形态...'
    },
    'strategy': {
        'name': '策略选股',
        'callable': strategy_data_daily_job.main,
        'message': '正在执行策略选股...'
    },
    'selection': {
        'name': '综合选股',
        'callable': selection_data_daily_job.main,
        'message': '正在执行综合选股...'
    },
    'backtest': {
        'name': '策略回测',
        'callable': backtest_data_daily_job.main,
        'message': '正在执行策略回测...'
    },
    'complete': {
        'name': '完整数据更新',
        'callable': execute_daily_job.main,
        'message': '正在执行完整数据更新...'
    }
}

# Job到菜单的映射关系
JOB_MAPPING = {
    # 基础数据相关
    'basic_data': {
        'name': '基础数据更新',
        'script': 'basic_data_daily_job.py',
        'description': '更新股票实时行情、ETF数据等基础数据',
        'tables': ['cn_stock_spot', 'cn_etf_spot'],
        'type': 'basic'
    },
    'basic_data_other': {
        'name': '其他基础数据',
        'script': 'basic_data_other_daily_job.py',
        'description': '更新历史股票数据、尾盘抢筹、大宗交易等',
        'tables': ['cn_stock_history', 'cn_stock_chip_race_end', 'cn_stock_blocktrade'],
        'type': 'basic'
    },
    'basic_data_after_close': {
        'name': '收盘后数据',
        'script': 'basic_data_after_close_daily_job.py',
        'description': '更新收盘后1-2小时才有的数据',
        'tables': [],
        'type': 'basic'
    },
    
    # 指标数据相关
    'indicators': {
        'name': '技术指标计算',
        'script': 'indicators_data_daily_job.py',
        'description': '计算股票技术指标（MACD、KDJ、RSI等）',
        'tables': ['cn_stock_indicators'],
        'type': 'indicators'
    },
    'indicators_buy': {
        'name': '买入信号指标',
        'script': 'indicators_data_daily_job.py',
        'description': '筛选买入信号技术指标',
        'tables': ['cn_stock_indicators_buy'],
        'type': 'indicators'
    },
    'indicators_sell': {
        'name': '卖出信号指标',
        'script': 'indicators_data_daily_job.py',
        'description': '筛选卖出信号技术指标',
        'tables': ['cn_stock_indicators_sell'],
        'type': 'indicators'
    },
    
    # K线形态相关
    'kline_pattern': {
        'name': 'K线形态识别',
        'script': 'klinepattern_data_daily_job.py',
        'description': '识别61种K线形态',
        'tables': ['cn_stock_kline_pattern'],
        'type': 'pattern'
    },
    
    # 策略数据相关
    'strategy': {
        'name': '策略选股',
        'script': 'strategy_data_daily_job.py',
        'description': '执行选股策略（放量上涨、停机坪等）',
        'tables': ['cn_stock_spot_buy'],
        'type': 'strategy'
    },
    
    # 综合选股
    'selection': {
        'name': '综合选股',
        'script': 'selection_data_daily_job.py',
        'description': '基于200多个条件的综合选股',
        'tables': ['cn_stock_selection'],
        'type': 'selection'
    },
    
    # 回测数据
    'backtest': {
        'name': '策略回测',
        'script': 'backtest_data_daily_job.py',
        'description': '对选股策略进行回测验证',
        'tables': [],
        'type': 'backtest'
    },
    
    # 完整更新
    'complete': {
        'name': '完整数据更新',
        'script': 'execute_daily_job.py',
        'description': '执行完整的数据更新流程（所有模块）',
        'tables': ['all'],
        'type': 'complete'
    }
}

# 菜单到Job的映射关系
MENU_TO_JOB = {
    # 股票基本数据相关
    'cn_stock_spot': 'basic_data',
    'cn_stock_history': 'basic_data_other', 
    'cn_stock_chip_race_open': 'basic_data',
    'cn_stock_chip_race_end': 'basic_data_other',
    'cn_stock_limitup_reason': 'basic_data',
    'cn_stock_fund_flow': 'basic_data',
    'cn_stock_bonus': 'basic_data',
    'cn_stock_top': 'basic_data',
    'cn_stock_blocktrade': 'basic_data_other',
    'cn_stock_fund_flow_industry': 'basic_data',
    'cn_stock_fund_flow_concept': 'basic_data',
    'cn_etf_spot': 'basic_data',
    
    # 股票指标数据
    'cn_stock_indicators': 'indicators',
    'cn_stock_indicators_buy': 'indicators_buy',
    'cn_stock_indicators_sell': 'indicators_sell',
    
    # K线形态
    'cn_stock_kline_pattern': 'kline_pattern',
    
    # 策略数据
    'cn_stock_spot_buy': 'strategy',
    
    # 综合选股
    'cn_stock_selection': 'selection'
}

class JobUpdateHandler(webBase.BaseHandler, ABC):
    async def post(self):
        """处理细粒度数据更新请求"""
        try:
            data = json.loads(self.request.body)
            job_type = data.get('job_type', '')  # 具体的job类型
            logger.info(f"Received job update request: {job_type}")
            if not job_type or job_type not in JOB_MAPPING:
                self.write(json.dumps({
                    'success': False,
                    'message': f'无效的job类型: {job_type}',
                    'task_id': None
                }))
                self.finish()
                return
            
            # 检查是否已有任务在执行
            with _task_lock:
                task_key = f"{job_type}_{int(time.time())}"
                if any(task.get('running', False) for task in _update_tasks.values()):
                    self.write(json.dumps({
                        'success': False,
                        'message': '已有数据更新任务在执行中，请稍后再试',
                        'task_id': None
                    }))
                    self.finish()
                    return
                
                # 标记任务开始
                executor = JOB_EXECUTORS.get(job_type)
                if not executor:
                    self.write(json.dumps({
                        'success': False,
                        'message': f'未找到 {job_type} 对应的执行器',
                        'task_id': None
                    }))
                    self.finish()
                    return
                _update_tasks[task_key] = {
                    'running': True,
                    'start_time': time.time(),
                    'job_type': job_type,
                    'progress': 0,
                    'message': '任务开始执行',
                    'executor': executor['name']
                }
            
            # 异步执行更新任务
            def run_job():
                try:
                    job_info = JOB_MAPPING[job_type]
                    executor = JOB_EXECUTORS.get(job_type)
                    if not executor:
                        raise RuntimeError(f'未找到 {job_type} 对应的执行器')
                    
                    with _task_lock:
                        _update_tasks[task_key]['message'] = executor['message']
                    
                    logger.info(f"Starting job callable for {job_type}")
                    original_cwd = os.getcwd()
                    os.chdir(cpath)
                    try:
                        executor['callable']()
                    finally:
                        os.chdir(original_cwd)
                    logger.info(f"Finished job callable for {job_type}")
                    
                    with _task_lock:
                        _update_tasks[task_key]['progress'] = 100
                        _update_tasks[task_key]['message'] = f'{job_info["name"]}执行完成'
                        _update_tasks[task_key]['success'] = True
                        _update_tasks[task_key]['running'] = False
                        _update_tasks[task_key]['end_time'] = time.time()
                        
                except Exception as e:
                    logger.exception(f"Job {job_type} execution failed")
                    with _task_lock:
                        _update_tasks[task_key]['progress'] = 100
                        executor_name = JOB_EXECUTORS.get(job_type, {}).get('name', job_type)
                        _update_tasks[task_key]['message'] = f'{executor_name}执行异常: {str(e)}'
                        _update_tasks[task_key]['success'] = False
                        _update_tasks[task_key]['running'] = False
                        _update_tasks[task_key]['end_time'] = time.time()
            
            # 启动后台线程执行更新任务
            thread = threading.Thread(target=run_job)
            thread.daemon = True
            thread.start()
            
            self.write(json.dumps({
                'success': True,
                'message': f'{JOB_MAPPING[job_type]["name"]}任务已开始执行',
                'task_id': task_key,
                'job_info': JOB_MAPPING[job_type]
            }))
            self.finish()
            
        except Exception as e:
            with _task_lock:
                if task_key in _update_tasks:
                    _update_tasks[task_key]['running'] = False
            
            self.write(json.dumps({
                'success': False,
                'message': f'请求处理失败: {str(e)}',
                'task_id': None
            }))
            logger.exception(f"Job update request failed: {str(e)}")
            self.finish()

class JobUpdateStatusHandler(webBase.BaseHandler, ABC):
    def get(self):
        """获取数据更新任务状态"""
        try:
            task_key = self.get_argument('task_id', '')
            logger.info(f"Received job update status request: {task_key}")
            with _task_lock:
                if task_key and task_key in _update_tasks:
                    task_info = _update_tasks[task_key]
                    result = {
                        'running': task_info.get('running', False),
                        'progress': task_info.get('progress', 0),
                        'message': task_info.get('message', '无任务执行'),
                        'success': task_info.get('success', None),
                        'start_time': task_info.get('start_time', None),
                        'end_time': task_info.get('end_time', None),
                        'job_type': task_info.get('job_type', ''),
                        'job_info': JOB_MAPPING.get(task_info.get('job_type', ''), {})
                    }
                    logger.info(f"Job status for {task_key}: {result}")
                else:
                    # 返回所有活跃任务
                    active_tasks = {}
                    for key, task in _update_tasks.items():
                        if task.get('running', False):
                            active_tasks[key] = {
                                'running': task.get('running', False),
                                'progress': task.get('progress', 0),
                                'message': task.get('message', '无任务执行'),
                                'job_type': task.get('job_type', ''),
                                'job_info': JOB_MAPPING.get(task.get('job_type', ''), {})
                            }
                    
                    if active_tasks:
                        result = {'has_active_tasks': True, 'active_tasks': active_tasks}
                    else:
                        result = {'has_active_tasks': False, 'message': '无活跃任务'}
            
            self.write(json.dumps({
                'success': True,
                'data': result
            }))
            
        except Exception as e:
            self.write(json.dumps({
                'success': False,
                'message': f'获取状态失败: {str(e)}'
            }))

class JobListHandler(webBase.BaseHandler, ABC):
    def get(self):
        """获取可用的job列表"""
        try:
            job_type = self.get_argument('type', '')
            
            if job_type:
                # 返回特定类型的job
                filtered_jobs = {k: v for k, v in JOB_MAPPING.items() if v.get('type') == job_type}
                result = filtered_jobs
            else:
                # 返回所有job
                result = JOB_MAPPING
            
            self.write(json.dumps({
                'success': True,
                'data': result
            }))
            
        except Exception as e:
            logger.exception(f"Failed to get job list: {str(e)}")
            self.write(json.dumps({
                'success': False,
                'message': f'获取job列表失败: {str(e)}'
            }))

class MenuToJobMappingHandler(webBase.BaseHandler, ABC):
    def get(self):
        """获取菜单到job的映射关系"""
        try:
            table_name = self.get_argument('table', '')
            
            if table_name:
                job_type = MENU_TO_JOB.get(table_name, '')
                if job_type:
                    result = {
                        'table_name': table_name,
                        'job_type': job_type,
                        'job_info': JOB_MAPPING.get(job_type, {})
                    }
                else:
                    result = {'table_name': table_name, 'job_type': None, 'message': '未找到对应的job'}
            else:
                result = MENU_TO_JOB
            
            self.write(json.dumps({
                'success': True,
                'data': result
            }))
            
        except Exception as e:
            logger.exception(f"Failed to get menu to job mapping: {str(e)}")
            self.write(json.dumps({
                'success': False,
                'message': f'获取映射关系失败: {str(e)}'
            }))