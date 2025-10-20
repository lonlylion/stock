#!/usr/local/bin/python3
# -*- coding: utf-8 -*-


import json
import os

from abc import ABC
import tornado.web

# 在项目运行时，临时将项目路径添加到环境变量
cpath_current = os.path.dirname(os.path.dirname(__file__))
cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
import sys
sys.path.append(cpath)
import instock.web.base as webBase
from instock.lib.simple_logger import get_logger
logger = get_logger(__name__)

# 配置文件路径
CONFIG_FILE = os.path.join(cpath, 'instock', 'config', 'system_config.json')

class ConfigHandler(webBase.BaseHandler, ABC):
    """配置管理处理器"""
    
    def get(self):
        """获取配置"""
        try:
            config_type = self.get_argument('config_type', 'all')
            
            # 读取配置文件
            config_data = self._read_config()
            
            if config_type == 'all':
                result = config_data
            else:
                result = config_data.get(config_type, {})
            
            self.write(json.dumps({
                'success': True,
                'data': result
            }))
            
        except Exception as e:
            logger.error(f"获取配置失败: {e}")
            self.write(json.dumps({
                'success': False,
                'message': f'获取配置失败: {str(e)}'
            }))
    
    def post(self):
        """保存配置"""
        try:
            data = json.loads(self.request.body)
            config_type = data.get('config_type')
            config_data = data.get('config_data', {})
            
            if not config_type:
                self.write(json.dumps({
                    'success': False,
                    'message': '配置类型不能为空'
                }))
                return
            
            # 读取现有配置
            current_config = self._read_config()
            
            # 更新配置
            current_config[config_type] = config_data
            
            # 保存配置
            self._save_config(current_config)
            
            self.write(json.dumps({
                'success': True,
                'message': '配置保存成功'
            }))
            
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            self.write(json.dumps({
                'success': False,
                'message': f'保存配置失败: {str(e)}'
            }))
    
    def _read_config(self):
        """读取配置文件"""
        # 确保配置目录存在
        config_dir = os.path.dirname(CONFIG_FILE)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
            # 如果配置文件不存在，创建默认配置
            if not os.path.exists(CONFIG_FILE):
                default_config = {
                    'proxy': {
                        'authKey': '',
                        'password': '',
                        'poolSize': 5,
                        'timeout': 10,
                        'cacheTime': 24
                    },
                    'ai': {
                        'apiKey': '',
                        'baseUrl': 'https://api.openai.com/v1',
                        'model': 'gpt-3.5-turbo',
                        'temperature': 0.7,
                        'maxTokens': 2000
                    },
                    'data_source': {
                        'tushareToken': '',
                        'refreshInterval': 60,
                        'retentionDays': 365,
                        'maxConcurrentRequests': 5,
                        'requestTimeout': 30
                    }
                }
                self._save_config(default_config)
                return default_config
        
        # 读取配置文件
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            # 如果配置文件损坏，创建默认配置
            default_config = {
                'proxy': {
                    'authKey': '',
                    'password': '',
                    'poolSize': 5,
                    'timeout': 10,
                    'cacheTime': 24
                },
                'ai': {
                    'apiKey': '',
                    'baseUrl': 'https://api.openai.com/v1',
                    'model': 'gpt-3.5-turbo',
                    'temperature': 0.7,
                    'maxTokens': 2000
                },
                'data_source': {
                    'tushareToken': '',
                    'refreshInterval': 60,
                    'retentionDays': 365,
                    'maxConcurrentRequests': 5,
                    'requestTimeout': 30
                }
            }
            self._save_config(default_config)
            return default_config
    
    def _save_config(self, config_data):
        """保存配置文件"""
        # 确保配置目录存在
        config_dir = os.path.dirname(CONFIG_FILE)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        # 保存配置文件
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)


