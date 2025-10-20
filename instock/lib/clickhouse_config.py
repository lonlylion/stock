#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ClickHouse统一配置文件
提供所有ClickHouse配置的单一来源
"""

import os
from typing import Dict, Any

__author__ = 'system'
__date__ = '2025/10/18'

class ClickHouseConfig:
    """ClickHouse统一配置管理"""
    
    # 默认配置
    DEFAULT_CONFIG = {
        'host': '192.168.1.6',
        'port': 8123,          # HTTP端口
        'tcp_port': 9000,      # TCP端口
        'username': 'root',
        'password': '123456',
        'database': 'instockdb'
    }
    
    # 环境变量映射
    ENV_MAPPINGS = {
        'host': 'CLICKHOUSE_HOST',
        'port': 'CLICKHOUSE_PORT',
        'tcp_port': 'CLICKHOUSE_TCP_PORT',
        'username': 'CLICKHOUSE_USER',
        'password': 'CLICKHOUSE_PASSWORD',
        'database': 'CLICKHOUSE_DATABASE'
    }
    
    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """获取统一的ClickHouse配置"""
        config = cls.DEFAULT_CONFIG.copy()
        
        # 从环境变量覆盖配置
        for key, env_var in cls.ENV_MAPPINGS.items():
            env_value = os.environ.get(env_var)
            if env_value is not None:
                if key == 'port' or key == 'tcp_port':
                    config[key] = int(env_value)
                else:
                    config[key] = env_value
        
        return config
    
    @classmethod
    def get_connection_string(cls, config: Dict[str, Any] = None) -> str:
        """获取ClickHouse连接字符串"""
        if config is None:
            config = cls.get_config()
        
        return f"clickhouse://{config['username']}:{config['password']}@{config['host']}:{config['port']}/{config['database']}"
    
    @classmethod
    def validate_config(cls, config: Dict[str, Any] = None) -> bool:
        """验证配置完整性"""
        if config is None:
            config = cls.get_config()
        
        required_keys = ['host', 'port', 'username', 'database']
        for key in required_keys:
            if key not in config or not config[key]:
                return False
        
        return True
    
    @classmethod
    def print_config(cls, config: Dict[str, Any] = None, hide_password: bool = True):
        """打印当前配置（用于调试）"""
        if config is None:
            config = cls.get_config()
        
        print("ClickHouse Configuration:")
        for key, value in config.items():
            if key == 'password' and hide_password and value:
                print(f"  {key}: {'*' * len(str(value))}")
            else:
                print(f"  {key}: {value}")

# 全局配置实例
clickhouse_config = ClickHouseConfig.get_config()

# 便利函数
def get_clickhouse_config() -> Dict[str, Any]:
    """获取ClickHouse配置"""
    return ClickHouseConfig.get_config()

def validate_clickhouse_config() -> bool:
    """验证ClickHouse配置"""
    return ClickHouseConfig.validate_config()

if __name__ == "__main__":
    # 测试配置
    print("Current ClickHouse Configuration:")
    ClickHouseConfig.print_config()
    
    # 验证配置
    if validate_clickhouse_config():
        print("\n✅ Configuration is valid")
    else:
        print("\n❌ Configuration is invalid")
