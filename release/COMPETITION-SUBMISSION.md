# SafePrompt

## 简介

SafePrompt 是一个本地运行的 AI 隐私脱敏工具。在文本发送给 AI 前，它会自动检测并替换敏感信息；AI 返回内容后，可在本地恢复原始信息。整个敏感信息处理流程均在本机完成。

## 核心功能

- PERSON 人名与 ORG 机构名称脱敏
- 手机号、邮箱、身份证、银行卡和 IP
- Password、Token 和 API Key
- 稳定的 Placeholder 管理
- 仅保存在当前进程内存中的本地 Recovery

## 使用方式

复制原始文本 → 按 `Ctrl + Shift + S` 调用 SafePrompt → 确认并复制脱敏文本 → 发送给 AI → 复制 AI 回复 → 按 `Ctrl + Shift + R` 在本地恢复。

解压比赛 ZIP 后直接双击 `SafePrompt.exe` 即可运行，无需安装。

## 特点

- 本地运行、离线可用
- 不依赖云端敏感信息检测
- 支持常见自然语言实体、结构化敏感信息和凭据
- Windows x64 portable，无需安装
- 不自动向 AI 发送内容，不保存 Recovery 历史

## 比赛版本

- Platform：Windows x64
- Portable：288.552 MiB
- ZIP：132.313 MiB
- ZIP SHA-256：`085aea516998e7bfe517ec810b7211ff512399cf80e0ba20cb0b5e69efa0ed4b`

## 测试

- PERSON Full/Hybrid A/B：118/118 exact
- ORG：34 exact，0 miss
- Mask / Recovery：100%
- Demo：20/20
- Portable probe：8/8
- Offline：PASS
- 最终状态：**COMPETITION READY**
