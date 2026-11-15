"""Existing companion atomic JSON pattern, without importing a worker runtime."""
import json
import os
import secrets


def atomic_json(path,data):
    temporary=path.with_name('.sc-'+secrets.token_hex(8)+'.tmp')
    try:
        with temporary.open('x',encoding='utf-8') as output:
            json.dump(data,output);output.flush();os.fsync(output.fileno())
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)
