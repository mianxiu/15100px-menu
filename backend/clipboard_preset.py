"""Read only image dimensions from the Windows clipboard; never copy pixels."""
import ctypes
import struct
import threading
from ctypes import wintypes as W

_reader_lock=threading.Lock()
_cached_sequence=None
_cached_metadata=None


def dib_size(header):
    if len(header)<40 or struct.unpack_from('<I',header)[0]<40:return None
    width,height=struct.unpack_from('<ii',header,4)
    if not 0<width<=300000 or not 0<abs(height)<=300000:return None
    return width,abs(height)


def image_metadata():
    # Status can be requested simultaneously by the periodic publisher and
    # several dashboard clients. Never overlap OpenClipboard/GetClipboardData
    # lifetimes, or repeatedly synthesize the same delayed-rendered DIB.
    with _reader_lock:
        return _image_metadata_locked()


def _image_metadata_locked():
    global _cached_sequence,_cached_metadata
    user=ctypes.WinDLL('user32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    user.GetClipboardData.argtypes=[W.UINT];user.GetClipboardData.restype=W.HANDLE
    kernel.GlobalLock.argtypes=[W.HANDLE];kernel.GlobalLock.restype=ctypes.c_void_p
    kernel.GlobalUnlock.argtypes=[W.HANDLE]
    kernel.GlobalSize.argtypes=[W.HANDLE];kernel.GlobalSize.restype=ctypes.c_size_t
    sequence=user.GetClipboardSequenceNumber()
    if sequence and sequence==_cached_sequence:
        return dict(_cached_metadata) if _cached_metadata else None
    if not user.OpenClipboard(None):return None
    dimensions=None
    try:
        for format_id in (17,8):  # CF_DIBV5, CF_DIB
            if not user.IsClipboardFormatAvailable(format_id):continue
            handle=user.GetClipboardData(format_id)
            if not handle or kernel.GlobalSize(handle)<40:continue
            pointer=kernel.GlobalLock(handle)
            if not pointer:continue
            try:dimensions=dib_size(ctypes.string_at(pointer,40))
            finally:kernel.GlobalUnlock(handle)
            if dimensions:break
    finally:user.CloseClipboard()
    if sequence!=user.GetClipboardSequenceNumber():return None
    if not dimensions:return None
    _cached_sequence=sequence
    _cached_metadata={'sequence':sequence,'width':dimensions[0],'height':dimensions[1]}
    return dict(_cached_metadata)


def clipboard_document(metadata):
    return {'name':'Clipboard','identifier':'','group':'','width':metadata['width'],
            'height':metadata['height'],'units':'pixelsUnit','profile':'none','resolution':72,
            'resolutionUnits':'inchesUnit','depth':8,'scale':1,'mode':'RGB','fill':'white',
            'guides':[],'artboards':[]}
