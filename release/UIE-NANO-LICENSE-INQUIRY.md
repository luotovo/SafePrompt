# UIE Nano Model Asset License Clarification Request

Suggested destination: an official PaddleNLP/PaddlePaddle maintainer channel or repository discussion.
This text has **not** been submitted.

## English

### Title

Clarification requested: license and redistribution terms for UIE Nano model assets

### Body

Hello PaddleNLP maintainers,

We are evaluating PaddleNLP 2.6.1 Taskflow `uie-nano` for offline inference in a Windows desktop
application. The application would distribute an ONNX conversion of the model together with the
executable. We found the PaddleNLP repository's Apache-2.0 license, but could not find an
asset-specific model card or license statement covering the following downloaded assets:

- `uie_nano_v1.1/model_state.pdparams`
- `uie_nano/config.json`
- shared `uie_base/vocab.txt`
- shared `uie_base/tokenizer_config.json`

Could you please clarify, separately for the UIE Nano weights, Nano config, shared vocabulary and
tokenizer config:

1. What license applies to each asset?
2. Does that license permit commercial and non-commercial use?
3. Does it permit modification and Paddle-to-ONNX format conversion?
4. Does it permit redistribution of the original assets?
5. Does it permit redistribution of the converted ONNX model?
6. May the converted model and tokenizer assets be bundled with a Windows desktop application binary?
7. What LICENSE text, NOTICE, attribution, modification notice, source offer, or other material must
   accompany such a binary distribution?
8. Does the PaddleNLP repository Apache-2.0 license explicitly cover these named model/tokenizer assets,
   or is a separate model/data license applicable?

For identification, the official PaddleNLP 2.6.1 resource table records MD5
`48db5206232e89ef16b66467562d90e5` for the UIE Nano `model_state.pdparams` file.

An explicit answer covering redistribution and conversion would help us avoid incorrectly applying the
source-code license to model assets. Thank you.

## 中文

### 标题

请求明确 UIE Nano 模型资产的许可证、转换与再分发条件

### 正文

PaddleNLP 维护者您好：

我们正在评估 PaddleNLP 2.6.1 Taskflow 的 `uie-nano`，计划在 Windows 桌面应用中进行完全离线
推理，并随应用程序分发由该模型转换得到的 ONNX 文件。我们看到了 PaddleNLP 仓库的
Apache-2.0 许可证，但没有找到明确覆盖以下资产的模型卡或资产许可证：

- `uie_nano_v1.1/model_state.pdparams`
- `uie_nano/config.json`
- 共用的 `uie_base/vocab.txt`
- 共用的 `uie_base/tokenizer_config.json`

烦请分别确认：

1. UIE Nano 权重、Nano config、共用 vocab 和 tokenizer config 各自采用什么许可证？
2. 是否允许商业和非商业使用？
3. 是否允许修改，以及从 Paddle 格式转换为 ONNX？
4. 是否允许重新分发原始资产？
5. 是否允许重新分发转换后的 ONNX 模型？
6. 是否允许把转换后的模型和 tokenizer 资产与 Windows 桌面应用二进制一起分发？
7. 分发时需要附带哪些 LICENSE、NOTICE、归属声明、修改声明、源码提供方式或其他材料？
8. PaddleNLP 仓库 Apache-2.0 是否明确覆盖上述具体模型/tokenizer 资产，还是另有模型/数据许可？

用于识别资产：PaddleNLP 2.6.1 官方资源表为 UIE Nano `model_state.pdparams` 记录的 MD5 是
`48db5206232e89ef16b66467562d90e5`。

我们希望避免把源代码许可证错误用于模型资产，因此需要一份明确覆盖转换与再分发的官方答复。谢谢。
