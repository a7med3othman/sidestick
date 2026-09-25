# PyInstaller spec. Build with build.bat (it generates assets/icon.ico first).
#
# One-folder build (not --onefile): starts faster and is far less likely to be
# flagged by antivirus, which often distrusts self-extracting executables that
# simulate input. UPX is off for the same reason.

block_cipher = None

a = Analysis(
    ["ControllerCompanion.pyw"],
    pathex=["."],
    hiddenimports=[
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "pystray._win32",
        "PIL.ImageTk",
    ],
    excludes=["numpy", "tkinter.test", "unittest", "pydoc_data", "pytest"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ControllerCompanion",
    console=False,
    icon="assets/icon.ico",
    version="version_info.txt",
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="ControllerCompanion", upx=False)
