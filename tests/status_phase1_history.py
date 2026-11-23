"""Verify an exact historical source when tests run without a Git checkout."""
import hashlib
import os
from pathlib import Path
import subprocess


def artwork_baseline(root):
    supplied = os.environ.get('STATUS_TEST_ARTWORK_BASELINE')
    value = Path(supplied).read_bytes() if supplied else subprocess.check_output(
        ['git', 'show', '58569c66:product_upload_artwork.py'], cwd=root)
    if hashlib.sha256(value).hexdigest() != '464680d788e3eb78b9675e21b4c16a67fea01acc630a5318df4d9da5d0d66b01':
        raise ValueError('Historical artwork baseline digest mismatch')
    return value
