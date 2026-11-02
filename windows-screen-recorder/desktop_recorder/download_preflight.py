"""Read-only Windows registration diagnostics. Does not launch Edge or the host."""
import json
from pathlib import Path

HOST = 'com.sportscave.recorder.downloads'


def inspect_manifest(path, extension_id):
    path = Path(path)
    try:
        manifest = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        return {'ready': False, 'reason': 'Manifest is missing or invalid UTF-8 JSON.',
                'error_type': type(error).__name__}
    if not isinstance(manifest, dict) or manifest.get('name') != HOST or manifest.get('type') != 'stdio':
        return {'ready': False, 'reason': 'Manifest host name or transport does not match.'}
    origins = manifest.get('allowed_origins')
    if not isinstance(origins, list) or not all(isinstance(origin, str) for origin in origins):
        return {'ready': False, 'reason': 'Manifest allowed_origins must be an array of extension origins.'}
    if 'chrome-extension://' + extension_id + '/' not in origins:
        return {'ready': False, 'reason': 'Manifest does not allow the selected recorder extension.'}
    value = manifest.get('path')
    if not isinstance(value, str) or not value:
        return {'ready': False, 'reason': 'Manifest executable path is missing.'}
    executable = Path(value)
    if not executable.is_absolute():
        executable = path.parent / executable
    if not executable.is_file():
        return {'ready': False, 'reason': 'Manifest executable does not exist.'}
    return {'ready': True, 'reason': 'Static manifest checks passed; Edge launch remains unverified.',
            'executable': str(executable.resolve())}


def inspect_registration(extension_id):
    import re
    import winreg
    if not re.fullmatch('[a-p]{32}', extension_id):
        raise ValueError('Provide the exact recorder extension ID from Edge.')
    checks = []
    selected = None
    # Microsoft Edge lookup precedence: HKCU then HKLM, 32-bit then 64-bit.
    for hive_name, hive in [('HKCU', winreg.HKEY_CURRENT_USER), ('HKLM', winreg.HKEY_LOCAL_MACHINE)]:
        for view_name, view in [('32', winreg.KEY_WOW64_32KEY), ('64', winreg.KEY_WOW64_64KEY)]:
            item = {'hive': hive_name, 'view': view_name}
            try:
                with winreg.OpenKey(hive, 'Software\\Microsoft\\Edge\\NativeMessagingHosts\\' + HOST,
                                    0, winreg.KEY_READ | view) as key:
                    value, kind = winreg.QueryValueEx(key, '')
                item.update(path=value, registry_type=kind)
                item['manifest'] = (inspect_manifest(value, extension_id)
                                    if kind == winreg.REG_SZ and isinstance(value, str) and Path(value).is_absolute()
                                    else {'ready': False, 'reason': 'Registry default must be REG_SZ with an absolute manifest path.'})
                if selected is None:
                    selected = item
            except OSError as error:
                item.update(error_type=type(error).__name__, windows_error=error.winerror)
            checks.append(item)
    return {'host': HOST, 'checks': checks, 'selected': selected,
            'browser_connection_verified': False,
            'guidance': 'https://learn.microsoft.com/en-us/microsoft-edge/extensions-chromium/developer-guide/native-messaging'}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('extension_id')
    args = parser.parse_args()
    print(json.dumps(inspect_registration(args.extension_id), indent=2))
