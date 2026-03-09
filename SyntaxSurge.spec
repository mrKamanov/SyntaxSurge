# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec для SyntaxSurge
import sys
import os
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

block_cipher = None

# Binaries: conda portaudio.dll (если собираем из Miniconda)
_binaries = []
_conda_prefix = os.environ.get("CONDA_PREFIX")
if _conda_prefix:
    _pa_dll = os.path.join(_conda_prefix, "Library", "bin", "portaudio.dll")
    if os.path.isfile(_pa_dll):
        _binaries.append((_pa_dll, "."))

# jaraco.text (через pkg_resources/setuptools) требует Lorem ipsum.txt
# sounddevice — PortAudio: pip (_sounddevice_data) или conda (portaudio.dll выше)
_datas = [('gui/icons/app', 'gui/icons/app')]
try:
    import setuptools
    _jaraco_text = os.path.join(os.path.dirname(setuptools.__file__), '_vendor', 'jaraco', 'text')
    if os.path.isdir(_jaraco_text):
        _datas.append((_jaraco_text, 'jaraco/text'))
except Exception:
    pass
try:
    import _sounddevice_data
    _sd_data = os.path.dirname(_sounddevice_data.__file__)
    _datas.append((_sd_data, '_sounddevice_data'))
except Exception:
    pass
try:
    import rapidocr
    _roc_dir = os.path.dirname(rapidocr.__file__)
    if os.path.isdir(_roc_dir) and os.path.isfile(os.path.join(_roc_dir, "default_models.yaml")):
        _datas.append((_roc_dir, "rapidocr"))
except Exception:
    pass

a = Analysis(
    ['run_gui.py'],
    pathex=[],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=[
        '_sounddevice_data',
        'numpy',
        'numpy._core',
        'numpy._core._exceptions',
        'numpy._core._multiarray_umath',
        'rapidocr',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',
        'shiboken6',
        'openai',
        'pygments',
        'pygments.lexers',
        'pygments.lexers.python',
        'pygments.lexers.javascript',
        'pygments.lexers.markup',
        'pygments.formatters',
        'pygments.formatters.html',
        'pynput',
        'pynput.keyboard',
        'pynput.mouse',
        'pyautogui',
        'onnxruntime',
        'sherpa_onnx',
        'sounddevice',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'pandas',
        'scipy',
        'torch',
        'torchvision',
        'tensorboard',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SyntaxSurge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
