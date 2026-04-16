# 流水线详细指南

## 实战教训（踩坑记录）

以下是在实际生产中总结的经验教训：

### ❌ 教训1：图片中烧入文字

**问题**：最初分镜的 image_prompt 包含了"no text"描述，但实际图片依然可能有文字，或字幕被烧入图片层，导致：
- 字幕重复（图片一层 + 字幕层一层）
- 竖屏裁剪时字幕被截断
- 图片中的文字和字幕冲突

**正确做法**：
- AI 绘图 prompt 中明确写"no text visible in image"
- **永远不要**用 Pillow 把字幕烧入图片文件
- 字幕应该作为视频的字幕轨道（soft subtitle）或在播放端渲染
- 如果必须硬字幕，用 ffmpeg 的 ` subtitles` 滤镜烧入，且只烧录 SRT 格式的纯字幕

### ❌ 教训2：背景音乐盖住配音

**问题**：早期版本 BGM 音量过大（50%+），完全压过了配音，听不清在说什么。

**正确做法**：
- BGM 音量：配音 100%，BGM 12-15%
- 使用 `amix` 的 `volume=0.12` 压制 BGM
- 配音音量可以适当提升到 1.2 倍补偿

### ❌ 教训3：音频被截断（最常见 bug）

**问题**：
- BGM 时长 ~40s，配音 ~119s
- `amix=inputs=2:duration=shortest` 把配音截到了 40s
- 视频按 40s 输出，结尾被切掉
- 用户反馈"还没说完就断了"

**根因**：
- 混音用 `duration=shortest`，按最短音频截断
- 视频和音频时长不一致时，`-shortest` 选择了错误的基准

**正确做法**：
1. 先生成完整配音（source of truth）
2. BGM 用 `apad=whole_dur=<配音时长+5秒>` 延长
3. 混音用 `duration=first`（以配音为准，不被 BGM 截断）
4. 视频时长 ≥ 音频时长，用 `-shortest` 时以音频为基准

```bash
# 错误（会被截断）
ffmpeg -i voice.mp3 -i bgm_short.mp3 \
  -filter_complex "[0:a][1:a]amix=inputs=2:duration=shortest[aout]" ...

# 正确（完整保留配音）
ffmpeg -y -i voice.mp3 -i bgm_extended.mp3 \
  -filter_complex "[0:a]volume=1.2[voice];[1:a]volume=0.12[bgm];[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]" \
  -map "[aout]" final_mix.mp3
```

### ❌ 教训4：视频时长和音频不匹配

**问题**：
- 视频固定 12 个场景，每个场景 `duration=9.48s`，总计 113.76s
- 音频 118.98s，视频短了 5s
- `-shortest` 以视频为准，配音被截尾

**正确做法**：
1. 以配音时长为基准：`scene_dur = audio_dur / 12`
2. 视频总时长 = 配音时长 + 0.5s（保险量）
3. 合成后用 `ffprobe` 验证输出视频和音频时长是否一致

---

## 各阶段注意事项

### 阶段 1：书籍获取

优先数据源：
1. Project Gutenberg（英文公版书）
2. 书路网（中文书籍）
3. 手动用户提供

`fulltext.txt` 预处理：去除页眉页脚，保留章节结构。

---

### 阶段 2：文案创作

- 优先 glm-5，效果不稳时切换 Claude
- 每篇文案自检：
  - [ ] 开头3句有钩子？
  - [ ] 有3个自然金句？
  - [ ] 结尾给方法了？
  - [ ] 没有违禁词？

---

### 阶段 3：分镜设计

- `image_prompt` 必须是**纯视觉描述**，禁止出现文字
- 格式：`英文，20~50词，modern illustration, warm tones, no text`
- `subtitle` 每条 8 字以内，是配音内容的关键词提炼

---

### 阶段 4：AI 绘图

使用 `image_generate` 工具（MiniMax image-01），prompt 示例：

```
Modern flat illustration of a tired salary worker sitting at desk, surrounded by gold coins but unable to reach them, warm orange lighting, minimalist style, clean composition, no text visible
```

**禁止**：
- 图片中出现文字或数字
- 人物手持写有文字的牌子/书/屏幕
- 图表中有文字标签

**质量检查**：
- 12 张图整体风格一致性
- 无明显变形或错误
- 如有异常，单独重绘该画面

---

### 阶段 5：AI 配音

**必须使用中国节点**：`MINIMAX_API_HOST=https://api.minimaxi.com`

