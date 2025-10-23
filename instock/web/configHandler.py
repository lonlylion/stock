#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

"""Handlers for system configuration management."""

import copy
import json
import os
import re
import sys
import time
from typing import Any, Dict, Iterable, List, Tuple

from abc import ABC
import requests
import tornado.web

# 在项目运行时，临时将项目路径添加到环境变量
cpath_current = os.path.dirname(os.path.dirname(__file__))
cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
if cpath not in sys.path:
    sys.path.append(cpath)
import instock.web.base as webBase
from instock.lib.simple_logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

CONFIG_FILE = os.path.join(cpath, 'instock', 'config', 'system_config.json')
CRON_FILE_PATH = os.path.join(cpath, 'cron', 'cron.stock_job')
PYTHON_BIN = os.path.join(cpath, '.venv', 'bin', 'python')
JOB_SCRIPT = os.path.join(cpath, 'instock', 'job', 'execute_daily_job.py')
CRON_LOG_FILE = os.path.join(cpath, 'instock', 'log', 'cron_stock_job.log')
MAX_SCHEDULE_ENTRIES = 20

DEFAULT_AI_CONFIG: Dict[str, Any] = {
    'apiKey': '',
    'baseUrl': 'https://api.openai.com/v1',
    'model': 'gpt-3.5-turbo',
    'temperature': 0.7,
    'maxTokens': 2000,
}

DEFAULT_CONFIG: Dict[str, Any] = {
    'proxy': {
        'authKey': '',
        'password': '',
        'poolSize': 5,
        'timeout': 10,
        'cacheTime': 24,
    },
    'ai': copy.deepcopy(DEFAULT_AI_CONFIG),
    'data_source': {
        'tushareToken': '',
        'refreshInterval': 60,
        'retentionDays': 365,
        'maxConcurrentRequests': 5,
        'requestTimeout': 30,
    },
    'job_schedules': {
        'execute_daily_job': []
    },
}

_DEFAULT_TEST_PROMPT: Dict[str, Any] = {
    "model": DEFAULT_AI_CONFIG['model'],
    "messages": [
        {"role": "system", "content": "You are a test assistant."},
        {"role": "user", "content": "ping"},
    ],
    "temperature": 0.0,
    "max_tokens": 1,
}


CRON_FIELD_PATTERN = re.compile(r"^([\d*/,-]+)$")


def _validate_cron_expression(expr: str) -> bool:
    parts = expr.split()
    if len(parts) != 5:
        return False
    return all(CRON_FIELD_PATTERN.match(part) for part in parts)


