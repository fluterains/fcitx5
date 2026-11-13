#!/usr/bin/env python3
"""Repackage matching Ubuntu 24.04 packages with a Docker-built payload."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


BASE_VERSION = '5.1.7-1build3'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--patch-version', type=int, choices=range(1, 100), default=1)
parser.add_argument('base_modules', type=Path)
parser.add_argument('base_modules_dev', type=Path)
parser.add_argument('base_meta', type=Path)
parser.add_argument('payload', type=Path)
parser.add_argument('output_dir', type=Path)
args = parser.parse_args()
PATCHED_VERSION = f'{BASE_VERSION}+patched.{args.patch_version}'
VARIANT = f'patch{args.patch_version}'


def extract_package(base: Path, root: Path, package: str) -> str:
    subprocess.run(['dpkg-deb', '-R', str(base), str(root)], check=True)
    control = root / 'DEBIAN/control'
    text = control.read_text()
    if not re.search(rf'^Version: {re.escape(BASE_VERSION)}$', text, re.M):
        raise ValueError(f'Expected Ubuntu base version {BASE_VERSION}')
    if 'Architecture: amd64\n' not in text:
        raise ValueError('Expected amd64 package')
    if not re.search(rf'^Package: {re.escape(package)}$', text, re.M):
        raise ValueError(f'Unexpected base package for {package}')
    return text


def finish_package(root: Path, text: str, output: Path) -> None:
    text = re.sub(rf'^Version: .+$', f'Version: {PATCHED_VERSION}', text, flags=re.M)
    text = re.sub(r'^X-Local-Variant:.*\n?', '', text, flags=re.M)
    text += f'X-Local-Variant: {VARIANT}\n'
    files = sorted(
        path
        for path in root.rglob('*')
        if path.is_file() and not path.is_symlink()
        and 'DEBIAN' not in path.relative_to(root).parts
    )
    (root / 'DEBIAN/md5sums').write_text(''.join(
        f'{hashlib.md5(path.read_bytes()).hexdigest()}  {path.relative_to(root)}\n'
        for path in files
    ))
    installed_size = (sum(path.stat().st_size for path in files) + 1023) // 1024
    text = re.sub(
        r'^Installed-Size: .+$',
        f'Installed-Size: {installed_size}',
        text,
        flags=re.M,
    )
    (root / 'DEBIAN/control').write_text(text)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ['dpkg-deb', '--root-owner-group', '-b', str(root), str(output)],
        check=True,
    )


with tempfile.TemporaryDirectory(prefix='fcitx5-patch1-') as directory:
    work = Path(directory)

    modules_root = work / 'modules'
    modules_control = extract_package(
        args.base_modules,
        modules_root,
        'fcitx5-modules',
    )
    modules_control = re.sub(
        r'^Depends: (.+)$',
        lambda match: match.group(0) + ', libxcb-shape0',
        modules_control,
        flags=re.M,
    )
    shutil.copy2(
        args.payload,
        modules_root / 'usr/lib/x86_64-linux-gnu/fcitx5/libclassicui.so',
    )
    modules_output = args.output_dir / f'fcitx5-modules_{PATCHED_VERSION}_amd64.deb'
    finish_package(modules_root, modules_control, modules_output)

    modules_dev_root = work / 'modules-dev'
    modules_dev_control = extract_package(
        args.base_modules_dev,
        modules_dev_root,
        'fcitx5-modules-dev',
    )
    stock_dependency = f'fcitx5-modules (= {BASE_VERSION})'
    patched_dependency = f'fcitx5-modules (= {PATCHED_VERSION})'
    if stock_dependency not in modules_dev_control:
        raise ValueError(f'Missing expected dependency: {stock_dependency}')
    modules_dev_control = modules_dev_control.replace(
        stock_dependency,
        patched_dependency,
    )
    modules_dev_output = (
        args.output_dir / f'fcitx5-modules-dev_{PATCHED_VERSION}_amd64.deb'
    )
    finish_package(modules_dev_root, modules_dev_control, modules_dev_output)

    meta_root = work / 'meta'
    meta_control = extract_package(args.base_meta, meta_root, 'fcitx5')
    if stock_dependency not in meta_control:
        raise ValueError(f'Missing expected dependency: {stock_dependency}')
    meta_control = meta_control.replace(stock_dependency, patched_dependency)
    meta_output = args.output_dir / f'fcitx5_{PATCHED_VERSION}_amd64.deb'
    finish_package(meta_root, meta_control, meta_output)

print(modules_output)
print(modules_dev_output)
print(meta_output)
