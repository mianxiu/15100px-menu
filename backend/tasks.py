"""Bounded task history with optional durable snapshots; never a replay queue."""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import asyncio
import json
import logging
import os
from pathlib import Path
import time
import uuid

STATES = {
    'queued':'排队中', 'waiting-photoshop':'等待 Photoshop', 'capturing':'读取目标',
    'running':'执行中', 'cancel-requested':'取消等待中', 'succeeded':'已完成',
    'failed':'失败', 'cancelled':'已取消', 'result-unknown':'结果未知',
}
TRANSITIONS = {
    'queued':{'capturing','cancelled','failed'},
    'capturing':{'running','cancel-requested','failed','cancelled'},
    'running':{'result-unknown','succeeded','failed','cancelled'},
    'cancel-requested':{'cancelled','failed'},
    'result-unknown':{'succeeded','failed'},
}


class TaskCancelled(RuntimeError):
    """Cancellation before any modifying script is dispatched."""


class TaskStore:
    def __init__(self, limit=64, path=None):
        self.limit = limit
        self.records = OrderedDict()
        self.on_change = None
        self.path = Path(path) if path else None
        self.persistence_error = ''
        self.writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix='task-history') if self.path else None
        self.pending = None
        if self.path:
            self._restore()

    def _restore(self):
        if not self.path.exists():return
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('protocol_version') != 1:raise ValueError('不支持的任务记录版本')
            records = OrderedDict()
            for item in reversed(data['items'][:self.limit]):
                item = deepcopy(item)
                if not isinstance(item.get('id'), str) or item.get('state') not in STATES:
                    raise ValueError('无效任务记录')
                item.pop('state_label', None)
                item['restored'] = True
                # An old COM instance cannot be queried reliably after restart.
                # Never infer success or resubmit a modifying command.
                if item['state'] in TRANSITIONS or item['state'] in ('queued','waiting-photoshop'):
                    item.setdefault('previous_state', item['state'])
                    item['state'] = 'result-unknown'
                    item['error'] = '服务已重启，无法确认上次任务结果；请检查 Photoshop，勿重复执行'
                item['_started'] = None
                records[item['id']] = item
            self.records = records
            self._persist()
        except Exception as exc:
            self.persistence_error = '任务记录读取失败：' + str(exc)
            logging.exception('Task history restore failed')

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + '.tmp')
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def _persist(self):
        if self.path and not self.persistence_error:
            self.pending = self.writer.submit(self._write, self.snapshot())

    async def flush(self):
        if self.persistence_error:raise RuntimeError(self.persistence_error)
        if self.pending:
            try:await asyncio.shield(asyncio.wrap_future(self.pending))
            except Exception as exc:
                self.persistence_error = '任务记录保存失败：' + str(exc)
                raise RuntimeError(self.persistence_error) from exc

    async def close(self):
        try:await self.flush()
        finally:
            if self.writer:self.writer.shutdown(wait=False)

    def create(self, action, label, state='capturing', **details):
        task_id = uuid.uuid4().hex
        self.records[task_id] = {
            'id':task_id, 'action':action, 'label':label, 'channel':getattr(self,'channel','com-jsx'),
            'state':state, 'created_at':datetime.now(timezone.utc).isoformat(),
            '_started':time.monotonic(), 'elapsed_ms':0,
            **deepcopy(details),
        }
        self.records[task_id]['timeline'] = [{'state':state, 'started_at':self.records[task_id]['created_at'],
                                               'start_elapsed_ms':0, 'duration_ms':0}]
        while len(self.records)>self.limit:self.records.popitem(last=False)
        self._changed(task_id)
        return task_id

    def update(self, task_id, state, **details):
        record = self.records[task_id]
        if record.get('restored'):raise ValueError('历史任务只读，不能重新执行或更改结果')
        old = record['state']
        if state != old and state not in TRANSITIONS.get(old, set()):
            raise ValueError(f'Invalid task transition: {old} -> {state}')
        elapsed = round((time.monotonic()-record['_started'])*1000)
        if state != old:
            timeline = record['timeline']
            timeline[-1]['duration_ms'] = max(0, elapsed-timeline[-1]['start_elapsed_ms'])
            timeline.append({'state':state, 'started_at':datetime.now(timezone.utc).isoformat(),
                             'start_elapsed_ms':elapsed, 'duration_ms':0})
        record.update(deepcopy(details))
        record['state'] = state
        record['elapsed_ms'] = elapsed
        self._changed(task_id)

    def _changed(self, task_id):
        record = self.records[task_id]
        record['updated_at'] = datetime.now(timezone.utc).isoformat()
        logging.info('Task state: id=%s action=%s state=%s elapsed_ms=%s',
                     task_id, record['action'], record['state'], record['elapsed_ms'])
        self._persist()
        if self.on_change:
            try:self.on_change(self.get(task_id))
            except Exception:logging.exception('Task status notification failed')

    def get(self, task_id):
        if not isinstance(task_id,str) or task_id not in self.records:
            raise ValueError('未找到当前服务会话中的任务')
        record=deepcopy(self.records[task_id])
        started=record.pop('_started')
        if started is not None and record['state'] in TRANSITIONS:
            record['elapsed_ms']=round((time.monotonic()-started)*1000)
        record['state_label']=STATES[record['state']]
        for index, phase in enumerate(record.get('timeline', [])):
            phase['state_label'] = STATES[phase['state']]
            phase['active'] = started is not None and record['state'] in TRANSITIONS and index == len(record['timeline'])-1
            if phase['active']:
                phase['duration_ms'] = max(0, record['elapsed_ms']-phase['start_elapsed_ms'])
        return record

    def snapshot(self):
        return {'protocol_version':1, 'persistent':bool(self.path), 'persistence_error':self.persistence_error, 'limit':self.limit,
                'states':dict(STATES), 'items':[self.get(task_id) for task_id in reversed(self.records)]}
