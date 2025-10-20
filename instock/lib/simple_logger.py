#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
InStock 简单日志模块

特点:
- 轻量级，即插即用
- 自动创建日志目录
- 支持控制台和文件输出
- 自动日志轮转
- 简单的配置

使用方式:
    from instock.lib.simple_logger import get_logger
    
    logger = get_logger(__name__)
    logger.info("这是一条日志")
    
    # 或者指定日志文件
    logger = get_logger(__name__, log_file="custom.log")
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from typing import Optional

__author__ = 'InStock Team'
__date__ = '2024/10/17'

# 全局配置
DEFAULT_LOG_DIR = "logs"
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_LEVEL = logging.INFO
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10MB
DEFAULT_BACKUP_COUNT = 3

# 缓存已创建的logger，避免重复创建
_loggers = {}


def get_logger(name: str, 
               log_file: Optional[str] = None,
               log_dir: Optional[str] = None,
               level: str = "INFO",
               console: bool = True,
               file_output: bool = True) -> logging.Logger:
    """
    获取日志器 - 简单易用的接口
    
    Args:
        name: 日志器名称，通常使用 __name__
        log_file: 日志文件名，如果为None则使用 name.log
        log_dir: 日志目录，如果为None则使用默认目录
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console: 是否输出到控制台
        file_output: 是否输出到文件
        
    Returns:
        logging.Logger: 配置好的日志器
    """
    # 生成唯一的logger key
    logger_key = f"{name}_{log_file}_{log_dir}_{level}_{console}_{file_output}"
    
    # 如果已经创建过，直接返回
    if logger_key in _loggers:
        return _loggers[logger_key]
    
    # 创建logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # 清除现有handlers（避免重复添加）
    logger.handlers.clear()
    
    # 创建格式器
    formatter = logging.Formatter(DEFAULT_FORMAT, DEFAULT_DATE_FORMAT)
    
    # 控制台输出
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, level.upper()))
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # 文件输出
    if file_output:
        # 确定日志目录
        if log_dir is None:
            # 尝试智能确定日志目录
            if 'instock' in name:
                # 如果是instock模块，使用instock/log
                current_dir = os.path.dirname(os.path.dirname(__file__))
                log_dir = os.path.join(current_dir, 'log')
            else:
                # 其他情况使用当前目录下的logs
                log_dir = DEFAULT_LOG_DIR
        
        # 创建日志目录
        os.makedirs(log_dir, exist_ok=True)
        
        # 确定日志文件名
        if log_file is None:
            # 从name生成文件名
            clean_name = name.replace('instock.', '').replace('.', '_')
            log_file = f"{clean_name}.log"
        
        # 完整的日志文件路径
        log_path = os.path.join(log_dir, log_file)
        
        # 创建文件处理器（带轮转）
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=DEFAULT_MAX_BYTES,
            backupCount=DEFAULT_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # 缓存logger
    _loggers[logger_key] = logger
    
    return logger


def info(message: str, name: str = "instock"):
    """快捷info日志函数"""
    logger = get_logger(name)
    logger.info(message)


def error(message: str, name: str = "instock"):
    """快捷error日志函数"""
    logger = get_logger(name)
    logger.error(message)


def warning(message: str, name: str = "instock"):
    """快捷warning日志函数"""
    logger = get_logger(name)
    logger.warning(message)


def debug(message: str, name: str = "instock"):
    """快捷debug日志函数"""
    logger = get_logger(name, level="DEBUG")
    logger.debug(message)


def log_performance(func):
    """
    简单的性能监控装饰器
    
    使用方式:
        @log_performance
        def my_function():
            pass
    """
    def wrapper(*args, **kwargs):
        import time
        
        logger = get_logger(f"performance.{func.__module__}.{func.__name__}")
        
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            logger.info(f"函数 {func.__name__} 执行成功，耗时: {duration:.3f}秒")
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"函数 {func.__name__} 执行失败，耗时: {duration:.3f}秒，错误: {e}")
            raise
    
    return wrapper


def setup_basic_logging(log_dir: str = None, level: str = "INFO"):
    """
    设置基础日志配置（可选使用）
    
    Args:
        log_dir: 日志目录
        level: 日志级别
    """
    global DEFAULT_LOG_DIR, DEFAULT_LEVEL
    
    if log_dir:
        DEFAULT_LOG_DIR = log_dir
        os.makedirs(log_dir, exist_ok=True)
    
    DEFAULT_LEVEL = getattr(logging, level.upper())
    
    # 配置根logger
    logging.basicConfig(
        level=DEFAULT_LEVEL,
        format=DEFAULT_FORMAT,
        datefmt=DEFAULT_DATE_FORMAT
    )


# 便捷的模块级logger
def get_module_logger(module_file: str, level: str = "INFO") -> logging.Logger:
    """
    根据模块文件路径获取logger
    
    Args:
        module_file: 通常传入 __file__
        level: 日志级别
        
    Returns:
        logging.Logger: 配置好的日志器
        
    使用方式:
        logger = get_module_logger(__file__)
    """
    # 从文件路径生成模块名
    module_name = os.path.splitext(os.path.basename(module_file))[0]
    
    # 如果在instock目录下，添加路径信息
    if 'instock' in module_file:
        parts = module_file.split(os.sep)
        if 'instock' in parts:
            instock_index = parts.index('instock')
            module_parts = parts[instock_index:]
            module_name = '.'.join(module_parts).replace('.py', '')
    
    return get_logger(module_name, level=level)


if __name__ == "__main__":
    # 测试代码
    print("测试简单日志模块...")
    
    # 基本使用
    logger = get_logger("test_module")
    logger.info("这是一条信息日志")
    logger.warning("这是一条警告日志")
    logger.error("这是一条错误日志")
    
    # 自定义日志文件
    custom_logger = get_logger("custom", log_file="custom_test.log")
    custom_logger.info("这是自定义日志文件的日志")
    
    # 只输出到控制台
    console_logger = get_logger("console_only", file_output=False)
    console_logger.info("这条日志只在控制台显示")
    
    # 只输出到文件
    file_logger = get_logger("file_only", console=False)
    file_logger.info("这条日志只在文件中保存")
    
    # 使用快捷函数
    info("使用快捷info函数")
    error("使用快捷error函数")
    
    # 测试性能装饰器
    @log_performance
    def test_function():
        import time
        time.sleep(0.1)
        return "测试完成"
    
    result = test_function()
    
    # 测试模块logger
    module_logger = get_module_logger(__file__)
    module_logger.info("使用模块logger记录日志")
    
    print("测试完成，请检查生成的日志文件")