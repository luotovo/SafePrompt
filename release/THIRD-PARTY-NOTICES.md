# SafePrompt Hybrid Lite — Third-Party Notices

Prepared for the controlled D2-R2 build on 2026-09-24. This notice covers the executable runtime;
the UIE Nano model, vocabulary and configuration assets remain blocked pending written licensing evidence.

The accompanying `LICENSES` directory contains the exact license texts and notices used for this build:

- Qt 6.11.2, PySide6 6.11.2 and Shiboken6 6.11.2: community LGPL-3.0/GPL alternatives. Exact wheel
  metadata and the Qt LGPL/GPL texts are included. Sources: `https://code.qt.io/cgit/qt/qt5.git/tag/?h=v6.11.2`
  and `https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.11.2`.
- pynput 1.8.2: LGPLv3. Exact source: `https://github.com/moses-palmer/pynput/tree/v1.8.2`.
- ONNX Runtime 1.22.1: MIT. The wheel's `LICENSE` and `ThirdPartyNotices.txt` are included.
- NumPy 2.5.3 and its wheel-bundled libraries: the complete wheel `licenses/` tree is included.
- CPython 3.12.0: PSF and incorporated-software terms from the official installation `LICENSE.txt`.
- OpenSSL 3.0.11 used by CPython: Apache License 2.0; the exact OpenSSL license is included.
- six 1.17.0: MIT; pyreadline3 3.5.6: BSD-3-Clause; exact wheel license files are included.
- PyInstaller 6.22.3 bootloader/runtime: GPL exception and runtime terms; exact distribution text included.
- SafePrompt's tokenizer/decoder contains a modified adaptation of PaddleNLP 2.6.1 code. PaddleNLP's
  Apache-2.0 license is included; see `PADDLENLP-ATTRIBUTION.md` for modification attribution.

No local modifications were made to Qt, PySide6, Shiboken6, pynput, ONNX Runtime, NumPy, CPython,
OpenSSL, six, pyreadline3 or PyInstaller. Product terms must not prohibit reverse engineering performed
for debugging modifications to LGPL-covered components.
