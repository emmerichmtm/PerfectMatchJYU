# Build on Windows: python -m PyInstaller --noconfirm PerfectMatch.spec
from pathlib import Path
import pulp

project = Path(SPECPATH)
cbc = Path(pulp.__file__).parent / "solverdir" / "cbc" / "win" / "i64"
if not (cbc / "cbc.exe").is_file():
    raise RuntimeError("Build this Windows package with 64-bit Python and PuLP 3.3.0.")

a = Analysis(
    [str(project / "browser_app.py")],
    pathex=[str(project)],
    binaries=[(str(cbc / "cbc.exe"), "pulp/solverdir/cbc/win/i64")],
    datas=[(str(project / "browser.html"), "."),
           (str(project / "manual.pdf"), "."),
           (str(project / "examples/config.csv"), "examples"),
           (str(project / "examples/problem.csv"), "examples"),
           (str(cbc / "coin-license.txt"), "pulp/solverdir/cbc/win/i64")],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["tkinter", "IPython", "matplotlib"], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PerfectMatch",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PerfectMatch")
