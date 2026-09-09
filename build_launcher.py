"""Build a portable Windows bundle with Python dependencies included."""
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


def main():
    root = Path(__file__).resolve().parent
    output = root / 'output'
    dist = output / 'launcher'
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
        '--name', 'RosterLauncher', '--distpath', str(dist),
        '--workpath', str(output / 'launcher-build'), '--specpath', str(output),
        '--add-data', f'{root / "worlds" / "roster"};worlds/roster',
        '--collect-submodules', 'websockets', '--hidden-import', 'yaml',
        str(root / 'RosterLauncher.py'),
    ], cwd=root, check=True)
    shutil.copytree(root / 'games', dist / 'games', dirs_exist_ok=True)
    shutil.copy2(root / 'README.md', dist / 'README.md')
    if (root / 'docs').is_dir():
        shutil.copytree(root / 'docs', dist / 'docs', dirs_exist_ok=True)
    bundle = output / 'Roster-Windows.zip'
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(dist.rglob('*')):
            if path.is_file():
                archive.write(path, 'Roster/' + path.relative_to(dist).as_posix())
    print(f'Built: {bundle}')


if __name__ == '__main__':
    main()
