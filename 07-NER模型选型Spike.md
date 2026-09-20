# SafePrompt NER 模型选型 Spike

## 目标

只评测 `PERSON` 与 `ORG`。所有模型必须在安装阶段准备到本地目录，运行时禁止联网；适配器必须使用本地路径和离线加载参数。

## 候选

| 候选 | 选择理由 | 主要风险 | 当前状态 |
| --- | --- | --- | --- |
| UER RoBERTa Base + CLUENER2020 | 标准 token classification；模型卡明确使用 CLUENER2020，含 name、company、organization 等标签；容易映射为 PERSON/ORG | Torch/Transformers 体积较大 | benchmark 已完成，未选型 |
| PaddleNLP UIE Nano | 官方提供中文 nano 版本；可用“人名、组织机构”schema，结果自带 start/end/probability | Paddle 运行时和 Windows 打包复杂 | benchmark 已完成，未选型 |
| PaddleNLP Taskflow NER (LAC) | 官方 Taskflow 的轻量中文 NER 路径，适合作为低成本基线 | 无可靠 confidence，当前正式 Finding 转换不会接受 | benchmark 已完成，未选型 |

资料：

- [UER CLUENER 模型卡](https://huggingface.co/uer/roberta-base-finetuned-cluener2020-chinese)
- [PaddleNLP UIE 文档](https://github.com/PaddlePaddle/PaddleNLP/blob/develop/slm/model_zoo/uie/README.md)
- [PaddleNLP Taskflow 文档](https://paddlenlp.readthedocs.io/en/latest/model_zoo/taskflow.html)

## 统一评测

评测集使用构造的日志、需求、工单和配置文本，不包含真实客户数据。每个适配器在同一 Windows CPU 环境执行：

1. 断网启动并从本地目录加载。
2. 记录首次加载时间、进程内存增量和模型目录大小。
3. 每个候选用 3 个全新 Python 进程串行运行。每个进程预热一次后，对每条样本重复五次；准确率 prediction 与 timing 调用分离。
4. 分别计算 PERSON、ORG 的 precision、recall、F1。
5. 验证 1,000 字输入总耗时是否小于 2 秒。
6. 使用 PyInstaller 做最小打包验证并记录额外体积与缺失动态库。

## 决策门槛

- 运行时完全离线，缺少模型时只降级，不尝试下载。
- PERSON 与 ORG 均不能因映射而变成 CUSTOMER。
- 1,000 字 CPU 推理目标小于 2 秒。
- 优先选择实际召回更高且误报可控的最小模型；指标接近时选择依赖和打包更简单的方案。

当前不确定正式模型。本轮只记录同机实测，不作正式选型。

## 适配约定

- UER CLUENER：`name → PERSON`，`company/government/organization → ORG`。使用 Transformers `average` 聚合后的 span score；超过上下文的文本按 token 分块并保留 64 token overlap。
- UIE：schema 固定为“人名”“组织机构”，分别只映射为 `PERSON`、`ORG`；使用模型返回的 span probability。
- Taskflow NER：仅接受实际输出中的 `PER → PERSON`、`ORG → ORG`。标准接口没有可靠 confidence 时只参与无阈值基准，不填造 `1.0`，也不进入要求有效 confidence 的正式 Finding 转换。
- 各模型独立在同一验证集上调阈值，不横向比较原始 confidence。

## 超时语义

V1 的线程超时保证调用方在约 2 秒后返回规则与词库结果，不会强杀正在运行的推理线程。每个候选还需记录超时后 CPU 是否持续占用、正常 1,000 字耗时及加载失败后的资源残留；存在长时间卡死的候选不得进入 V1。

## 实测结果

统一数据由 `benchmarks/ner_dataset.py` 生成，仅包含合成文本；运行入口为 `benchmarks/run_ner_benchmark.py`。

环境统一为 Windows 11 `10.0.26200`、Python `3.12.0`、CPU 模式。UER 使用 Torch `2.6.0` / Transformers `4.48.3`；UIE 与 Taskflow 使用 Paddle `2.6.2` / PaddleNLP `2.6.1`。评分是未调阈值的 raw exact-span 结果。

跨进程汇总取 3 个进程各自统计值的中位数，不合并未保存的 repeat 级 timing。普通样本与 `>=1000` 字长文本互斥。表中 RSS 是短样本预热后的当前 Working Set 增量，不是总 RSS 或峰值内存。

| 候选 | cold load 中位数 | 普通 median / p95 / max | 长文本 median / p95 / max | PERSON P/R/F1 | ORG P/R/F1 | FP | RSS 增量 | runtime 模型目录 |
| --- | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: |
| UER CLUENER | 5,105.97 ms | 49.43 / 72.82 / 90.31 ms | 1,019.07 / 1,089.30 / 1,089.30 ms | .9062 / .8286 / .8657 | .6829 / .8485 / .7568 | 16 | 610,267,136 B | 407,010,299 B |
| UIE Nano | 8,481.63 ms | 85.38 / 107.74 / 168.74 ms | 278.95 / 285.52 / 285.52 ms | .9722 / 1 / .9859 | 1 / .9697 / .9846 | 1 | 500,305,920 B | 71,538,217 B |
| Taskflow NER | 5,386.08 ms | 12.45 / 21.43 / 32.06 ms | 358.68 / 373.78 / 373.78 ms | 1 / .8 / .8889 | .8649 / .9697 / .9143 | 5 | 389,541,888 B | 32,704,790 B |

### 三次 fresh-process 原值

单位均为 ms。`long p95=max` 是因为正式集只有 1 条 1,228 字长文本，每进程只有该文本的 5 次 timing；不能解释为多文本尾延迟。

| 候选 / run | cold load | 普通 median / p95 / max | 长文本 median / p95 / max | RSS 增量 |
| --- | ---: | ---: | ---: | ---: |
| UER #1 | 10,892.49 | 49.43 / 72.82 / 89.30 | 948.97 / 1,013.12 / 1,013.12 | 610,766,848 B |
| UER #2 | 4,966.99 | 51.99 / 76.49 / 90.31 | 1,120.71 / 1,143.25 / 1,143.25 | 610,267,136 B |
| UER #3 | 5,105.97 | 48.11 / 58.37 / 103.01 | 1,019.07 / 1,089.30 / 1,089.30 | 609,464,320 B |
| UIE #1 | 8,481.63 | 82.97 / 107.74 / 159.42 | 254.62 / 263.47 / 263.47 | 500,686,848 B |
| UIE #2 | 5,763.15 | 85.38 / 118.94 / 238.63 | 278.95 / 285.52 / 285.52 | 500,305,920 B |
| UIE #3 | 44,714.75 | 89.24 / 104.80 / 168.74 | 289.55 / 291.46 / 291.46 | 499,191,808 B |
| Taskflow #1 | 35,342.02 | 13.99 / 24.44 / 40.62 | 358.80 / 373.78 / 373.78 | 389,804,032 B |
| Taskflow #2 | 5,353.90 | 12.45 / 21.43 / 32.06 | 358.68 / 375.19 / 375.19 | 389,541,888 B |
| Taskflow #3 | 5,386.08 | 12.15 / 20.41 / 31.32 | 334.55 / 336.58 / 336.58 | 389,402,624 B |

所有 9 份有效 JSON 与 stderr 在 `benchmarks/results/`。cold load 是解释器内第一次 import + loader，不含解释器启动，也不是冷磁盘；UIE #3 与 Taskflow #1 的异常峰值原样保留。UER 三轮所有已计时推理均小于 2 秒，最高长文本 max 为 1,143.25 ms。

### 模型快照与数据集

- UER：`uer/roberta-base-finetuned-cluener2020-chinese@cddd8fc233e373855a8c0a7f4b7eb83acb686a2b`；本地 manifest SHA-256 `581da658016d3bd44df39173385af70201a1e49de1e8999721ea93d2e4b138d4`。
- UIE static：manifest SHA-256 `954c292a19536ef55d320b3b903c5fdfa028f1d0dcdd765050fa5e7382dc378d`。
- Taskflow static：manifest SHA-256 `149c2239223face281545bc742d774e1b6bfa5cbcf0327d6d438b16b877975a2`。
- 三份 manifest 收尾复核 mismatch 均为 0。Paddle 准备目录保留动态与静态双份，完整准备根分别约 143,386,915 B 与 67,387,844 B；主表只列实际 loader 使用的 static runtime path。
- 数据集 56 条：PERSON gold 35、ORG gold 33、负样本 20、长文本 1。`ner_dataset.py` SHA-256 为 `3d1b0f0fc04ce22823c24eac2c33be8d8cc060af51b684734ecf9ef29c30a09c`，`ner_samples.jsonl` 为 `ebee70d695b910b5e2af9bf4af7f675208feb12a5907bba1a76eb11b2744c6a`。
- benchmark 开始时项目还没有 Git 元数据，因此没有更早的 VCS 基线可独立证明 gold 历史未变；本轮开始记录与结束复核的 hash 一致，项目随后已初始化 Git。

### 离线与缺失模型

本轮使用全新进程，并在 adapter 加载与推理期间让 Python `socket.connect` / `socket.create_connection` fail-closed。它不是物理禁用网卡，也不是系统级连接审计。

| 候选 | 本地启动+真实推理 | 启动+推理耗时 | 观察到的 Python 网络尝试 | 不存在路径 |
| --- | --- | ---: | --- | --- |
| UER | 成功 | 23,874.67 ms | `[]` | exit 1，`OSError: Incorrect path_or_model_id`，未创建目录 |
| UIE Nano | 成功 | 11,302.41 ms | `[]` | exit 1，`FileNotFoundError`，未创建目录 |
| Taskflow NER | 成功 | 10,361.57 ms | `[]` | exit 1，`FileNotFoundError`，未创建目录 |

物理断网启动未测。上述结果可证明受监控的 Python socket 路径没有连接尝试，不能证明原生库或被内部吞掉的连接尝试绝对不存在。

### PyInstaller 最小打包

PyInstaller `6.22.3`，统一 `--clean --onedir --noconfirm --paths .`；各独立环境最小 baseline 均为 19,401,285 B 且启动 exit 0。模型外置，`dist + runtime model` 不是完整 SafePrompt 发布体积。首次三模型横向打包阶段均构建成功，但当时没有一个冻结后的 recognizer 成功运行到推理阶段。

| 候选 | candidate dist | 相对 baseline 增量 | dist + runtime model | 独立启动结果 |
| --- | ---: | ---: | ---: | --- |
| UER | 468,233,236 B | 448,831,951 B | 875,243,535 B | exit 1；已有 `hook-torch.py` / `hook-transformers.py`，但 Transformers pipeline 导入链到 `torch._numpy._ufuncs.py:235` 后 `NameError: name 'name' is not defined` |
| UIE Nano（默认） | 531,085,012 B | 511,683,727 B | 602,623,229 B | exit 1；冻结目录缺 PaddleNLP AutoConfig 要求的 `paddlenlp/transformers` data tree |
| UIE Nano（一次 datafix） | 545,190,343 B | 525,789,058 B | 616,728,560 B | 加入 `paddlenlp/transformers` 后首个错误消失；随后在 `scipy.stats._distn_infrastructure` 报 `NameError: obj is not defined`，exit 1 |
| Taskflow NER（默认） | 531,085,012 B | 511,683,727 B | 563,789,802 B | exit 1；同样缺 `paddlenlp/transformers` data tree；未重复 UIE 已证明仍会进入的深层 datafix 链 |

首次打包进程未观察到网络尝试，也未先遇到 missing DLL；但因为三者当时都未到推理阶段，不能据此证明后续 DLL/runtime 完整。干净 VM 或另一台机器启动未测。原始 spec/build/dist/warn/xref 保存在 `benchmarks/results/pyinstaller/`。

### UIE Nano Windows Packaging Spike

三模型横向 benchmark 结束后，仅对 UIE Nano 做了独立 packaging/runtime 定位。固定环境仍为 Python `3.12.0`、Paddle `2.6.2`、PaddleNLP `2.6.1`、PyInstaller `6.22.3`；没有修改模型、gold set、正式 SafePrompt app/core/NER loader。

最终最小入口为 `benchmarks/packaging_uie_smoke.py`，构建命令为：

```powershell
.benchmark-venvs\uie-nano\Scripts\pyinstaller.exe --clean --onedir --noconfirm --paths . --additional-hooks-dir benchmarks\pyinstaller_hooks --distpath benchmarks\results\uie-packaging-spike\attempt2\dist --workpath benchmarks\results\uie-packaging-spike\attempt2\build --specpath benchmarks\results\uie-packaging-spike\attempt2\spec --name uie-recognizer benchmarks\packaging_uie_smoke.py
```

生成的 spec 位于 `benchmarks/results/uie-packaging-spike/attempt2/spec/uie-recognizer.spec`。自定义 hook 为 `benchmarks/pyinstaller_hooks/hook-paddlenlp.py`：

- `paddlenlp.transformers` 使用纯 `py` source collection，满足 PaddleNLP 2.6.1 AutoConfig 对真实源码目录的扫描。
- `scipy.stats._distn_infrastructure` 使用纯 `py` source collection，避免 frozen PYZ 下的 `NameError: obj is not defined`。
- 显式收集 `paddle/libs/mklml.dll` 到原包布局；没有额外 hidden imports、data files、runtime hook 或 PATH 修改。

定位过程：

1. 既有 datafix 已解决 `paddlenlp/transformers` 目录缺失，但 frozen PYZ 中的 SciPy 模块在 `del obj` 时报 `NameError`。同一模块在普通 Python 中导入成功，证明问题仅发生在 frozen/PYZ 路径。
2. `pyz+py` 同时存在时仍优先加载 PYZ，因此 attempt1 继续失败。
3. attempt2 改成纯 source mode 后进入 Paddle static predictor，随后暴露唯一明确 native 缺项：`mklml.dll` error 126。
4. 将 pinned venv 中的 `mklml.dll` 按 `_internal/paddle/libs` 原布局补入 attempt2 dist 后，新进程真实推理成功。

成功验证：

- 输入：`韩静在海川大学提交了报告。`
- 输出：`PERSON 韩静 [0,2]`、`ORG 海川大学 [3,7]`。
- executable exit code：`0`。
- executable-relative 外置模型路径启动：成功；不依赖当前 cwd。
- 启动并完成一次推理：约 `4.82s`。
- 进程级 socket fail-closed 下 `network_attempts=[]`。
- 构造 Taskflow 前设置 `paddlenlp.taskflow.utils.DOWNLOAD_CHECK=True`，避免本地模型路径仍触发匿名统计请求。
- 缺失模型路径：约 `304.67ms` 后 exit `1`，在导入 PaddleNLP 前由 preflight 报出缺失配置和模型参数对。
- 缺失模型路径与隔离的 `PADDLE_HOME` / `PPNLP_HOME` / `HF_HOME` 前后均不存在，没有创建缓存目录。
- UIE static manifest mismatch 为 `0`，模型未修改。

| 项目 | 实测大小 |
| --- | ---: |
| 同环境最小 baseline | 19,401,285 B |
| 成功的 patched onedir dist | 628,113,553 B |
| 相对 baseline 增量 | 608,712,268 B |
| 外置 UIE static model | 71,538,217 B |
| dist + 外置模型 | 699,651,770 B |
| `mklml.dll` | 92,649,344 B |

`mklml.dll` SHA-256 为 `e2a7fd93e1534568626cffe22676b15164a5a2b3a62f1919a55993478b45811e`。成功 executable SHA-256 为 `72153c24aaa0f667be70d1550273d022d75a0db981eb78d1974442189ce31488`。

边界：`mklml.dll` 规则是在 attempt2 clean build 暴露缺项后写入最终 hook；遵守两次 build 上限，没有再做第三次 clean rebuild。成功产物是同一 attempt2 dist 经 `benchmarks/apply_uie_dist_dll_fix.py` 可审计补入同一 DLL 后的结果；最终 hook 从零 clean rebuild 的可重复性仍未测。物理断网、系统级连接审计和干净 VM 仍未测。完整 stdout/stderr、traceback、warnings、spec、TOC、xref 与运行证据索引见 `benchmarks/results/uie-packaging-spike/README.md`。

### timeout 后资源行为

受控 CPU-bound recognizer 运行 2.5 秒，`NerService.timeout_seconds=2.0`：调用方在 2,034.43 ms 返回空结果并将服务标记 unavailable；返回时后台线程仍运行，466.38 ms 后结束。timeout 前后分别消耗约 2.046875 / 0.46875 CPU 秒，等待后非主线程列表为空。此次未观察到长期 CPU 占用、线程不结束或明显资源残留；线程方案仍然不具备强杀能力。

### 限制与审计记录

- 普通样本与长文本延迟最初被混在同一个池中；修复后三个候选全部重跑。旧 UER 结果以 `pre-fix-*` 保留，仅作审计，不进入主表。
- 两次 UIE 因传入模型父目录而失败，日志以 `invalid-wrong-model-path-*` 保留，不计入结果。
- 延迟是同文本已有一次 accuracy 调用后的 warm steady-state，不是 first-inference latency。
- FP 是 PERSON + ORG exact-span FP 总数，不是文档级误报率。
- 合成集规模小且模板化，不能外推真实客户文本分布。
- Taskflow 的 `confidence=None` 仅参与无阈值 benchmark；当前正式 `to_findings()` 会拒绝它。
- 只有顶层依赖版本和模型 manifest 被固定，没有完整 transitive lock。
- 事实汇总保存在 `benchmarks/results/packaging-offline-timeout-facts.json`。本轮完整测试为 `39 passed`。
