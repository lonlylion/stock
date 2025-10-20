#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
简单的 JSON 进度记录工具，用于跨线程报送分页抓取进度。
"""

import json
import os
import threading
import time
from contextlib import contextmanager
from typing import Optional

from instock.lib.simple_logger import get_logger

logger = get_logger(__name__)

_DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'log', 'progress.json')
_LOCK = threading.RLock()


def _ensure_parent(path: str) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def _read_all(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"读取进度文件失败 {path}: {exc}")
        return {}


def _write_all(path: str, data: dict) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)




def update(task_id: str,
           *,
           current: int,
           total: Optional[int],
           message: str,
           path: str = _DEFAULT_PATH,
           success: Optional[bool] = None) -> None:
    """更新指定任务的进度。"""
    with _LOCK:
        _ensure_parent(path)
        data = _read_all(path)
        task = data.setdefault(task_id, {})
        task['current'] = current
        task['total'] = total
        task['message'] = message
        task['timestamp'] = time.time()
        if total and total > 0:
            task['progress'] = round(current / total * 100, 2)
        else:
            task['progress'] = None
        if success is not None:
            task['success'] = success
        data[task_id] = task
        _write_all(path, data)


def clear(task_id: str, *, path: str = _DEFAULT_PATH) -> None:
    with _LOCK:
        if not os.path.exists(path):
            return
        data = _read_all(path)
        if task_id in data:
            data.pop(task_id, None)
            _write_all(path, data)


def get(task_id: str, *, path: str = _DEFAULT_PATH) -> Optional[dict]:
    with _LOCK:
        if not os.path.exists(path):
            return None
        data = _read_all(path)
        return data.get(task_id)


def get_many(task_ids, *, path: str = _DEFAULT_PATH):
    with _LOCK:
        data = _read_all(path)
        return {task_id: data.get(task_id) for task_id in task_ids if data.get(task_id)}
