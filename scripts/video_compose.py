#!/usr/bin/env python3
"""
视频合成脚本
使用 ffmpeg + Pillow 将图片、配音、字幕、背景音乐合成为最终 MP4 视频
"""

import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime

# 检查 ffmpeg 是否安装
def check_ffmpeg():
    import subprocess
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def load_subtitles(subtitle_json: Path) -> list:
    """加载字幕时间轴"""
    if not subtitle_json.exists():
        print(f"[Video] 警告: 字幕文件不存在: {subtitle_json}")
        return []
    with subtitle_json.open(encoding="utf-8") as f:
        data = json.load(f)
    return data.get("subtitles", [])


def calculate_scene_duration(subtitle: dict, total_scenes: int, total_duration: float) -> float:
    """
    根据字幕时间计算每个场景的显示时长
    简化版本：平均分配
    """
    if total_scenes <= 0:
        return 5.0
    return total_duration / total_scenes


def render_subtitle_with_pillow(text: str, image_path: Path, output_path: Path, font_size: int = 48) -> bool:
    """
    使用 Pillow 在图片上渲染字幕
    text: 字幕文本
    image_path: 源图片
    output_path: 输出图片（含字幕）
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        img = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        
        # 尝试加载字体（使用默认字体，Linux 下需要指定字体路径）
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
        
        # 计算字幕位置（底部居中，留边距）
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        img_width, img_height = img.size
        
        x = (img_width - text_width) // 2
        y = img_height - text_height - 40  # 底部留 40px
        
        # 绘制半透明背景
        bg_padding = 10
        bg_box = [
            x - bg_padding, y - bg_padding,
            x + text_width + bg_padding, y + text_height + bg_padding
        ]
        draw.rectangle(bg_box, fill=(0, 0, 0, 160))  # 半透明黑色背景
        
        # 绘制文字（白色）
        draw.text((x, y), text, fill=(255, 255, 255), font=font)
        
        img.save(output_path, "PNG")
        return True
    except Exception as e:
        print(f"[Video] Pillow 渲染字幕失败: {e}")
        # 如果渲染失败，复制原图
        import shutil
        shutil.copy(image_path, output_path)
        return False


def compose_video(essay_id: str, output_dir: Path, images_dir: Path, audio_file: Path, subtitle_file: Path, bgm_file: Path, fps: int = 30) -> bool:
    """
    主函数：合成视频
    """
    import subprocess
    import shutil
    import os
    
    if not check_ffmpeg():
        print("[Video] 错误: ffmpeg 未安装或不可用，请先安装: sudo apt install ffmpeg")
        return False
    
    work_dir = output_dir / "temp"
    work_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[Video] 开始合成视频...")
    print(f"[Video] 音频: {audio_file}")
    print(f"[Video] 字幕: {subtitle_file}")
    print(f"[Video] BGM: {bgm_file}")
    print(f"[Video] 图片目录: {images_dir}")
    
    # 1. 加载字幕
    subtitles = load_subtitles(subtitle_file)
    total_duration = subtitles[-1]["end"] if subtitles else 60
    total_scenes = len(list(images_dir.glob("*.png")))
    
    if total_scenes == 0:
        print(f"[Video] 错误: 找不到图片文件: {images_dir}/*.png")
        return False
    
    print(f"[Video] 共 {total_scenes} 个场景，预计时长 {total_duration:.1f}s")
    
    # 2. 为每个场景生成带字幕的图片
    print("[Video] 渲染字幕到图片...")
    rendered_dir = work_dir / "rendered"
    rendered_dir.mkdir(exist_ok=True)
    
    scene_images = sorted(images_dir.glob("scene_*.png"))
    for i, img_path in enumerate(scene_images):
        subtitle_text = ""
        if i < len(subtitles):
            subtitle_text = subtitles[i].get("text", "")[:20]  # 截取前20字
        output_path = rendered_dir / f"scene_{i+1:02d}_subtitled.png"
        render_subtitle_with_pillow(subtitle_text, img_path, output_path)
    
    print(f"[Video] 字幕渲染完成: {rendered_dir}")
    
    # 3. 确定视频总时长（使用音频时长）
    if audio_file.exists():
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", 
             "-of", "default=noprint_wrappers=1:nokey=1", str(audio_file)],
            capture_output=True, text=True
        )
        try:
            video_duration = float(probe.stdout.strip())
            print(f"[Video] 音频时长: {video_duration:.1f}s")
        except ValueError:
            video_duration = total_duration
    
    # 4. 合成视频（图片序列 -> 视频片段）
    scene_list_file = work_dir / "scene_list.txt"
    with scene_list_file.open("w") as f:
        for i in range(1, total_scenes + 1):
            scene_duration = video_duration / total_scenes if total_scenes > 0 else 5
            img_file = rendered_dir / f"scene_{i:02d}_subtitled.png"
            f.write(f"file '{img_file.absolute()}'\n")
            f.write(f"duration {scene_duration:.2f}\n")
        # 最后一帧延长
        last_img = rendered_dir / f"scene_{total_scenes:02d}_subtitled.png"
        f.write(f"file '{last_img.absolute()}'\n")
    
    # 5. 使用 ffmpeg concat 生成视频
    video_only = work_dir / "video_only.mp4"
    
    concat_cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(scene_list_file),
        "-vf", f"scale=1920:1080:force_original_aspect_ratio=decrease,"
               f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
               f"fps={fps}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p",
        str(video_only)
    ]
    
    print(f"[Video] 执行: {' '.join(concat_cmd[:5])}...")
    result = subprocess.run(concat_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[Video] 错误: ffmpeg 执行失败:\n{result.stderr}")
        return False
    
    # 6. 混合音频（旁白 + BGM）
    final_video = output_dir / f"final_essay_{essay_id}.mp4"
    
    audio_args = []
    if audio_file.exists() and bgm_file.exists():
        # 混合旁白和 BGM
        mix_cmd = [
            "ffmpeg", "-y",
            "-i", str(video_only),
            "-i", str(audio_file),
            "-i", str(bgm_file),
            "-filter_complex",
            "[1:a][2:a]amix=inputs=2:duration=shortest:dropout_transition=2[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
            str(final_video)
        ]
    elif audio_file.exists():
        mix_cmd = [
            "ffmpeg", "-y",
            "-i", str(video_only),
            "-i", str(audio_file),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac",
            str(final_video)
        ]
    else:
        # 无音频，直接复制
        shutil.copy(video_only, final_video)
        print(f"[Video] 视频已生成（无音频）: {final_video}")
        return True
    
    print(f"[Video] 混合音频...")
    result = subprocess.run(mix_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[Video] 警告: 音频混合失败:\n{result.stderr}")
        shutil.copy(video_only, final_video)
    
    print(f"[Video] 视频合成完成: {final_video}")
    
    # 7. 清理临时文件
    shutil.rmtree(work_dir, ignore_errors=True)
    
    return True


def main():
    if not check_ffmpeg():
        print("[Video] 错误: ffmpeg 未安装")
        print("请安装 ffmpeg:")
        print("  Ubuntu/Debian: sudo apt install ffmpeg")
        print("  macOS: brew install ffmpeg")
        sys.exit(1)
    
    parser = argparse.ArgumentParser(description="合成视频（图片+配音+字幕+背景音乐）")
    parser.add_argument("essay_id", help="文案编号（如: 01）")
    parser.add_argument("--output", "-o", type=Path, default="output", help="输出根目录")
    parser.add_argument("--images", type=Path, help="图片目录（默认: output/images/essay_XX）")
    parser.add_argument("--audio", type=Path, help="配音文件（默认: output/audio/essay_XX.mp3）")
    parser.add_argument("--subtitles", type=Path, help="字幕JSON（默认: output/audio/essay_XX_subtitles.json）")
    parser.add_argument("--bgm", type=Path, default=None, help="背景音乐文件（默认: output/bgm.mp3）")
    parser.add_argument("--fps", type=int, default=30, help="帧率（默认: 30）")
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    essay_id = args.essay_id
    
    # 自动推断路径
    images_dir = args.images or output_dir / "images" / f"essay_{essay_id}"
    audio_file = args.audio or output_dir / "audio" / f"essay_{essay_id}.mp3"
    subtitle_file = args.subtitles or output_dir / "audio" / f"essay_{essay_id}_subtitles.json"
    bgm_file = args.bgm or output_dir / "bgm.mp3"
    
    success = compose_video(
        essay_id, output_dir, images_dir,
        audio_file, subtitle_file, bgm_file, args.fps
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
