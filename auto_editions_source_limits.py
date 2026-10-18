"""Bounded streamed PSD input admission; package/pixel limits stay independent."""
import shutil
MAX_SOURCE_BYTES=2*1024*1024*1024
SCRATCH_RESERVE=5*1024*1024*1024

def check_source(size,folder):
    if type(size) is not int or not 0<size<=MAX_SOURCE_BYTES:
        raise ValueError('Source exceeds the preparation transfer limit.')
    # Allow source + staged source + package workspace, plus Photoshop headroom.
    if shutil.disk_usage(folder).free < size*3+SCRATCH_RESERVE:
        raise ValueError('Insufficient free staging/scratch storage for this PSD; source retained.')

