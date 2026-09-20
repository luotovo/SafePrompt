# UIE Nano Windows Packaging Spike evidence

Scope is limited to Python 3.12.0, Paddle 2.6.2, PaddleNLP 2.6.1, PyInstaller
6.22.3, an external static UIE Nano model, and the benchmark-only executable.

## Result

The final `attempt2` onedir executable succeeds after the recorded post-build
`mklml.dll` repair. A new process given `韩静在海川大学提交了报告。` exits 0 and
returns `PERSON 韩静 [0,2]` and `ORG 海川大学 [3,7]`. The absolute-path and
executable-relative-path runs both report `network_attempts=[]`.

The successful patched dist is 628,113,553 bytes. The same-environment minimal
baseline is 19,401,285 bytes, so the measured increment is 608,712,268 bytes.
The external runtime static model is 71,538,217 bytes; dist plus model is
699,651,770 bytes.

## Failure classification and evidence

1. `reproduce-datafix/`: existing frozen executable, exit 1. PaddleNLP source
   data was present, but `scipy.stats._distn_infrastructure:370` raised
   `NameError: obj is not defined`.
2. `native-scipy-import/`: the identical module imports under ordinary Python,
   exit 0 and empty stderr. The failure is specific to frozen/PYZ execution.
3. `attempt1-build-evidence/`, `attempt1/`, `attempt1-run/`: build exit 0. The
   first source-mode experiment used `pyz+py`; external sources existed, but
   PYZ remained preferred and the same SciPy `NameError` remained, exit 1.
4. `attempt2-build-evidence/`, `attempt2/`, `attempt2-run/`: build exit 0. Pure
   source mode for `paddlenlp.transformers` and the single failing SciPy module
   removed both namespace failures. Predictor construction then failed with
   Windows error 126 because `paddle/libs/mklml.dll` was absent.
5. `attempt2-dll-fix/`: copied the environment's pinned `mklml.dll` into the
   existing dist's `_internal/paddle/libs` directory. Size is 92,649,344 bytes;
   SHA-256 is `e2a7fd93e1534568626cffe22676b15164a5a2b3a62f1919a55993478b45811e`.
6. `attempt2-run-dllfix/`: absolute external model path, exit 0. Captured stdout
   is Windows console GBK and decodes to the required text and entities.
7. `attempt2-offline-relative/`: model path is resolved relative to the frozen
   executable directory, exit 0, required entities present, no observed Python
   socket connection attempt.
8. `attempt2-missing-model/`: nonexistent executable-relative model path fails
   preflight with exit 1 in about 305 ms. The model directory and isolated
   `PADDLE_HOME` / `PPNLP_HOME` / `HF_HOME` root were absent both before and
   after; `network_attempts=[]`.

Every probe directory contains `result.json`, exact `stdout.bin`, and exact
`stderr.bin`. Each build directory retains the generated spec, Analysis TOC,
warning file, xref, and collected output.

## Packaging inputs

- Entry point: `benchmarks/packaging_uie_smoke.py`
- Custom hook: `benchmarks/pyinstaller_hooks/hook-paddlenlp.py`
- Probe capture: `benchmarks/run_executable_probe.py`
- Auditable DLL repair: `benchmarks/apply_uie_dist_dll_fix.py`
- Explicit hidden imports: none
- Explicit data collection: none; `paddlenlp.transformers` is collected in
  source mode because PaddleNLP 2.6.1 physically scans that tree.
- Explicit binary: `paddle/libs/mklml.dll`
- Runtime hook: none
- PATH modification: none

The custom hook was updated with the `mklml.dll` binary rule after the final
build exposed the missing DLL. Per the two-attempt limit, it was not rebuilt a
third time; the current successful dist received the identical binary through
the recorded post-build repair. A clean rebuild from the final hook remains
unverified.

The successful executable SHA-256 is
`72153c24aaa0f667be70d1550273d022d75a0db981eb78d1974442189ce31488`.
The generated attempt2 spec SHA-256 is
`9999410ed62a361e4e39996dc651655fc96946ded148ca867557ec773765cbde`.
The attempt2 warning file SHA-256 is
`9002bc6f9d9f1e8d6157ba96249a8d790394fff657540bdd270f76cf41ed7a2c`.

## Verification boundary

This proves a new process on the benchmark host can run the frozen executable
with the external local model and Python socket fail-closed. It is not a clean
VM test and does not prove that native code cannot make an unobserved network
attempt. Full repository tests after the spike: `39 passed`.
