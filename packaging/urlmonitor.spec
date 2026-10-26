# PyInstaller spec for URLMonitor.exe. Build with:
#   pyinstaller --noconfirm --distpath dist --workpath build packaging/urlmonitor.spec
# mitmproxy ships its own PyInstaller hooks, which collect its data files.

from pathlib import Path

root = Path(SPECPATH).parent

a = Analysis(
    [str(root / "packaging" / "entry.py")],
    pathex=[str(root)],
    datas=[(str(root / "urlmonitor" / "web"), "urlmonitor/web")],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="URLMonitor",
    console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, name="URLMonitor")
