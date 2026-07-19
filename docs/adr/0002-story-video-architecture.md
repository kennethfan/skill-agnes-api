# 2. Story Video Architecture

**Date**: 2026-07-19

## Context

需要为 3-6 岁儿童生成中文经典故事动画视频。要求：多角色配音（不同声音）、同一场景多条对话、角色外观一致、纯文字字幕。

## Decision

复用 poem_video 的 t2i/i2i/edge-tts/ffmpeg 管线，增加以下能力：

1. **YAML 格式扩展** — `scenes[].dialogues[]` 层级结构，每段 dialogue 指定角色和文本，可选手工指定 voice
2. **角色语音自动映射** — AI 根据角色名称自动分配 edge-tts voice（旁白→童声，大灰狼→低沉男声，小猪→活泼男声等）
3. **首图 t2i + 后续 i2i** — 第一张场景图作为角色锚定起点，后续图以首张为参考保证角色一致
4. **同场景多 dialogue 共图拼接** — 同一场景的多条对话共用一张生成图片，ffmpeg concat filter 中每条 dialogue 重复使用同一图片输入，字幕随对话切换
5. **edge-tts 重试机制** — 微软 TTS 服务偶发 `NoAudioReceived`/`The read operation timed out`，设 3 次重试 + 指数退避（1s, 2s, 4s），timeout 60s
6. **drawtext 纯文字字幕** — 白字 + 半透明阴影，无黑底遮罩，距底部 80px
7. **临时文件清理** — 所有中间音频文件存放在 `tempfile.mkdtemp()` 创建的临时目录中，合成完成后 `shutil.rmtree` 整体删除

## Consequences

- 多角色语音让故事更生动，适合 3-6 岁儿童
- 同场景共图节省 API 费用（每条对话不再需要独立生成图片）
- edge-tts 重试将成功率从 ~60% 提升至 ~95%（多数故障可在 3 次内恢复）
- 先统一生成所有音频再 ffmpeg 合成，避免逐条生成时中途失败导致部分生成了但视频不完整
- `XiaomengNeural` 和 `XiaohanNeural` 已从 edge-tts 服务端下线，映射表中移除以避免静默失败
