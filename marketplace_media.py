"""Bounded recorded-item videos in the existing private assets bucket.

Only the approved listing route serves these objects. No public bucket URLs or
presigned links are issued, including for pending moderation previews.
"""
import base64
from contextlib import contextmanager
from pathlib import Path
import re
import subprocess
import tempfile
import threading
from uuid import uuid4

from marketplace import identifier

MAX_INPUT = 15_000_000
MAX_OUTPUT = 12_000_000
MAX_SECONDS = 60
_ENCODERS = threading.BoundedSemaphore(1)


def configured():
    from services.r2_storage import safe_r2_enabled, get_bucket_name
    return bool(safe_r2_enabled() and get_bucket_name('assets'))


@contextmanager
def encoder_slot():
    if not _ENCODERS.acquire(blocking=False):
        raise ValueError('Another video is being prepared. Please try again shortly.')
    try:
        yield
    finally:
        _ENCODERS.release()


def _run(binary, args, timeout):
    try:
        return subprocess.run([binary, '-hide_banner', '-nostdin', *args],
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, timeout=timeout, check=False,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (subprocess.TimeoutExpired, OSError):
        raise ValueError('This video could not be prepared. Try a shorter MP4, MOV or WebM clip.') from None


def _probe(binary, path, container):
    result = _run(binary, ['-max_alloc', '134217728', '-protocol_whitelist', 'file',
                          '-f', container, '-i', str(path)], 12)
    details = result.stderr.decode('utf-8', errors='replace')
    duration = re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', details)
    dimensions = re.search(r'Video: [^\r\n]*?\b(\d{2,5})x(\d{2,5})\b', details)
    if not duration or not dimensions:
        raise ValueError('Choose a valid MP4, MOV or WebM video of your item.')
    hours, minutes, seconds = map(float, duration.groups())
    seconds += hours * 3600 + minutes * 60
    width, height = map(int, dimensions.groups())
    if not 0 < seconds <= MAX_SECONDS + .05 or min(width, height) < 100 or width * height > 8_400_000:
        raise ValueError('Use an item video up to 60 seconds and no larger than 4K.')
    return seconds


def prepare_video(value):
    """Transcode actual uploaded bytes, remove metadata and optimise for playback."""
    if value in (None, ''):
        return None
    if not isinstance(value, str) or len(value) > ((MAX_INPUT + 2) // 3) * 4:
        raise ValueError('Use one video up to 15 MB and 60 seconds.')
    try:
        raw = base64.b64decode(value, validate=True)
    except ValueError:
        raise ValueError('Choose a valid MP4, MOV or WebM video.') from None
    if not raw or len(raw) > MAX_INPUT:
        raise ValueError('Use one video up to 15 MB and 60 seconds.')
    container = 'mov' if len(raw) > 12 and raw[4:8] == b'ftyp' else 'matroska' if raw.startswith(b'\x1aE\xdf\xa3') else None
    if not container:
        raise ValueError('Choose an MP4, MOV or WebM video.')
    import imageio_ffmpeg
    binary = imageio_ffmpeg.get_ffmpeg_exe()
    with encoder_slot(), tempfile.TemporaryDirectory(prefix='sc-item-video-') as folder:
        source, output = Path(folder) / 'upload.bin', Path(folder) / 'item.mp4'
        source.write_bytes(raw)
        _probe(binary, source, container)
        result = _run(binary, ['-y', '-v', 'error', '-xerror', '-max_alloc', '134217728',
            '-threads', '2', '-protocol_whitelist', 'file', '-f', container, '-i', str(source),
            '-map', '0:v:0', '-map', '0:a:0?', '-sn', '-dn', '-map_metadata', '-1', '-map_chapters', '-1',
            '-t', '60.05', '-vf', "scale=960:960:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '25', '-maxrate', '1300k', '-bufsize', '2600k',
            '-threads', '2', '-pix_fmt', 'yuv420p', '-r', '30', '-c:a', 'aac', '-b:a', '96k',
            '-movflags', '+faststart', str(output)], 75)
        if result.returncode or not output.exists() or not 0 < output.stat().st_size <= MAX_OUTPUT:
            raise ValueError('This video could not be prepared. Try a shorter MP4 clip.')
        duration = _probe(binary, output, 'mov')
        return {'bytes': output.read_bytes(), 'seconds': round(duration, 2)}


class VideoStorage:
    def __init__(self, client=None, bucket=None):
        from services.r2_storage import get_r2_client, get_bucket_name
        self.bucket = bucket or get_bucket_name('assets')
        if not self.bucket:
            raise RuntimeError('Item video storage is not configured.')
        self.client = client or get_r2_client()

    @staticmethod
    def key(listing_id, token):
        return f'marketplace/media/{identifier(listing_id)}/{identifier(token)}.mp4'

    def save(self, listing_id, prepared):
        token = str(uuid4())
        key = self.key(listing_id, token)
        data = prepared['bytes']
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data,
                               ContentType='video/mp4', CacheControl='no-store')
        return {'token': token, 'size': len(data), 'seconds': prepared['seconds']}

    def discard(self, listing_id, metadata):
        self.client.delete_object(Bucket=self.bucket, Key=self.key(listing_id, metadata['token']))

    def open(self, listing_id, metadata, start=0, end=None):
        end = metadata['size'] - 1 if end is None else end
        return self.client.get_object(Bucket=self.bucket, Key=self.key(listing_id, metadata['token']),
                                      Range=f'bytes={start}-{end}')['Body']

    def preview(self, listing_id, metadata):
        stream = self.open(listing_id, metadata)
        try:
            data = stream.read(MAX_OUTPUT + 1)
            if len(data) > MAX_OUTPUT:
                raise ValueError('Item video exceeds the preview limit.')
            return data
        finally:
            stream.close()


def byte_range(value, size):
    """Single RFC byte ranges, including suffixes; reject unsatisfiable requests."""
    if not value:
        return 0, size - 1, False
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
    if not match or not any(match.groups()):
        raise ValueError('Invalid byte range.')
    first, last = match.groups()
    if not first:
        if int(last) <= 0:
            raise ValueError('Invalid byte range.')
        start, end = max(0, size - int(last)), size - 1
    else:
        start, end = int(first), min(int(last), size - 1) if last else size - 1
    if not 0 <= start <= end < size:
        raise ValueError('Invalid byte range.')
    return start, end, True
