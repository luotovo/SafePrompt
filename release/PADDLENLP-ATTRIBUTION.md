# PaddleNLP-Derived Code Attribution

Status: prepared for review; not yet a complete release notice bundle.

Parts of `safeprompt/adapters/onnx_uie.py`, including the lightweight ERNIE-compatible tokenizer,
preprocessing behavior and UIE span-pairing/decoder logic, are based on and adapted from PaddleNLP 2.6.1
ERNIE tokenizer and UIE helper implementations.

- Upstream project: PaddlePaddle/PaddleNLP
- Upstream version: 2.6.1
- Upstream source: `https://github.com/PaddlePaddle/PaddleNLP/tree/v2.6.1`
- Upstream license: Apache License 2.0

Modifications for SafePrompt include a reduced pure-Python tokenizer surface, local vocabulary loading,
fixed-shape ONNX input preparation, chunk offset handling, a compact span decoder, and integration with
SafePrompt's local ONNX inference interface. The adaptation does not include the Paddle or PaddleNLP
runtime.

Before binary release, include the unmodified official PaddleNLP/Apache-2.0 license text and retain an
appropriate modification notice. This attribution does not license the UIE Nano model weights, vocabulary
or configuration assets; those remain separately blocked pending official clarification.
