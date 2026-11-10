#!/usr/bin/env python3
"""Validate the paired Fcitx5 Patch1 packages and their patched payload."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile


BASE_VERSION = '5.1.7-1build3'
PATCHED_VERSION = f'{BASE_VERSION}+patched.1'

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('payload', type=Path)
parser.add_argument('package_dir', type=Path)
args = parser.parse_args()


def field(package: Path, name: str) -> str:
    return subprocess.run(
        ['dpkg-deb', '-f', str(package), name],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


modules = args.package_dir / f'fcitx5-modules_{PATCHED_VERSION}_amd64.deb'
modules_dev = args.package_dir / f'fcitx5-modules-dev_{PATCHED_VERSION}_amd64.deb'
meta = args.package_dir / f'fcitx5_{PATCHED_VERSION}_amd64.deb'

for package in (modules, modules_dev, meta):
    if not package.is_file():
        raise SystemExit(f'missing package: {package}')
    if field(package, 'Version') != PATCHED_VERSION:
        raise SystemExit(f'wrong version: {package}')
    if field(package, 'Architecture') != 'amd64':
        raise SystemExit(f'wrong architecture: {package}')
    if field(package, 'X-Local-Variant') != 'patch1':
        raise SystemExit(f'wrong local variant: {package}')

if field(modules, 'Package') != 'fcitx5-modules':
    raise SystemExit('wrong modules package')
if field(modules_dev, 'Package') != 'fcitx5-modules-dev':
    raise SystemExit('wrong modules development package')
if field(meta, 'Package') != 'fcitx5':
    raise SystemExit('wrong meta package')

modules_depends = field(modules, 'Depends')
if 'libxcb-shape0' not in modules_depends:
    raise SystemExit('modules package is missing libxcb-shape0')

meta_depends = field(meta, 'Depends')
expected_dependency = f'fcitx5-modules (= {PATCHED_VERSION})'
if expected_dependency not in meta_depends:
    raise SystemExit(f'meta package is missing {expected_dependency}')
if f'fcitx5-modules (= {BASE_VERSION})' in meta_depends:
    raise SystemExit('meta package still depends on the stock modules package')

modules_dev_depends = field(modules_dev, 'Depends')
if expected_dependency not in modules_dev_depends:
    raise SystemExit(f'modules development package is missing {expected_dependency}')
if f'fcitx5-modules (= {BASE_VERSION})' in modules_dev_depends:
    raise SystemExit('modules development package still depends on the stock modules package')

with tempfile.TemporaryDirectory(prefix='fcitx5-patch1-verify-') as directory:
    root = Path(directory)
    subprocess.run(['dpkg-deb', '-x', str(modules), str(root)], check=True)
    installed_payload = root / 'usr/lib/x86_64-linux-gnu/fcitx5/libclassicui.so'
    if digest(installed_payload) != digest(args.payload):
        raise SystemExit('installed libclassicui.so does not match the built payload')

print(f'verified {modules.name}, {modules_dev.name}, and {meta.name}')
