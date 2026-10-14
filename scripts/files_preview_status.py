"""Read-only configuration report. Never prints values or contacts a provider.

Run in the intended service environment. Presence is not proof of bucket privacy,
permissions, conditional-write support or successful end-to-end preparation.
"""
import json
import os


def status():
    names = ('FILES_PREVIEW_PRIVATE_BUCKET_CONFIRMED', 'FILES_PREVIEW_BUCKET',
             'FILES_PREVIEW_NAMESPACE', 'FILES_PREVIEW_ENCRYPTION_KEY',
             'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_ENDPOINT', 'R2_ACCOUNT_ID')
    present = {name: bool(os.getenv(name)) for name in names}
    valid_key = False
    if present['FILES_PREVIEW_ENCRYPTION_KEY']:
        try:
            from cryptography.fernet import Fernet
            Fernet(os.environ['FILES_PREVIEW_ENCRYPTION_KEY'].encode())
            valid_key = True
        except Exception:
            pass  # No exception detail: it could contain configuration values.
    gate = (os.getenv('FILES_PREVIEW_PRIVATE_BUCKET_CONFIRMED') == '1'
            and all(present[name] for name in names[1:4]))
    return {'settings_present': present, 'feature_gate_enabled': gate,
            'encryption_key_valid': valid_key,
            'r2_connection_settings_present': all(present[name] for name in names[4:6])
                and (present['R2_ENDPOINT'] or present['R2_ACCOUNT_ID']),
            'provider_validation': 'NOT PERFORMED; configuration alone does not establish safe activation'}


if __name__ == '__main__':
    print(json.dumps(status(), indent=2))
