---
name: book-to-video-pipeline
description: AI 视频自动化生产流水线。根据书名自动完成从书籍获取、文案创作、分镜设计、AI绘图、AI配音、背景音乐生成到最终视频合成的全部 7 个阶段，输出 MP4 视频。当用户提到"视频流水线"、"从书生成视频"、"自动化视频生产"、"book to video"或需要将一本书自动制成短视频时使用此 skill。
---

# Book-to-Video Pipeline

将一本书转换为一支完整短视频的自动化流水线。

## ⚠️ 视频生产关键规范（必读）

以下规范在首次实践中总结，容易踩坑，必须严格遵守：

1. **视频默认 16:9 横屏（1920×1080）**
   - 输出分辨率为 1920×1080（16:9），适配 YouTube/Bilibili 等横屏平台
   - 如需发抖音（竖屏 9:16），用流水线中单独的竖屏处理步骤

2. **图片中禁止出现任何文字**
   - AI 绘图的提示词中绝对不要包含文字描述
   - 画面应该是纯视觉表达，人物、场景、概念图均可
   - 文字全部在字幕层处理，不烧入图片

3. **背景音乐规范**
   - 必须为纯器乐无人声（选 `--instrumental` 模式）
   - 风格推荐班得瑞（Bandari）风格：轻柔、自然、器乐为主
   - BGM 音量必须低于配音：建议配音 100%，BGM 12-15%
   - BGM 时长必须覆盖完整配音，遇到不够长的情况用 `apad` 滤镜延长

4. **视频时长必须匹配音频**
   - **音频是基准**，视频时长必须 ≥ 音频时长
   - 合成时用 `-shortest` 让视频跟随音频长度
   - 场景数量固定 12 个，时长 = 音频总长 / 12
   - 注意：`amix` 的 `duration=shortest` 会按最短音频截断，混音时用 `duration=first` 以配音时长为准

5. **MiniMax API Key 配置**
   - TTS/Music/Image 均使用 MiniMax API
   - API Host：中国节点 `https://api.minimaxi.com`，不是 global
   - Key 格式：`sk-cp-...`

## 流水线概览（7 个阶段）

| 阶段 | 名称 | 实现方式 | 输入 | 输出 |
|------|------|----------|------|------|
| 1 | 书籍获取 | `scripts/fetch_book.py` | 书名 | `fulltext.txt` + `book-meta.json` |
| 2 | 文案创作 | 大模型 + `references/copywriter-system.md` | 书籍全文 | `essay_01~03.txt` |
| 3 | 分镜设计 | 大模型 + `references/storyboard-system.md` | 文案 | `storyboard.json` |
| 4 | AI 绘图 | `image_generate` 工具（batch） | 分镜提示词 | 每篇 12 张 PNG（**无文字**） |
| 5 | AI 配音 | MiniMax TTS | 文案文本 | MP3 + 字幕 JSON |
| 6 | 背景音乐 | MiniMax Music（`--instrumental`） | 风格描述 | BGM MP3（**纯器乐**） |
| 7 | 视频合成 | ffmpeg | 所有素材 | `final.mp4` |

## 快速启动

用户只需提供：**书名** + **音乐风格描述**

```
书名: "穷爸爸富爸爸"
音乐风格: "班得瑞风格，钢琴为主，舒缓轻音乐，无人声"
```

## 完整执行流程

### 阶段 1：书籍获取

```bash
python scripts/fetch_book.py "书名"
```

输出：`fulltext.txt`（书籍全文）+ `book-meta.json`（元数据）

---

### 阶段 2：文案创作

使用 glm-5 模型，读取 `references/copywriter-system.md`。

生成 3 篇不同角度的短视频文案，每篇：
- 强钩子开头（前3句抓眼球）
- 1句话1段落，段落留空行
- 3个金句（黑体）
- 给方法的结尾

输出：`essay_01.txt`、`essay_02.txt`、`essay_03.txt`

---

### 阶段 3：分镜设计

使用 glm-5 模型，读取 `references/storyboard-system.md`。

生成 JSON 格式分镜脚本，每篇 12 个场景，包含：
- 画面描述（**禁止含文字**，纯视觉描述）
- 配音摘句
- 字幕内容（8字以内）

输出：`storyboard_01.json` ~ `storyboard_03.json`

---

### 阶段 4：AI 绘图（图片禁止含文字）

**使用 `image_generate` 工具生成图片，prompt 必须是纯视觉描述。**

示例 prompt（正确）：
> "Modern flat illustration of a tired salary worker sitting at desk, surrounded by gold coins but unable to reach them, warm orange lighting, minimalist style, clean composition"

示例 prompt（错误，含文字）：
> ❌ "A person reading a book with text '富爸爸' on the cover"

