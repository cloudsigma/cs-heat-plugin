"""Packaging-only guard: bind installed contract origins to wheel and checkout."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

root, dist, receipt = map(Path, sys.argv[1:])
wheels = list(dist.glob('*.whl'))
assert len(wheels) == 1, wheels
with zipfile.ZipFile(wheels[0]) as wheel:
    members = set(wheel.namelist())
    expected = {str(p.relative_to(root)) for p in (root / 'cloudsigma_heat').rglob('*.py')}
    assert {n for n in members if n.endswith('.py')} == expected
    assert not any(n.startswith(('tests/', 'ci/', '.github/')) for n in members)
    assert not any(n.endswith(('entry_points.txt', '.sqlite', '.db')) for n in members)
    assert any(n.endswith('/licenses/LICENSE') for n in members)
    for name in expected:
        assert wheel.read(name) == (root / name).read_bytes(), name
    for name, item in json.loads(receipt.read_text()).items():
        member = 'cloudsigma_heat/experimental_offline/' + name + '.py'
        installed = Path(item['path']).resolve()
        assert 'site-packages' in installed.parts and not installed.is_relative_to(root.resolve())
        digest = hashlib.sha256(wheel.read(member)).hexdigest()
        assert item['sha256'] == digest == hashlib.sha256(installed.read_bytes()).hexdigest()
print('PASS: wheel contents, source bytes, installed contract origins, retained LICENSE')
