#!/usr/bin/env python3
"""
AI 配音脚本
使用 MiniMax TTS 将文案文本转换为语音，输出 MP3 + 字幕 JSON
"""

import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime

# MiniMax TTS API 配置
MINIMAX_TTS_URL = "https://api.minimax.chat/v1/t2a_v2"
# 需要配置 API Key（建议写入环境变量或配置文件）
MINIMAX_API_KEY = None  # 请设置: os.environ.get("MINIMAX_API_KEY") 或直接填写


def split_text_into_sentences(text: str) -> list:
    """将文本分割成句子，用于字幕时间轴对齐"""
    # 按常见句末标点分割
    sentences = re.split(r'([。！？.!?])', text)
    result = []
    current = ""
    for i, part in enumerate(sentences):
        if i % 2 == 0:  # 文本内容
            current += part
        else:  # 标点
            current += part
            if current.strip():
                result.append(current.strip())
            current = ""
    if current.strip():
        result.append(current.strip())
    return result


def estimate_duration(text: str, speed: float = 1.0) -> float:
    """估算语音时长（秒），中文约 4-5 字/秒"""
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    other_chars = len(re.findall(r'[a-zA-Z0-9]', text))
    total_chars = chinese_chars + other_chars
    # 中文 4.5 字/秒，英文酌情
    base_duration = total_chars / 4.5
    return base_duration / speed


def generate_subtitles(text: str, speed: float = 1.0) -> list:
    """生成字幕时间轴"""
    sentences = split_text_into_sentences(text)
    subtitles = []
    current_time = 0.0
    
    for i, sentence in enumerate(sentences):
        duration = estimate_duration(sentence, speed)
        subtitles.append({
            "id": i + 1,
            "start": round(current_time, 2),
            "end": round(current_time + duration, 2),
            "text": sentence
        })
        current_time += duration + 0.1  # 句子间加入 0.1s 间隙
    
    return subtitles


def call_minimax_tts(text: str, voice_id: str = "zh-CN-XiaoxiaoNeural", speed: float = 1.0) -> bytes:
    """
    调用 MiniMax TTS API
    voice_id: 语音选择，默认中文女声
    speed: 语速，1.0 为正常速度
    """
    global MINIMAX_API_KEY
    
    if MINIMAX_API_KEY is None:
        try:
            import os
            MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY")
        except Exception:
            pass
    
    if not MINIMAX_API_KEY:
        print("[TTS] 警告: 未配置 MINIMAX_API_KEY，将生成占位音频")
        return b""  # 返回空字节流，实际使用时替换为真实 API 调用
    
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "speech-02-hd",
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": speed,
            "pitch": 0,
            "volume": 0
        },
        "output_format": "mp3"
    }
    
    import requests
    response = requests.post(MINIMAX_TTS_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.content


def tts_generate(input_file: Path, output_dir: Path, voice: str = "zh-CN-XiaoxiaoNeural", speed: float = 1.0) -> bool:
    """
    主函数：生成 TTS 音频和字幕
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 读取文案
    text = input_file.read_text(encoding="utf-8").strip()
    if not text:
        print(f"[TTS] 错误: 输入文件 {input_file} 为空")
        return False
    
    print(f"[TTS] 读取文案: {input_file.name}，字符数: {len(text)}")
    
    # 生成字幕时间轴
    subtitles = generate_subtitles(text, speed)
    total_duration = subtitles[-1]["end"] if subtitles else 0
    print(f"[TTS] 生成 {len(subtitles)} 条字幕，预计时长: {total_duration:.1f}s")
    
    # 调用 TTS API（如果已配置）
    try:
        audio_data = call_minimax_tts(text, voice, speed)
        if audio_data:
            mp3_file = output_dir / f"{input_file.stem}.mp3"
            mp3_file.write_bytes(audio_data)
            print(f"[TTS] 音频已保存: {mp3_file}")
        else:
            # 创建占位文件（仅用于测试流程）
            mp3_file = output_dir / f"{input_file.stem}.mp3"
            mp3_file.write_bytes(b"")
            print(f"[TTS] 占位音频已创建: {mp3_file}（请配置 MINIMAX_API_KEY 生成真实音频）")
    except Exception as e:
        print(f"[TTS] 警告: TTS API 调用失败: {e}，创建占位文件")
        mp3_file = output_dir / f"{input_file.stem}.mp3"
        mp3_file.write_bytes(b"")
    
    # 保存字幕 JSON
    subtitle_file = output_dir / f"{input_file.stem}_subtitles.json"
    with subtitle_file.open("w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "total_duration": total_duration,
            "voice": voice,
            "speed": speed,
            "subtitles": subtitles
        }, f, ensure_ascii=False, indent=2)
    
    print(f"[TTS] 字幕已保存: {subtitle_file}")
    return True


def main():
    parser = argparse.ArgumentParser(description="使用 MiniMax TTS 生成配音")
    parser.add_argument("input_file", type=Path, help="输入文案文件 (.txt)")
    parser.add_argument("--output", "-o", type=Path, default="output/audio", help="输出目录")
    parser.add_argument("--voice", default="zh-CN-XiaoxiaoNeural", help="语音 ID")
    parser.add_argument("--speed", type=float, default=1.0, help="语速 (默认 1.0)")
    args = parser.parse_args()
    
    if not args.input_file.exists():
        print(f"[TTS] 错误: 输入文件不存在: {args.input_file}")
        sys.exit(1)
    
    success = tts_generate(args.input_file, args.output, args.voice, args.speed)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
