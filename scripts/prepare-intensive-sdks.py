"""Download exact public SDK releases, verify integrity, extract only inert files."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path('artifacts/intensive-v04/vendor')
ROOT.mkdir(parents=True, exist_ok=True)
provenance = []
for version in ('0.3.0', '0.4.0'):
    with urllib.request.urlopen(f'https://registry.npmjs.org/fingerprint-singularity/{version}', timeout=30) as response:
        metadata = json.load(response)
    with urllib.request.urlopen(metadata['dist']['tarball'], timeout=30) as response:
        artifact = response.read()
    integrity = 'sha512-' + base64.b64encode(hashlib.sha512(artifact).digest()).decode()
    assert metadata['version'] == version and integrity == metadata['dist']['integrity']
    destination = ROOT / version
    destination.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(artifact), mode='r:gz') as archive:
        for entry in archive.getmembers():
            if not entry.isfile() or not entry.name.startswith('package/dist/'):
                continue
            relative = Path(entry.name).relative_to('package')
            assert '..' not in relative.parts and not relative.is_absolute()
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(entry).read())
    provenance.append(dict(package=metadata['name'], version=version, integrity=integrity,
                           url=metadata['dist']['tarball']))
(ROOT.parent / 'sdk-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
print(json.dumps(provenance))
