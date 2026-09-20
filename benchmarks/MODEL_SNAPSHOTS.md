# Benchmark model snapshots

- UER CLUENER: `uer/roberta-base-finetuned-cluener2020-chinese@cddd8fc233e373855a8c0a7f4b7eb83acb686a2b`
- UIE Nano static runtime directory: manifest SHA-256 `954c292a19536ef55d320b3b903c5fdfa028f1d0dcdd765050fa5e7382dc378d`.
- Taskflow NER fast/LAC static runtime directory: manifest SHA-256 `149c2239223face281545bc742d774e1b6bfa5cbcf0327d6d438b16b877975a2`.
- UER local directory manifest SHA-256: `581da658016d3bd44df39173385af70201a1e49de1e8999721ea93d2e4b138d4`.

Environment pins: Python 3.12.0, UER `torch==2.6.0` / `transformers==4.48.3`; Paddle candidates `paddlepaddle==2.6.2` / `paddlenlp==2.6.1`. Paddle 3.3.1 was rejected because PaddleNLP 2.6.1 Taskflow expects the legacy static runtime format. PaddleNLP 2.8.1 and 2.7.2 were rejected because their published dependency metadata required unavailable `tool-helpers` on this machine.

Paddle Taskflow resources are versioned static artifacts rather than a single repository revision in this setup. A benchmark run is invalid until its local snapshot manifest is recorded.
