# SafePrompt

SafePrompt 是一个面向 Windows 的本地 AI 安全剪贴板工具。

在将日志、SQL、JSON、代码、接口数据或客户信息发送给 ChatGPT、Claude、Codex 等 AI 工具前，SafePrompt 会先在本地识别敏感信息，并将其替换为可恢复的占位符。AI 返回结果后，也可以在本地将这些占位符恢复为原始实体。

它不接管浏览器，也不会自动向 AI 发送数据。

## 工作流程

```text
复制原始文本
    ↓
Ctrl + Shift + S
    ↓
本地检测敏感信息
    ↓
确认需要脱敏的内容
    ↓
复制安全文本
    ↓
发送给任意 AI
    ↓
复制 AI 回复
    ↓
Ctrl + Shift + R
    ↓
本地恢复原始实体
```

原始内容：

```text
张明反馈星河科技有限公司的服务器 10.20.8.15 无法访问。
邮箱：zhangming@example.com
password=123456
```

脱敏后：

```text
<PERSON_1>反馈<ORG_1>的服务器 <IP_1> 无法访问。
邮箱：<EMAIL_1>
password=<PASSWORD_1>
```

AI 返回：

```text
建议先让<PERSON_1>确认<IP_1>是否可以正常访问。
```

SafePrompt 可在本地恢复为：

```text
建议先让张明确认10.20.8.15是否可以正常访问。
```

## 主要功能

### 本地敏感信息检测

当前支持的类别包括：

- 人名 `PERSON`
- 组织机构 `ORG`
- 手机号 `PHONE`
- 邮箱 `EMAIL`
- IP 地址 `IP`
- URL
- 身份证号 `ID_CARD`
- Password / Secret
- Token / Bearer Token
- API Key
- 数据库连接凭据 `DB_CREDENTIAL`
- JSON、日志和 Key-Value 中的结构化 `ID`
- 本地自定义词库

SafePrompt Core 的固定格式信息主要通过规则识别。Hybrid Lite 源码配置使用本地 ONNX UIE Nano 识别 `PERSON` 与 `ORG`；规则、词库和 UIE 结果都会进入同一套冲突处理与替换流程。

### 一致占位符

同一实体在同一份文本中重复出现时，会复用同一个占位符：

```text
张明 -> <PERSON_1>
张明 -> <PERSON_1>
```

SafePrompt 会避开原文本中已有的合法占位符。例如原文已有 `<PERSON_1>` 时，新识别出的张明会从下一个可用编号开始，不会破坏原有内容。

### AI 回复本地恢复

按 `Ctrl + Shift + R` 可恢复当前剪贴板中的 SafePrompt 占位符。

- Recovery Mapping 仅存在于当前进程内存
- 默认有效期为 15 分钟
- 新任务会覆盖上一份映射
- 可以从托盘菜单手动清除
- 应用退出后立即失效
- 不写入磁盘，也不保存恢复历史

未知占位符不会猜测恢复：

```text
<PERSON_1> -> 张明
<PERSON_99> -> 不存在
```

恢复结果：

```text
张明
<PERSON_99>
```

## 隐私设计

SafePrompt 采用本地优先设计：

- 不上传剪贴板原文或 Recovery Mapping
- 不保存剪贴板、脱敏文本或 AI 回复历史
- 不自动操作浏览器或向 AI 发送内容
- Core 规则、词库和脱敏流程可离线运行
- UIE 是可选本地增强能力；模型或运行时不可用时，规则与词库仍可继续运行
- 本地设置使用当前 Windows 用户的 DPAPI 保护

SafePrompt 不控制 Windows 剪贴板历史、云剪贴板同步或第三方剪贴板工具；如需严格避免系统级留存，请同时检查这些系统设置。

## 快捷键与设置

| 快捷键 | 功能 |
| --- | --- |
| `Ctrl + Shift + S` | 检测并脱敏当前文本剪贴板 |
| `Ctrl + Shift + R` | 恢复当前 AI 回复中的占位符 |

应用启动后常驻 Windows 托盘。设置页可配置默认脱敏类别、高风险提示、词库、快捷键以及当前用户的开机启动项。

单次处理最多支持 100,000 个字符；超出时会提示先截取需要处理的内容。

## 适用场景

- 开发日志、代码和 SQL
- JSON、HTTP 请求/响应与接口 Payload
- 配置文件和数据库连接信息
- 数据迁移数据、客户需求和工单
- 项目交付资料与 AI 辅助排障内容

例如 Bearer Token 会保留语法结构，只隐藏凭据值：

```text
Authorization: Bearer eyJ...
```

```text
Authorization: Bearer <TOKEN_1>
```

结构化 ID 也会按字段语义处理：

