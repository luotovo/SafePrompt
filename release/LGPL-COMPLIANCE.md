# LGPL Compliance and Replacement Instructions

SafePrompt Hybrid Lite is distributed as a PyInstaller **onedir** application. Qt, PySide6 and Shiboken
native libraries remain separate DLL/PYD files under `_internal`; they are dynamically loaded and are not
statically linked into `SafePrompt.exe`. A recipient may replace these files with ABI-compatible builds of
the same 6.11 series. Back up the application directory, replace only the corresponding `_internal/PySide6`,
`_internal/shiboken6` and `shiboken6.abi3.dll` files, and run the normal startup/probe checks.

`pynput` 1.8.2 is pure Python and is stored in PyInstaller's PYZ archive. To use a modified copy, obtain
SafePrompt source plus pynput 1.8.2 source, create a Python 3.12 environment, install the pinned dependencies,
place the modified pynput package ahead of site-packages, and rebuild with `release/SafePrompt-Hybrid.spec`.
Set `SAFEPROMPT_HYBRID_MODEL_DIR` to a separately authorized model staging directory. The exact PyInstaller
recipe and dependency versions are recorded by the D2 controlled-build evidence.

Corresponding upstream source locations:

- Qt 6.11.2: `https://download.qt.io/official_releases/qt/6.11/6.11.2/submodules/`
- Qt for Python / PySide6 / Shiboken6 6.11.2: `https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.11.2`
- pynput 1.8.2: `https://github.com/moses-palmer/pynput/tree/v1.8.2`

The LGPL/GPL texts and exact wheel metadata are under `LICENSES`. SafePrompt imposes no additional term
that forbids replacement, modification, or reverse engineering for debugging LGPL-covered modifications.
This engineering package does not replace legal review or resolve the separate UIE Nano asset-license block.