每篇生成 12 张，保存到 `images/essay_XX/scene_01.png` ~ `scene_12.png`

---

### 阶段 5：AI 配音（MiniMax TTS）

```bash
export MINIMAX_API_KEY="sk-cp-..."
export MINIMAX_API_HOST="https://api.minimaxi.com"

# 单段 TTS 生成
bash scripts/tts/generate_voice.sh tts "$(cat essay_01.txt)" \
  -v female-shaonv --model speech-2.8-hd \
  -o audio/essay_01.mp3
```

输出：`audio/essay_01.mp3` + `audio/essay_01_subtitles.json`

---

### 阶段 6：背景音乐（纯器乐、低音量）

```bash
# 生成班得瑞风格纯器乐 BGM
bash scripts/music/generate_music.sh \
  --instrumental \
  --prompt "Bandari style ambient instrumental, soft flute and piano melodies, nature sounds, peaceful atmosphere, gentle and relaxing, pure instrumental no vocals" \
  --output bgm_raw.mp3 --download
```

**BGM 必须延长到覆盖配音时长（配音是 source of truth）：**

```bash
# 配音 ~120s，BGM ~40s，需要延长
ffmpeg -y -i bgm_raw.mp3 \
  -filter_complex "[0:a]apad=whole_dur=125[padded]" \
  -map "[padded]" bgm_extended.mp3
```

**BGM 音量压到配音的 12%：**

```bash
ffmpeg -y -i audio/essay_01.mp3 -i bgm_extended.mp3 \
  -filter_complex "[0:a]volume=1.2[voice];[1:a]volume=0.12[bgm];[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]" \
  -map "[aout]" audio/final_mix.mp3
```

> 注意：`duration=first` 确保以配音为准，不会被 BGM 时长截断

---

### 阶段 7：视频合成

**步骤 A：计算每场景时长**
```python
# 音频总长 / 12 场景
audio_dur = 118.98  # 秒
num_scenes = 12
scene_dur = audio_dur / num_scenes  # 每场景约 9.9 秒
```

**步骤 B：生成 ffmpeg concat 场景列表**

每行格式：
```
file 'images/essay_01/scene_XX.png'
duration 9.92
```

最后一个场景重复一行（concat demuxer 要求）。

**步骤 C：合成视频 + 音频**

```bash
# 先合成视频（时长 >= 音频）
ffmpeg -y -f concat -safe 0 -i scene_list.txt \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,fps=30" \
  -c:v mpeg4 -q:v 5 -pix_fmt yuv420p \
  video_raw.mp4

# 再 mux 音频（-shortest 以音频为准，视频不够长会自动截断，这里确保视频 >= 音频）
ffmpeg -y -i video_raw.mp4 -i audio/final_mix.mp3 \
  -c:v copy -c:a aac -b:a 128k \
  -shortest \
  final_essay_01.mp4
```

---

## 抖音竖屏版本（9:16）

如需发抖音，生成 9:16 竖屏版本：

```bash
# 先生成竖屏图片（裁剪中间部分）
for img in images/essay_01/scene_*.png; do
  ffmpeg -y -i "$img" -vf "crop=ih*9/16:ih" "${img%.png}_vert.png"
done

# 用竖屏图片列表合成
ffmpeg -y -f concat -safe 0 -i scene_list_vertical.txt \
  -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,fps=30" \
  -c:v mpeg4 -q:v 5 -pix_fmt yuv420p \
  video_vertical_raw.mp4

ffmpeg -y -i video_vertical_raw.mp4 -i audio/final_mix.mp3 \
  -c:v copy -c:a aac -b:a 128k -shortest \
  final_essay_01_vertical.mp4
```

---

## 目录结构

```
output/<书名>/
├── book-meta.json
├── fulltext.txt
├── essay_01.txt / essay_02.txt / essay_03.txt
├── storyboard_01.json / 02.json / 03.json
├── images/essay_01/scene_01~12.png（12张，**无文字**）
├── audio/
│   ├── essay_01.mp3 + _subtitles.json
│   ├── essay_02.mp3 + _subtitles.json
│   └── essay_03.mp3 + _subtitles.json
├── bgm_raw.mp3
├── bgm_extended.mp3（BGM 延长后）
├── final_mix.mp3（配音+BGM混音）
└── final_essay_01.mp4
```

## 关键参考文件

- **文案系统提示词**：`references/copywriter-system.md`
- **分镜系统提示词**：`references/storyboard-system.md`
- **流水线详细指南**：`references/pipeline-guide.md`

## 错误处理

- 某阶段失败时，从该阶段重试，不要从头开始
- 书籍获取失败：尝试备用书源，或询问用户是否手动提供 txt
- TTS 失败：检查 API Key 和网络，重试 3 次
- 视频合成失败：检查 ffmpeg、素材是否完整、时长是否对齐
