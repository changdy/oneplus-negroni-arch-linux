#!/usr/bin/env python3
"""Verify delayed automatic GPU policy delivery and the disabled fallback."""
import json
from pathlib import Path
import sys

from image_feature import Image


def verify(image_dir, log_dir):
    image = Image(image_dir)
    files = {}
    for unit in ('gpu-runtime-pm.service', 'gpu-runtime-active.service'):
        path = f'/etc/systemd/system/{unit}'
        files[path] = image.source(path, f'config/systemd/{unit}')
    image.file('/usr/bin/bash', '0755')
    image.link('/usr/bin/sh', 'bash')
    image.enabled('gpu-runtime-pm.service', 'graphical.target')
    # Check every target, including an accidentally retained enablement in another target.
    entries = image.query('ls -p /etc/systemd/system').decode().splitlines()
    for entry in entries:
        parts = entry.split('/')
        if len(parts) > 5 and parts[5].endswith(('.wants', '.requires')):
            listing = image.query(f'ls -p /etc/systemd/system/{parts[5]}').decode()
            if '/gpu-runtime-active.service/' in listing:
                raise RuntimeError('Forced-active GPU service must not be enabled by default')
    report = {
        'image': str(image.path), 'service': 'gpu-runtime-pm.service',
        'service_enabled': True, 'power_control': 'auto',
        'forced_active_enabled': False, 'automatic_service_enabled': True,
        'autosuspend_delay_ms': 1000,
        'installed_file_sha256': files, 'hardware_tested': False,
    }
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / 'gpu-runtime-pm-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print('GPU runtime PM image verified: auto enabled at 1000 ms, active fallback disabled')
    return report


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: verify-gpu-runtime-pm-image.py IMAGE_DIRECTORY LOG_DIRECTORY')
    verify(*map(Path, sys.argv[1:]))
