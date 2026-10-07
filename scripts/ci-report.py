"""Publish bounded, redacted failure diagnostics as a public CI annotation."""
import os
from pathlib import Path
import subprocess
import sys

result = subprocess.run([sys.executable, 'scripts/verify-platform.py'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
output = result.stdout
for name in ('.env', '.admin-password'):
    path = Path(name)
    if path.exists():
        for line in path.read_text().splitlines():
            value = line.split('=', 1)[-1]
            if len(value) >= 16:
                output = output.replace(value, '[redacted]')
path = Path('artifacts/platform'); path.mkdir(parents=True, exist_ok=True)
(path / 'acceptance.log').write_text(output)
print(output)
if result.returncode:
    tail = '\n'.join(output.splitlines()[-50:])[-7000:]
    tail = tail.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print('::error title=Platform acceptance diagnostics::' + tail)
sys.exit(result.returncode)