class GetConfigHandler(webBase.BaseHandler, ABC):
    """获取配置的简化处理器"""
    
    def get(self):
        """获取所有配置"""
        try:
            # 直接读取配置文件
            config_data = self._read_config()
            
            self.write(json.dumps({
                'success': True,
                'data': config_data
            }))
            
        except Exception as e:
            logger.error(f"获取配置失败: {e}")
            self.write(json.dumps({
                'success': False,
                'message': f'获取配置失败: {str(e)}'
            }))
    
    def _read_config(self):
        """读取配置文件"""
        # 确保配置目录存在
        config_dir = os.path.dirname(CONFIG_FILE)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        # 如果配置文件不存在，创建默认配置
        if not os.path.exists(CONFIG_FILE):
            default_config = {
                'proxy': {
                    'authKey': '',
                    'password': '',
                    'poolSize': 5,
                    'timeout': 10,
                    'cacheTime': 24
                },
                'ai': {
                    'apiKey': '',
                    'baseUrl': 'https://api.openai.com/v1',
                    'model': 'gpt-3.5-turbo',
                    'temperature': 0.7,
                    'maxTokens': 2000
                },
                'data_source': {
                    'tushareToken': '',
                    'refreshInterval': 60,
                    'retentionDays': 365,
                    'maxConcurrentRequests': 5,
                    'requestTimeout': 30
                }
            }
            self._save_config(default_config)
            return default_config
        
        # 读取配置文件
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            # 如果配置文件损坏，创建默认配置
            default_config = {
                'proxy': {
                    'authKey': '',
                    'password': '',
                    'poolSize': 5,
                    'timeout': 10,
                    'cacheTime': 24
                },
                'ai': {
                    'apiKey': '',
                    'baseUrl': 'https://api.openai.com/v1',
                    'model': 'gpt-3.5-turbo',
                    'temperature': 0.7,
                    'maxTokens': 2000
                },
                'data_source': {
                    'tushareToken': '',
                    'refreshInterval': 60,
                    'retentionDays': 365,
                    'maxConcurrentRequests': 5,
                    'requestTimeout': 30
                }
            }
            self._save_config(default_config)
            return default_config
    
    def _save_config(self, config_data):
        """保存配置文件"""
        # 确保配置目录存在
        config_dir = os.path.dirname(CONFIG_FILE)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        # 保存配置文件
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)


class SaveConfigHandler(webBase.BaseHandler, ABC):
    """保存配置的简化处理器"""
    
    def post(self):
        """保存配置"""
        try:
            data = json.loads(self.request.body)
            config_type = data.get('config_type')
            config_data = data.get('config_data', {})
            
            if not config_type:
                self.write(json.dumps({
                    'success': False,
                    'message': '配置类型不能为空'
                }))
                return
            
            # 读取现有配置
            current_config = self._read_config()
            
            # 更新配置
            current_config[config_type] = config_data
            
            # 保存配置
            self._save_config(current_config)
            
            self.write(json.dumps({
                'success': True,
                'message': '配置保存成功'
            }))
            
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            self.write(json.dumps({
                'success': False,
                'message': f'保存配置失败: {str(e)}'
            }))
    
    def _read_config(self):
        """读取配置文件"""
        # 确保配置目录存在
        config_dir = os.path.dirname(CONFIG_FILE)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        # 如果配置文件不存在，创建默认配置
        if not os.path.exists(CONFIG_FILE):
            default_config = {
                'proxy': {
                    'authKey': '',
                    'password': '',
                    'poolSize': 5,
                    'timeout': 10,
                    'cacheTime': 24
                },
                'ai': {
                    'apiKey': '',
                    'baseUrl': 'https://api.openai.com/v1',
                    'model': 'gpt-3.5-turbo',
                    'temperature': 0.7,
                    'maxTokens': 2000
                },
                'data_source': {
                    'tushareToken': '',
                    'refreshInterval': 60,
                    'retentionDays': 365,
                    'maxConcurrentRequests': 5,
                    'requestTimeout': 30
                }
            }
            self._save_config(default_config)
            return default_config
        
        # 读取配置文件
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            # 如果配置文件损坏，创建默认配置
            default_config = {
                'proxy': {
                    'authKey': '',
                    'password': '',
                    'poolSize': 5,
                    'timeout': 10,
                    'cacheTime': 24
                },
                'ai': {
                    'apiKey': '',
                    'baseUrl': 'https://api.openai.com/v1',
                    'model': 'gpt-3.5-turbo',
                    'temperature': 0.7,
                    'maxTokens': 2000
                },
                'data_source': {
                    'tushareToken': '',
                    'refreshInterval': 60,
                    'retentionDays': 365,
                    'maxConcurrentRequests': 5,
                    'requestTimeout': 30
                }
            }
            self._save_config(default_config)
            return default_config
    
    def _save_config(self, config_data):
        """保存配置文件"""
        # 确保配置目录存在
        config_dir = os.path.dirname(CONFIG_FILE)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        # 保存配置文件
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)