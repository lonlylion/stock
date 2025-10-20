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


from instock.lib.progress_tracker import clear as progress_clear
from instock.lib.progress_tracker import get_many as progress_get_many
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

PROGRESS_GROUPS = {
    'basic': ['stock_spot', 'fund_etf'],
    'basic_other': [],
    'after_close': [],
    'indicators': [],
    'kline': [],
    'strategy': [],
    'selection': [],
    'backtest': [],
    'full': ['stock_spot', 'fund_etf'],
    'complete': ['stock_spot', 'fund_etf'],
}


def _collect_progress(job_key):
    if not job_key:
        return {}
    keys = PROGRESS_GROUPS.get(job_key, [])
    if not keys:
        return {}
    return progress_get_many(keys)


def _compute_progress_percent(details):
    if not details:
        return None
    values = []
    for info in details.values():
        if not info:
            continue
        progress = info.get('progress')
        if progress is not None:
            values.append(progress)
        else:
            current = info.get('current')
            total = info.get('total')
            if current is not None and total:
                try:
                    values.append(round(current / total * 100, 2))
                except ZeroDivisionError:
                    continue
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _collect_progress(job_key):
    if not job_key:
        return {}
    groups = PROGRESS_GROUPS.get(job_key, [])
    if not groups:
        return {}
    return progress_get_many(groups)


def _compute_progress_percent(target):
    if isinstance(target, dict):
        details = target
    else:
        details = _collect_progress(target)
    if not details:
        return None
    values = []
    for info in details.values():
        if not info:
            continue
        progress = info.get('progress')
        if progress is not None:
            values.append(progress)
        else:
            current = info.get('current')
            total = info.get('total')
            if current is not None and total:
                try:
                    values.append(round(current / total * 100, 2))
                except ZeroDivisionError:
                    continue
    if not values:
        return None
    return round(sum(values) / len(values), 2)

JOB_EXECUTORS = {
    'basic': {
        'name': '基础数据更新',
        'callable': basic_data_daily_job.main,
        'message': '正在更新基础数据...'
    },
    'basic_other': {
        'name': '其他基础数据更新',
        'callable': basic_data_other_daily_job.main,
        'message': '正在更新其他基础数据...'
    },
    'after_close': {
        'name': '收盘后数据更新',
        'callable': basic_data_after_close_daily_job.main,
        'message': '正在更新收盘后数据...'
    },
    'indicators': {
        'name': '技术指标计算',
        'callable': indicators_data_daily_job.main,
        'message': '正在计算技术指标...'
    },
    'kline': {
        'name': 'K线形态识别',
        'callable': klinepattern_data_daily_job.main,
        'message': '正在识别K线形态...'
    },
    'strategy': {
        'name': '策略选股计算',
        'callable': strategy_data_daily_job.main,
        'message': '正在执行策略选股...'
    },
    'selection': {
        'name': '综合选股计算',
        'callable': selection_data_daily_job.main,
        'message': '正在执行综合选股...'
    },
    'backtest': {
        'name': '策略回测',
        'callable': backtest_data_daily_job.main,
        'message': '正在执行策略回测...'
    },
    'full': {
        'name': '完整数据更新',
        'callable': execute_daily_job.main,
        'message': '正在执行完整数据更新...'
    },
    'complete': {
        'name': '完整数据更新',
        'callable': execute_daily_job.main,
        'message': '正在执行完整数据更新...'
    }
}

