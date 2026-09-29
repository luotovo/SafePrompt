# UIE Nano License Research

Status: **UNKNOWN / RELEASE BLOCKER**  
Checked: 2026-09-24

## Identity and source chain

- Model: PaddleNLP Taskflow `information_extraction`, `uie-nano`.
- Reference environment: PaddleNLP 2.6.1 / 2.6.1.post.
- Architecture: four layers, hidden size 312, twelve attention heads.
- Weights URL: `https://bj.bcebos.com/paddlenlp/taskflow/information_extraction/uie_nano_v1.1/model_state.pdparams`.
- Upstream weights MD5: `48db5206232e89ef16b66467562d90e5`.
- Nano config URL: `https://bj.bcebos.com/paddlenlp/taskflow/information_extraction/uie_nano/config.json`.
- Shared vocabulary URL: `https://bj.bcebos.com/paddlenlp/taskflow/information_extraction/uie_base/vocab.txt`.
- Shared tokenizer config URL: `https://bj.bcebos.com/paddlenlp/taskflow/information_extraction/uie_base/tokenizer_config.json`.
- Shared special-token map URL (not distributed): `https://bj.bcebos.com/paddlenlp/taskflow/information_extraction/uie_base/special_tokens_map.json`.

URLs and MD5 values are from PaddleNLP 2.6.1 `paddlenlp/taskflow/information_extraction.py`.
PaddleNLP's UIE documentation identifies the model and architecture. The repository code is Apache-2.0.

## Distributed assets

| Asset | SHA-256 | Relationship |
|---|---|---|
| `model.onnx` | `d8d0ddb7c856c162604008921a7825d27691f3e85806e36a9bb15092c29c490b` | Locally converted from the Paddle static UIE Nano model; opset 11 |
| `vocab.txt` | `8b99e7ded859fe015d33329c4a6d75cfba7784cfe8d82db7551fbf481f262fbb` | Shared UIE Base asset |
| `tokenizer_config.json` | `514e28fd3eac186a14b3a79589565670073c72ab6a513632c494dfe394980cac` | Shared UIE Base asset |
| `config.json` | `e52d4051a2755851c4ced75cf1361cc845a8a0299a406b1624182ada9d08508a` | UIE Nano config |

The original Paddle weight file is not present in controlled test-data, so its SHA-256 cannot be reported.
The official resource table supplies only the MD5 above.

## Evidence checked

1. PaddleNLP v2.6.1 repository LICENSE (Apache-2.0 for repository work).
2. v2.6.1 UIE Taskflow resource table (official asset URLs and MD5 values).
3. PaddleNLP UIE README/documentation (model identity and architecture).
4. ERNIE tokenizer and UIE helper source (local-code provenance).
5. Official PaddleNLP GitHub/docs and BCE/BOS asset endpoints.
6. Current/develop PaddleNLP repository, official releases/tags, UIE GitHub issues/discussions, official
   model-community search results and available official FAQ material through 2026-09-24.

No checked source contained a model card, asset-side LICENSE, download-service license statement, or
unambiguous declaration that Apache-2.0 covers the UIE Nano weights, shared vocabulary, or JSON assets.
Downloadability and source-code licensing are not treated as redistribution permission.

## Local code provenance

`safeprompt/adapters/onnx_uie.py` entered in commit `956acf2`. Its tokenizer and span decoder are condensed,
modified, behavior-compatible adaptations of PaddleNLP 2.6.1 ERNIE tokenizer/UIE helpers and were tested
against PaddleNLP behavior. This was not a documented clean-room process. The conservative classification
is Apache-2.0-derived code requiring license inclusion, attribution, and a prominent modification notice.

## Conclusion

- Source weights license: **UNKNOWN**.
- Redistribution right: **NOT ESTABLISHED**.
- Modification/conversion right: **NOT ESTABLISHED**.
- ONNX model: derived from UIE Nano; conversion creates no independent license.
- Vocabulary/config/tokenizer asset licenses: **UNKNOWN**.
- Gate effect: **BLOCKED**.

Next evidence must be an official model page/card with license metadata, an asset-directory LICENSE, an
official statement explicitly covering these named assets, or written clarification from PaddleNLP/
PaddlePaddle maintainers expressly covering redistribution and conversion.

A ready-to-submit request is available in `release/UIE-NANO-LICENSE-INQUIRY.md`. It has not been submitted
on the user's behalf.