```bash
export MINIMAX_API_KEY="sk-cp-..."
export MINIMAX_API_HOST="https://api.minimaxi.com"

bash scripts/tts/generate_voice.sh tts "$(cat essay_01.txt)" \
  -v female-shaonv --model speech-2.8-hd \
  -o audio/essay_01.mp3
```

**字幕对齐后校验**：
- 总时长与配音时长误差 < 1s
- 每条字幕在合理时间范围内

---

### 阶段 6：背景音乐

**必须 `--instrumental`**，无人声。

班得瑞风格 prompt：
```
Bandari style ambient instrumental, soft flute and piano melodies, nature sounds, peaceful forest atmosphere, gentle and relaxing, no vocals, pure instrumental, soft dynamics
```

**BGM 延长**（关键！）：
```bash
# 如果 BGM < 配音时长，用 apad 延长
AUDIO_DUR=$(ffprobe -v error -show_entries stream=duration \
  -of default=noprint_wrappers=1:nokey=1 voice.mp3)
ffmpeg -y -i bgm.mp3 \
  -filter_complex "[0:a]apad=whole_dur=${AUDIO_DUR}[padded]" \
  -map "[padded]" bgm_extended.mp3
```

---

### 阶段 7：视频合成

**正确的合成顺序**：

```bash
# 1. 确认音频时长（这是基准）
AUDIO_DUR=$(ffprobe -v error -show_entries format=duration \
  -of default=noprint_wrappers=1:nokey=1 audio/final_mix.mp3)
# 例如：118.98s

# 2. 计算场景时长（12个场景）
NUM_SCENES=12
SCENE_DUR=$(python3 -c "print($AUDIO_DUR / $NUM_SCENES + 0.002)")

# 3. 生成场景列表（最后一个场景重复一行）
python3 << EOF
dur = $AUDIO_DUR / 12 + 0.002
for i in range(1, 13):
    d = dur if i < 12 else dur + 1.0
    print(f"file 'scene_{i:02d}.png'\nduration {d:.4f}")
print(f"file 'scene_12.png'")
EOF > scene_list.txt

# 4. 合成视频（时长 >= 音频）
ffmpeg -y -f concat -safe 0 -i scene_list.txt \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,fps=30" \
  -c:v mpeg4 -q:v 5 -pix_fmt yuv420p \
  video_raw.mp4

# 5. 验证视频时长
VIDEO_DUR=$(ffprobe -v error -show_entries stream=duration:stream=codec_type=video \
  -of default=noprint_wrappers=1:nokey=1 video_raw.mp4)
# VIDEO_DUR 必须 >= AUDIO_DUR

# 6. mux（-shortest 以音频为准）
ffmpeg -y -i video_raw.mp4 -i audio/final_mix.mp3 \
  -c:v copy -c:a aac -b:a 128k \
  -shortest \
  final.mp4

# 7. 最终验证
ffprobe -v error -show_entries format=duration \
  -of default=noprint_wrappers=1:nokey=1 final.mp4
# 期望值 ≈ AUDIO_DUR
```

---

## 抖音竖屏适配

如发布到抖音，改为 9:16 竖屏（1080×1920）：

```bash
# 裁剪图片中间部分（16:9 -> 9:16）
mkdir -p images_vert
for f in images/essay_01/scene_*.png; do
  ffmpeg -y -i "$f" \
    -vf "crop=ih*9/16:ih" \
    "images_vert/$(basename $f)"
done

# 竖屏场景列表
# scale=1080:1920，pad 填充

ffmpeg -y -f concat -safe 0 -i scene_list_vert.txt \
  -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,fps=30" \
  -c:v mpeg4 -q:v 5 -pix_fmt yuv420p \
  video_vert_raw.mp4

ffmpeg -y -i video_vert_raw.mp4 -i audio/final_mix.mp3 \
  -c:v copy -c:a aac -b:a 128k -shortest \
  final_vertical.mp4
```

---

## 错误处理

| 阶段 | 常见错误 | 处理方式 |
|------|----------|----------|
| 1.书籍获取 | 书籍不存在/禁止抓取 | 尝试备用源，仍失败则询问用户提供 |
| 2.文案创作 | 模型输出格式异常 | 重新生成，最多3次，仍失败切换模型 |
| 3.分镜设计 | JSON格式错误 | 重新生成，检查 prompt 准确性 |
| 4.AI绘图 | 某张图质量差/有文字 | 单独重绘该画面，修正 prompt |
| 5.TTS | API 超时/Key无效 | 检查 API Key，重试 3 次 |
| 6.音乐 | 风格不符/人声残留 | 重新生成，调整 prompt 加"pure instrumental" |
| 7.视频合成 | 视频音频时长不一致 | 重新计算场景时长，以音频为基准 |
