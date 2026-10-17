"""One request-bound preview mailbox; replace values, never queue mutations."""
import json
import threading
import time
import asyncio
import logging
from pathlib import Path

from .shape_paint import parameters


class MaskPreview:
    def __init__(self, epoch, paint):
        self.epoch = epoch
        self.paint = parameters(paint)
        self.has_mask = 'mask' in self.paint
        self.revision = self.paint['revision']
        self.phase = 'preview'
        self.seq = 1
        self.binding = None
        self.lock = threading.Lock()
        self.publish_lock = threading.Lock()
        self.published = None
        self.published_at = 0
        self.closed = False

    def update(self, paint, commit=False):
        value = parameters(paint)
        if value['revision'] != self.revision or ('mask' in value) != self.has_mask:
            raise ValueError('预览草稿身份已改变')
        with self.lock:
            if self.closed or self.phase != 'preview':
                return False
            self.paint = value
            self.seq += 1
            if commit:
                self.phase = 'commit'
            return True

    def cancel(self):
        with self.lock:
            if not self.closed and self.phase == 'preview':
                self.phase = 'cancel'
                self.seq += 1

    def bind(self, folder, request):
        with self.lock:
            self.binding = (Path(folder), {key: request[key] for key in ('id', 'session', 'token')})
        self.publish()

    def publish(self):
        # Called by the dedicated publisher, never by the hook/window thread.
        # Serialize publishers, copying state under a separate short lock so
        # a filesystem delay never blocks UI updates or cancellation.
        from .uxp_bridge import publish_request
        with self.publish_lock:
            with self.lock:
                if not self.binding or self.closed:return
                folder, identity = self.binding
                key=(identity['id'],self.seq)
                if key==self.published and time.monotonic()-self.published_at<.5:return
                value = {**identity, 'seq': self.seq, 'phase': self.phase,
                         'lease_until_ms': int(time.time()*1000)+4000, 'paint': self.paint}
            data = json.dumps(value, separators=(',', ':'))
            if len(data.encode('utf-8')) > 4096:
                raise ValueError('预览草稿超出协议长度')
            temporary = folder/(identity['id']+'.preview.tmp')
            temporary.write_text(data, 'utf-8')
            publish_request(temporary, folder/('mask-preview-'+identity['id']+'.json'))
            self.published=key;self.published_at=time.monotonic()

    def close(self):
        with self.lock:
            self.closed = True


async def dispatch_preview(app, action, args):
    from .uxp_bridge import UxpBridge
    if not isinstance(app.bridge,UxpBridge) or not app.desktop:
        raise RuntimeError('实时预览需要桌面菜单和 UXP 0.3.26')
    epoch=args.get('menu_epoch')
    if type(epoch) is not int or epoch!=app.desktop.menu_epoch:
        raise ValueError('预览菜单已过期')
    current=getattr(app,'_mask_preview',None)
    if current:
        if current.epoch!=epoch:raise RuntimeError('上一项预览尚未结束')
        if action=='mask.preview.commit':
            current.update(args.get('params'),commit=True)
            await asyncio.to_thread(app.desktop.hide)
        else:current.update(args.get('params'))
        return {'message':'已更新当前预览'}
    if action!='mask.preview.update':raise RuntimeError('预览已结束，未重复提交')
    app.require_uxp_enabled()
    if (app.operation_lock.locked() or app.bridge.busy or getattr(app,'_mask_preview',None)
            or app.photoshop_launcher.active or not app.desktop.visible
            or epoch!=app.desktop.menu_epoch or not getattr(app.desktop,'color_editor_active',False)):
        raise RuntimeError('当前不能开始预览，请等待完成后重新打开菜单')
    preview=MaskPreview(epoch,args.get('params'))
    snapshot=app.desktop.menu_layer_context
    target={key:snapshot.get(key) for key in ('session','document_id','layer_ids')}
    if len(target.get('layer_ids') or [])!=1:raise ValueError('预览需要冻结的单选形状')
    target['active_layer_id']=target['layer_ids'][0]
    # Reserve synchronously before starting the worker. Subsequent slider
    # events replace this same session while focus/target checks are pending.
    await app.operation_lock.acquire()
    app._mask_preview=app.desktop.mask_preview=preview
    task=asyncio.create_task(run_preview(app,preview,target))
    app._mask_preview_task=task
    return {'message':'正在预览羽化／密度'}


async def run_preview(app, preview, target):
    stopped=asyncio.Event()
    async def pump():
        while not stopped.is_set():
            try:
                if preview.phase=='preview' and (not app.desktop.visible or app.desktop.menu_epoch!=preview.epoch
                        or not await asyncio.to_thread(app.desktop._scope)):
                    preview.cancel()
                await asyncio.to_thread(preview.publish)
            except Exception:
                # Stop renewing the lease if publication fails. Photoshop owns
                # rollback; a missing final receipt continues to block writes.
                preview.cancel()
                logging.exception('Mask preview publication failed')
                return
            try:await asyncio.wait_for(stopped.wait(),.08)
            except asyncio.TimeoutError:pass
    publisher=asyncio.create_task(pump())
    try:
        await app.broadcast({'type':'operation','busy':True,'action':'shape.paint'})
        await asyncio.to_thread(app.desktop.require_action_focus)
        async def before_dispatch(captured):
            if (app.desktop.menu_epoch!=preview.epoch or preview.phase=='cancel'
                    or not app.desktop.visible and preview.phase!='commit'):
                raise RuntimeError('菜单已关闭，未开始预览')
            await asyncio.to_thread(app.desktop.require_menu_layer_target,'shape.paint',captured)
        result=await app.bridge.execute_shape(preview.paint,before_dispatch=before_dispatch,
                                             frozen_target=target,preview=preview)
        app.desktop.layer_context=dict(app.bridge.layer_context)
        if app.desktop.menu_epoch==preview.epoch and app.desktop.visible:
            await asyncio.to_thread(app.desktop.hide)
        await app.broadcast({'type':'notice','scope':'operation','action':'shape.paint','ok':True,'message':result['message']})
    except Exception as error:
        preview.cancel()
        if app.desktop.menu_epoch==preview.epoch and app.desktop.visible:
            await asyncio.to_thread(app.desktop.hide,restore=False)
        await app.broadcast({'type':'notice','scope':'operation','action':'shape.paint','ok':False,'message':str(error)})
        logging.exception('Mask preview ended with error')
    finally:
        stopped.set();await publisher;preview.close()
        app.operation_lock.release()
        app._mask_preview=app.desktop.mask_preview=None
        app.desktop.event({'type':'mask.preview','active':False})
        await app.broadcast({'type':'operation','busy':app.bridge.busy})
