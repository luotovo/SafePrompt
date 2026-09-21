# SafePrompt Windows Packaging RC

## Scope and baseline

- Source baseline: `3d419be` (UIE integration) plus `101d151` (recovery window).
- Build host: Windows, Python 3.12.0.
- Build environment: PyInstaller 6.22.3, PaddlePaddle 2.6.2, PaddleNLP 2.6.1, PySide6 6.11.2, pynput 1.8.2, six 1.17.0.
- Model policy: UIE Nano static model is external and is not included by the spec or committed.

## Reproducible build

From the repository root:

```powershell
.benchmark-venvs\uie-nano\Scripts\pyinstaller.exe --clean --noconfirm --distpath release\dist --workpath release\build release\SafePrompt.spec
```

The final clean build exited 0 in about 256,597 ms. The executable is
`release\dist\SafePrompt\SafePrompt.exe`. The build automatically includes
PySide6, the tray UI, pynput's Windows keyboard backend, Paddle, PaddleNLP, and
`paddle\libs\mklml.dll`; no DLL was copied into the final dist by hand. DPAPI is
called through the Windows `crypt32` API and was verified in the frozen probe.

Final sizes:

- onedir application without model: 733,555,692 bytes (699.573 MiB)
- external static model: 71,538,217 bytes (8 files)
- application plus external model: 805,093,909 bytes (767.797 MiB, 3,872 files)
- `SafePrompt.exe`: 40,949,574 bytes
- automatically collected `mklml.dll`: 92,649,344 bytes

The copied RC model was byte-for-byte SHA-256 manifest-equivalent to the
prepared local snapshot. It remains ignored under
`release\dist\SafePrompt\models\uie-nano-static`.

## Release fixes

1. Frozen startup now registers only the executable. Development startup still
   registers Python plus `main.py`.
2. The local UIE loader sets PaddleNLP's `DOWNLOAD_CHECK` guard before Taskflow
   construction and retains the fail-closed socket guard.
3. `hook-paddlenlp.py` includes `mklml.dll` and keeps the required PaddleNLP and
   SciPy modules as source.
4. A runtime hook supplies `_path` on six's namespace importer. This fixes the
   Python 3.12 PySide/Shiboken inspection failure reached through pynput.
5. The spec excludes ambient Poppler `icuuc.dll` and `icudt78.dll`. They were
   discovered through the developer PATH and caused QtCore to load an
   incompatible ICU 78 DLL instead of the Windows ICU shim.
6. UIE is loaded, warmed, and invoked on one persistent background worker.
   Paddle's predictor failed when it was constructed on one thread and invoked
   on another; the same-thread worker preserves the two-second request timeout
   without blocking the Qt UI.

## Frozen validation

- No-cwd startup: launched the absolute EXE from `F:\code`; it remained alive
  for 10 seconds and was then stopped by the probe.
- Frozen UI probe: exit 0. The tray was visible, both global hotkey listeners
  were alive, and the real Qt clipboard/preview path produced the expected
  PERSON, ORG, IP, PHONE, EMAIL, and PASSWORD placeholders. The probe restored
  the user's prior clipboard contents before exiting.
- Frozen offline pipeline probe: exit 0. The requested synthetic V1 sample
  returned `PERSON 韩静` and `ORG 海川大学`, merged them with rule results via
  the shared Finding/overlap/mask pipeline, and produced the expected safe text.
- Recovery E2E restored PERSON, ORG, and EMAIL from the simulated AI reply.
  The same frozen probe also passed 15-minute expiry, new-session overwrite,
  and manual clear checks.
- Network fail-closed: socket connect and `create_connection` were blocked for
  both model construction and inference; recorded network attempts were empty.
  This was a process-level network test; the machine's network adapter was not
  disabled.
- DPAPI: a synthetic byte sequence protected and unprotected successfully in
  the frozen process.
- Missing model: exit 2 with an explicit `FileNotFoundError`, no
  network attempt, no creation of the missing model path, and no cache-file
  delta.
- Cache behavior: Paddle/PaddleNLP created empty cache directory scaffolding in
  the isolated process home, but wrote zero cache files.
- The frozen UI probe temporarily used the clipboard but saved and restored its
  original text. It invoked the same handlers as Ctrl+Shift+S/Ctrl+Shift+R;
  physical key injection itself was not used.

## Threshold facts

- SafePrompt's `MODEL_THRESHOLDS` currently has no non-zero UIE override, so
  validated adapter results pass the SafePrompt post-filter at threshold `0.0`.
- The production adapter explicitly passes the already validated
  `position_prob=0.5` to PaddleNLP Taskflow UIE. This is the effective extraction
  threshold and no longer depends on PaddleNLP's future default value.
- The 56-sample selection benchmark scored the adapter's returned spans without
  an additional SafePrompt threshold. No threshold was tuned for this RC.

## Recovery privacy semantics

The active recovery mapping exists only in current-process memory. A Qt
single-shot timer expires it after 15 minutes, clears the mapping, and releases
the application's session reference. A new successful safe copy clears and
replaces the prior session; manual clear and application exit do the same. The
mapping is never written to settings, logs, statistics, or disk. This is
reference release, not a claim of secure memory wiping.

## Tests and warnings

- `python -m pytest -q`: 63 passed.
- The dedicated packaging venv does not contain pytest, so the same suite was
  not duplicated there.
- PyInstaller's warning file contains optional/cross-platform imports. No
  missing module in that list blocked startup or the verified UIE path.
- The frozen inference emitted PaddleNLP deprecation and invalid-escape
  warnings; inference still completed successfully.

## Evidence

- Final build: `release/evidence/build/`
- Original six/Shiboken traceback: `release/evidence/rc-probe-process/`
- QtCore/ambient ICU failure: `release/evidence/missing-model/`
- Frozen offline inference: `release/evidence/frozen-offline-success/` and
  `release/evidence/frozen-offline-success-result.json`
- Frozen missing-model check: `release/evidence/frozen-missing-model/` and
  `release/evidence/frozen-missing-model-result.json`
- No-cwd startup: `release/evidence/frozen-startup.json`
- Final clean build log: `release/evidence/final-clean-build-thread-affinity.log`
- Final frozen UI E2E: `release/evidence/rc-frozen-ui-e2e.json`
- Final offline pipeline E2E: `release/evidence/rc-frozen-offline-e2e.json`
- Final missing-model check: `release/evidence/rc-frozen-missing-model.json`