class DataUpdateHandler(webBase.BaseHandler, ABC):
    @tornado.web.authenticated
    async def post(self):
        """处理数据更新请求"""
        try:
            data = json.loads(self.request.body)
            update_type = data.get('type', 'full')  # full: 全部数据, basic: 基础数据
            _update_tasks['cwd'] = os.getcwd()
            
            # 检查是否已有任务在执行
            with _task_lock:
                if _update_tasks.get('running', False):
                    self.write(json.dumps({
                        'success': False,
                        'message': '已有数据更新任务在执行中，请稍后再试',
                        'task_id': None
                    }))
                    self.finish()
                    return
                
                # 标记任务开始
                _update_tasks['running'] = True
                _update_tasks['start_time'] = time.time()
                _update_tasks['type'] = update_type
                _update_tasks['progress'] = 0
                _update_tasks['message'] = '任务开始执行'
                _update_tasks['success'] = None
            
            job_key = update_type if update_type in JOB_EXECUTORS else 'full'
            job_info = JOB_EXECUTORS[job_key]
            _update_tasks['job'] = job_key
            
            for key in PROGRESS_GROUPS.get(job_key, []):
                progress_clear(key)
            
            # 异步执行更新任务
            def run_update():
                try:
                    with _task_lock:
                        _update_tasks['message'] = job_info['message']
                    
                    logger.info(f"Data update handler starting job: {job_key}")
                    _update_tasks['progress_details'] = {}
                    original_cwd = os.getcwd()
                    os.chdir(cpath)
                    try:
                        job_info['callable']()
                    finally:
                        os.chdir(original_cwd)
                    logger.info(f"Data update handler finished job: {job_key}")
                    
                    with _task_lock:
                        details = _collect_progress(job_key)
                        aggregated = _compute_progress_percent(details)
                        _update_tasks['progress'] = aggregated if aggregated is not None else 100
                        _update_tasks['progress_details'] = details
                        _update_tasks['message'] = f"{job_info['name']}执行完成"
                        _update_tasks['success'] = True
                        _update_tasks['running'] = False
                        _update_tasks['end_time'] = time.time()
                        
                except Exception as e:
                    logger.exception(f"Data update job '{job_key}' failed")
                    with _task_lock:
                        details = _collect_progress(job_key)
                        aggregated = _compute_progress_percent(details)
                        _update_tasks['progress'] = aggregated if aggregated is not None else 100
                        _update_tasks['progress_details'] = details
                        _update_tasks['message'] = f"{job_info['name']}执行异常: {str(e)}"
                        _update_tasks['success'] = False
                        _update_tasks['running'] = False
                        _update_tasks['end_time'] = time.time()
            
                finally:
                    for key in PROGRESS_GROUPS.get(job_key, []):
                        progress_clear(key)

            # 启动后台线程执行更新任务
            thread = threading.Thread(target=run_update)
            thread.daemon = True
            thread.start()
            
            self.write(json.dumps({
                'success': True,
                'message': '数据更新任务已开始执行',
                'task_id': int(time.time())
            }))
            self.finish()
            
        except Exception as e:
            with _task_lock:
                _update_tasks['running'] = False
            logger.exception(f"Data update request failed: {str(e)}")
            self.write(json.dumps({
                'success': False,
                'message': f'请求处理失败: {str(e)}',
                'task_id': None
            }))
            self.finish()

class DataUpdateStatusHandler(webBase.BaseHandler, ABC):
    @tornado.web.authenticated
    def get(self):
        """获取数据更新任务状态"""
        try:
            with _task_lock:
                task_info = {
                    'running': _update_tasks.get('running', False),
                    'progress': _update_tasks.get('progress', 0),
                    'message': _update_tasks.get('message', '无任务执行'),
                    'success': _update_tasks.get('success', None),
                    'start_time': _update_tasks.get('start_time', None),
                    'end_time': _update_tasks.get('end_time', None),
                    'type': _update_tasks.get('type', 'full'),
                    'job': _update_tasks.get('job', None)
                }
                progress_details = _collect_progress(task_info['job'])
                if task_info['running']:
                    aggregated = _compute_progress_percent(progress_details)
                    if aggregated is not None:
                        task_info['progress'] = aggregated
                task_info['progress_details'] = progress_details
            
            self.write(json.dumps({
                'success': True,
                'data': task_info
            }))
            
        except Exception as e:
            logger.exception(f"Failed to get data update status: {str(e)}")
            self.write(json.dumps({
                'success': False,
                'message': f'获取状态失败: {str(e)}'
            }))

class DataCheckHandler(webBase.BaseHandler, ABC):
    @tornado.web.authenticated
    def get(self):
        """检查数据是否存在"""
        try:
            table_name = self.get_argument('table', '')
            date = self.get_argument('date', '')
            
            if not table_name:
                self.write(json.dumps({
                    'success': False,
                    'message': '缺少表名参数',
                    'has_data': False
                }))
                return
            
            # 检查指定表是否有数据
            sql = f"SELECT COUNT(*) as count FROM `{table_name}`"
            if date:
                sql += f" WHERE `date` = '{date}'"
            
            result = self.db.query(sql)
            count = result[0]['count'] if result else 0
            
            self.write(json.dumps({
                'success': True,
                'has_data': count > 0,
                'count': count
            }))
            
        except Exception as e:
            logger.exception(f"Data check failed: {str(e)}")
            self.write(json.dumps({
                'success': False,
                'message': f'数据检查失败: {str(e)}',
                'has_data': False
            }))