```json
{
  "userId": "068226",
  "recordId": "2309820071649066686",
  "count": 20
}
```

```json
{
  "userId": "<ID_1>",
  "recordId": "<ID_2>",
  "count": 20
}
```

普通数量、状态码、页码和时间戳不会仅因数字形态自动被识别为 ID。

## 已构建便携包的使用方式

> 本仓库只发布源码，不包含比赛 ZIP、EXE 或 UIE 模型资产。以下步骤仅适用于已合法获得便携包的用户。

1. 解压 SafePrompt Windows 便携包，双击 `SafePrompt.exe`；应用启动后常驻 Windows 托盘，无需安装或联网。
2. 复制需要处理的文本，按 `Ctrl + Shift + S`，确认人名、机构、手机、邮箱、身份证、银行卡、IP、Password、Token、API Key 等敏感信息后复制脱敏文本。
3. 将脱敏文本发送给 AI；收到回复后复制回复并按 `Ctrl + Shift + R`，在本地恢复原始信息。

## 从源码运行

环境：Windows、Python 3.12。Core 版本不需要修改源码，也不需要下载模型。

```powershell
git clone https://github.com/luotovo/SafePrompt.git
cd SafePrompt

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements-core.txt
python main.py
```

首次启动后请检查 Windows 托盘区域。若托盘图标被系统折叠，可在 Windows 的任务栏设置中显示它。

如果 PowerShell 禁止当前会话激活虚拟环境，可直接使用：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-core.txt
.\.venv\Scripts\python.exe main.py
```

## 本地 UIE 模型（可选）

仓库不包含 UIE 模型文件，也不包含构建后的 Windows release artifact。

SafePrompt V1.1 Core 不依赖 AI 模型。没有 UIE 时，仍可使用规则、Structured ID、本地词库、中文 PERSON-lite、脱敏和 Recovery；Core 不提供通用自动 ORG NER。

UIE Nano 是可选本地 AI 增强能力，可提升复杂 PERSON 与自动 ORG 识别。当前 Windows Core Release 不包含 UIE 模型、Paddle 或 PaddleNLP 运行时。

Hybrid Lite 源码配置不需要 Paddle、PaddleNLP、Transformers 或 tokenizers。安装本地 ONNX 运行时：

```powershell
python -m pip install -r requirements-hybrid.txt
```

将准备好的本地 ONNX UIE 资产放入：

```text
models/uie-nano-onnx/
```

目录至少需要包含：

```text
model.onnx
vocab.txt
tokenizer_config.json
config.json
```

源码测试也可以通过环境变量指定其他本地目录：

```powershell
$env:SAFEPROMPT_UIE_ONNX_DIR = "F:\path\to\uie-nano-onnx"
python main.py
```

该路径只读取本地文件；运行时不会下载模型。`requirements-ai.txt` 与 Paddle 静态模型入口暂时保留，仅用于 Full 对照验证。

当前 Hybrid 验证环境：

```text
Python        3.12.0
ONNX Runtime  1.22.1
NumPy         2.5.3
```

冻结构建使用 PyInstaller 6.22.3。

运行时会拒绝模型组件联网下载资源；本地模型缺失或加载失败时会明确降级，不阻断规则和词库处理。

## 运行测试

测试工具不属于产品运行依赖，需要单独安装：

```powershell
python -m pip install pytest
python -m pytest -q
```

未配置 UIE 模型时，需要真实模型的测试会跳过。

## 当前状态

当前公开仓库为 SafePrompt V1.1 Hybrid 的源码快照。仓库不分发 UIE Nano 模型或构建后的 Windows artifact。

已验证：

- Windows Core frozen build
- 无 UIE 的中文 PERSON-lite
- Rule + Dictionary + PERSON-lite + optional UIE 统一检测
- Structured ID、Bearer Token 与数据库凭据处理
- 长代码、日志、JSON 和 Recovery Preview
- Placeholder collision protection
- Offline fail-closed 与 missing-model fallback

当前公开源码测试：`226 passed, 1 skipped`

## 已知限制

- PERSON-lite 主要面向中文姓名，基于确定性规则与上下文；极端语言场景可能漏报或误报，不是完整 NER 模型
- Core 不自动提供通用 ORG NER；组织名称可通过本地词库处理，UIE AI Profile 可增强自动 ORG 识别
- 部分英文姓名的识别边界有限
- 极端复杂 URL 可能拆分为内部 EMAIL/IP 等敏感项处理
- 尚未覆盖所有 Windows 环境的大规模兼容性测试

这些边界不影响核心规则脱敏与 Recovery 流程。

## 项目原则

> 发送前脱敏，AI 返回后本地还原。

SafePrompt 不做云端剪贴板历史、不自动发送内容、不接管用户的 AI 工具，也不保存长期 Recovery 会话。
