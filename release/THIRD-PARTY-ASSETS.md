# SafePrompt Hybrid Lite — Third-Party Assets Draft

Status: **PENDING VERIFICATION — NOT A RELEASE APPROVAL**

This draft records components actually observed in the C2 frozen engineering
artifact. It must be reviewed and completed before public distribution.

| Component | Frozen version / identity | Declared license | Current status |
|---|---|---|---|
| UIE Nano ONNX model weights | SHA-256 `d8d0ddb7c856c162604008921a7825d27691f3e85806e36a9bb15092c29c490b` | UNKNOWN | PENDING authoritative model license |
| UIE Nano `vocab.txt` | SHA-256 `8b99e7ded859fe015d33329c4a6d75cfba7784cfe8d82db7551fbf481f262fbb` | UNKNOWN | PENDING authoritative asset license |
| UIE tokenizer/model JSON assets | Locally recorded SHA-256 values in `C0B-LICENSE-MATRIX.md` | UNKNOWN | PENDING authoritative asset license |
| ONNX Runtime | 1.22.1 | MIT | License text/notice must be bundled |
| NumPy and bundled native components | 2.5.3 | BSD-3-Clause plus bundled-component licenses | Wheel license directory must be carried into release notices |
| PySide6, Qt and Shiboken | 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | PENDING license selection and distribution-compliance review |
| pynput | 1.8.2 | LGPLv3 | PENDING distribution-compliance review |
| six | 1.17.0 | MIT | License text must be bundled |
| coloredlogs / humanfriendly | 15.0.1 / 10.0 | MIT | License texts must be bundled |
| FlatBuffers | 25.12.19 | Apache-2.0 | License and NOTICE review required |
| protobuf | 7.36.2 | BSD-3-Clause | License text must be bundled |
| SymPy / mpmath | 1.14.0 / 1.3.0 | BSD-family declarations | License texts must be bundled |
| OpenSSL DLLs collected with the frozen runtime | Exact upstream mapping pending | PENDING VERIFICATION | Identify exact version/source and notices before release |

PyInstaller 6.22.3 is a build-time tool, not an intended runtime component. Its
metadata declares GPLv2-or-later with the PyInstaller distribution exception.

The file named `libscipy_openblas64_*.dll` in the artifact is supplied by the
NumPy wheel under `numpy.libs`; no SciPy Python package is present. Its notices
must be handled as part of NumPy's bundled-component license set.
