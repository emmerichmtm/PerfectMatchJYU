"""Collect notices for the runtime and dependencies included in the Windows ZIP."""
from importlib import metadata
from pathlib import Path
import shutil
import sys


def collect(package):
    destination = package / 'Third-party notices'
    destination.mkdir(parents=True, exist_ok=True)
    versions = []
    for name in ('numpy', 'pandas', 'PuLP', 'openpyxl', 'et_xmlfile', 'python-dateutil',
                 'six', 'tzdata', 'pyinstaller'):
        dist = metadata.distribution(name)
        versions.append(f'{dist.metadata["Name"]} {dist.version}')
        for entry in dist.files or []:
            if any(word in entry.name.lower() for word in ('license', 'copying', 'notice')):
                source = Path(dist.locate_file(entry))
                if source.is_file():
                    target = destination / name / Path(*[p for p in entry.parts if p not in ('.', '..')])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        raise RuntimeError('The Python runtime LICENSE.txt was not found.')
    shutil.copy2(python_license, destination / 'Python-LICENSE.txt')
    (destination / 'VERSIONS.txt').write_text('Python '+sys.version+'\n'+'\n'.join(versions)+'\n', encoding='utf-8')


if __name__ == '__main__':
    collect(Path(sys.argv[1]))
