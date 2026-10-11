"""Continuously preserve existing service diagnostics without installing hooks.

Run with pythonw for a hidden collector. Create OUTPUT/stop to exit normally.
Retention is size based: 32 files of up to 16 MiB, not a guaranteed day count.
"""
import argparse
import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import time


def collect(source, logger, positions):
    # Open and close each time so the running service can rename its log files.
    # File identity follows rotation, preventing repeated copies of old content.
    for path in sorted(source.glob('service.log*'), key=lambda p: p.name, reverse=True):
        try:
            with path.open('rb') as stream:
                stat = os.fstat(stream.fileno())
                identity = (stat.st_dev, stat.st_ino)
                offset = positions.get(identity, 0)
                if stat.st_size < offset:
                    offset = 0
                stream.seek(offset)
                data = stream.read()
                # Leave a partial final line for the next poll.
                complete = data.rfind(b'\n') + 1
                for line in data[:complete].splitlines():
                    logger.info(json.dumps({'type': 'service.line', 'source': path.name,
                                            'line': line.decode('utf-8', errors='replace')},
                                           ensure_ascii=False))
                positions[identity] = offset + complete
        except FileNotFoundError:
            continue  # The service may rotate between enumeration and opening.
    # A bounded map is sufficient for the four source log files.
    if len(positions) > 64:
        for identity in list(positions)[:-32]:
            del positions[identity]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path,
                        default=Path(os.environ.get('LOCALAPPDATA', '.')) / 'PhotoshopMenu')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--once', action='store_true', help='Archive currently retained logs and exit')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    mutex = None
    if os.name == 'nt' and not args.once:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        mutex = kernel.CreateMutexW(None, False, 'Local\\PhotoshopMenuHotkeyArchive')
        error = ctypes.get_last_error()
        if not mutex:
            raise ctypes.WinError(error)
        if error == 183:
            kernel.CloseHandle(mutex)
            return
    logger = logging.getLogger('hotkey.archive')
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(args.output / 'history.jsonl', maxBytes=16*1024*1024,
                                  backupCount=31, encoding='utf-8')
    logger.addHandler(handler)
    logger.info(json.dumps({'type': 'collector.start', 'pid': os.getpid(),
                            'source': str(args.source.resolve()), 'time': time.time()}))
    positions = {}
    heartbeat = 0
    try:
        while not (args.output / 'stop').exists():
            try:
                collect(args.source, logger, positions)
            except OSError:
                logger.exception('Archive read failed; retrying next poll')
            now = time.monotonic()
            if now >= heartbeat:
                logger.info(json.dumps({'type': 'collector.heartbeat', 'pid': os.getpid(),
                                       'time': time.time()}))
                heartbeat = now + 60
            if args.once:
                break
            time.sleep(.5)
    finally:
        logger.info(json.dumps({'type': 'collector.stop', 'time': time.time()}))
        handler.close()
        if mutex:
            kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