def _merge_job_schedules(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    merged: List[Dict[str, Any]] = []

    def normalize(entry: Dict[str, Any]) -> Dict[str, Any]:
        cron = str(entry.get('cron', '')).strip()
        description = str(entry.get('description', '')).strip()
        enabled = bool(entry.get('enabled', True))
        if cron and not _validate_cron_expression(cron):
            raise ValueError(f'无效的 cron 表达式: {cron}')
        return {'cron': cron, 'description': description, 'enabled': enabled}

    for collection in (existing, incoming):
        for item in collection or []:
            normalized = normalize(item)
            key = normalized['cron']
            if not key or key in seen:
                continue
            merged.append(normalized)
            seen.add(key)
    return merged[:MAX_SCHEDULE_ENTRIES]


def _build_cron_line(entry: Dict[str, Any]) -> str:
    cron_expr = entry['cron']
    return f"{cron_expr} {PYTHON_BIN} {JOB_SCRIPT} >> {CRON_LOG_FILE} 2>&1"


def _render_cron_file(entries: List[Dict[str, Any]]) -> str:
    lines = [
        "# 股票数据定时任务",
        "# 该文件由系统自动生成，请勿手动编辑",
        ""
    ]
    for entry in entries:
        if entry.get('enabled', True):
            lines.append(_build_cron_line(entry))
    if len(lines) == 3:
        lines.append(f"# (未配置 execute_daily_job 定时任务，默认禁用)")
    return "\n".join(lines) + "\n"


def _update_cron_file(entries: List[Dict[str, Any]]) -> None:
    try:
        os.makedirs(os.path.dirname(CRON_FILE_PATH), exist_ok=True)
        content = _render_cron_file(entries)
        with open(CRON_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as exc:
        logger.error("更新 cron 文件失败: %s", exc)
        raise


def _ensure_config_dir() -> None:
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)


def _merge_with_default(config: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(DEFAULT_CONFIG)
    for section, value in config.items():
        if isinstance(value, dict) and section in merged:
            if section == 'job_schedules':
                existing = merged['job_schedules'].get('execute_daily_job', [])
                incoming = value.get('execute_daily_job', [])
                merged['job_schedules']['execute_daily_job'] = _merge_job_schedules(existing, incoming)
            else:
                merged[section].update(value)
        else:
            merged[section] = value
    return merged


def _read_config_file() -> Dict[str, Any]:

    _ensure_config_dir()
    if not os.path.exists(CONFIG_FILE):
        _write_config_file(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        logger.warning("配置文件损坏，重新生成默认配置: %s", exc)
        _write_config_file(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)

    if not isinstance(loaded, dict):
        logger.warning("配置文件格式异常，重新生成默认配置")
        _write_config_file(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)

    return _merge_with_default(loaded)


def _write_config_file(config_data: Dict[str, Any]) -> None:
    _ensure_config_dir()
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)


def _mask_api_key(key: str) -> str:
    if not key:
        return ''
    key = key.strip()
    if len(key) <= 8:
        return '*' * len(key)
    return f"{key[:4]}...{key[-4:]}"


def _build_test_request(model: str, temperature: float, max_tokens: int) -> Dict[str, Any]:
    payload = copy.deepcopy(_DEFAULT_TEST_PROMPT)
    if model:
        payload['model'] = model
    payload['temperature'] = max(0.0, float(temperature))
    payload['max_tokens'] = max(1, min(int(max_tokens), 32))
    return payload


def _normalize_base_url(base_url: str) -> str:
    base = (base_url or '').strip()
    if not base:
        return ''
    base = base.rstrip('/')
    if base.endswith('/chat/completions'):
        return base
    return f"{base}/chat/completions"


def _prepare_ai_config(overrides: Dict[str, Any]) -> Dict[str, Any]:
    config = _read_config_file()
    ai_config = copy.deepcopy(config.get('ai', {}))
    for key in ['apiKey', 'baseUrl', 'model', 'temperature', 'maxTokens']:
        if key in overrides and overrides[key] not in (None, ''):
            ai_config[key] = overrides[key]
    return ai_config


def _perform_ai_test(ai_config: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    api_key = (ai_config.get('apiKey') or '').strip()
    base_url = _normalize_base_url(ai_config.get('baseUrl', DEFAULT_AI_CONFIG['baseUrl']))
    model = ai_config.get('model') or DEFAULT_AI_CONFIG['model']

    if not api_key:
        return False, '未配置 API Key', {}
    if not base_url:
        return False, '未配置基础 URL', {}

    try:
        temperature = float(ai_config.get('temperature', DEFAULT_AI_CONFIG['temperature']))
    except (TypeError, ValueError):
        temperature = DEFAULT_AI_CONFIG['temperature']

    try:
        max_tokens = int(ai_config.get('maxTokens', DEFAULT_AI_CONFIG['maxTokens']))
    except (TypeError, ValueError):
        max_tokens = DEFAULT_AI_CONFIG['maxTokens']

    payload = _build_test_request(model, temperature, max_tokens)
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    timeout = 10
    start_ts = time.monotonic()
    try:
        response = requests.post(base_url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        logger.warning("AI 测试请求异常: %s", exc)
        return False, f'请求失败: {exc}', {}

    elapsed_ms = int((time.monotonic() - start_ts) * 1000)

    if not 200 <= response.status_code < 300:
        snippet = response.text[:200] if response.text else '无返回体'
        return False, f'HTTP {response.status_code}: {snippet}', {'latency_ms': elapsed_ms}

    try:
        body = response.json()
    except ValueError:
        return False, '返回结果不是有效的 JSON', {'latency_ms': elapsed_ms}

    if not isinstance(body, dict) or 'choices' not in body:
        return False, '返回结果缺少 choices 字段，可能不兼容', {'latency_ms': elapsed_ms}

    return True, f'连接成功，耗时 {elapsed_ms} ms', {'latency_ms': elapsed_ms, 'model': body.get('model', model)}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


class ConfigHandler(webBase.BaseHandler, ABC):
    """配置管理处理器"""

    def get(self):
        try:
            config_type = self.get_argument('config_type', 'all')
            config_data = _read_config_file()
            if config_type == 'all':
                result = config_data
            else:
                result = config_data.get(config_type, {})
            self.write(json.dumps({'success': True, 'data': result}))
        except Exception as exc:
            logger.error("获取配置失败: %s", exc)
            self.write(json.dumps({'success': False, 'message': f'获取配置失败: {exc}'}))

    def post(self):
        try:
            data = json.loads(self.request.body)
            config_type = data.get('config_type')
            config_data = data.get('config_data', {})
            if not config_type:
                self.write(json.dumps({'success': False, 'message': '配置类型不能为空'}))
                return
            current = _read_config_file()
            merged = _merge_with_default({config_type: config_data})
            current[config_type] = merged.get(config_type, config_data)
            _write_config_file(current)
            if config_type == 'job_schedules':
                _update_cron_file(current['job_schedules'].get('execute_daily_job', []))
            self.write(json.dumps({'success': True, 'message': '配置保存成功'}))
        except Exception as exc:
            logger.error("保存配置失败: %s", exc)
            self.write(json.dumps({'success': False, 'message': f'保存配置失败: {exc}'}))

    def _read_config(self):
        return _read_config_file()

    def _save_config(self, config_data: Dict[str, Any]):
        _write_config_file(config_data)


class GetConfigHandler(webBase.BaseHandler, ABC):
    """获取配置的简化处理器"""

    def get(self):
        try:
            config_data = _read_config_file()
            self.write(json.dumps({'success': True, 'data': config_data}))
        except Exception as exc:
            logger.error("获取配置失败: %s", exc)
            self.write(json.dumps({'success': False, 'message': f'获取配置失败: {exc}'}))

    def _read_config(self):
        return _read_config_file()

    def _save_config(self, config_data: Dict[str, Any]):
        _write_config_file(config_data)


class SaveConfigHandler(webBase.BaseHandler, ABC):
    """保存配置的简化处理器"""

    def post(self):
        try:
            data = json.loads(self.request.body)
            config_type = data.get('config_type')
            config_data = data.get('config_data', {})
            if not config_type:
                self.write(json.dumps({'success': False, 'message': '配置类型不能为空'}))
                return
            current = _read_config_file()
            merged = _merge_with_default({config_type: config_data})
            current[config_type] = merged.get(config_type, config_data)
            _write_config_file(current)
            self.write(json.dumps({'success': True, 'message': '配置保存成功'}))
        except Exception as exc:
            logger.error("保存配置失败: %s", exc)
            self.write(json.dumps({'success': False, 'message': f'保存配置失败: {exc}'}))

    def _read_config(self):
        return _read_config_file()

    def _save_config(self, config_data: Dict[str, Any]):
        _write_config_file(config_data)


class AiTestHandler(webBase.BaseHandler, ABC):
    """AI 配置测试处理器"""

    def post(self):
        try:
            overrides = json.loads(self.request.body) if self.request.body else {}
            if not isinstance(overrides, dict):
                raise ValueError('请求体必须为 JSON 对象')
        except ValueError as exc:
            self.write(json.dumps({'success': False, 'message': f'无效的请求参数: {exc}'}))
            return

        ai_config = _prepare_ai_config(overrides)
        masked_key = _mask_api_key(ai_config.get('apiKey', ''))
        logger.info("开始测试 AI 配置，模型: %s，URL: %s，Key: %s", ai_config.get('model'), ai_config.get('baseUrl'), masked_key)

        success, message, details = _perform_ai_test(ai_config)
        self.write(json.dumps({'success': success, 'message': message, 'details': details}))
