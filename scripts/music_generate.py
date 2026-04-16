#!/usr/bin/env python3
"""
背景音乐生成脚本
使用 MiniMax Music 生成背景音乐，输出 MP3
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# MiniMax Music API 配置
MINIMAX_MUSIC_URL = "https://api.minimax.chat/v1/music_generation"
# 需要配置 API Key
MINIMAX_API_KEY = None  # 请设置: os.environ.get("MINIMAX_API_KEY") 或直接填写


def call_minimax_music(style: str, duration: int = 60) -> bytes:
    """
    调用 MiniMax Music API
    style: 音乐风格描述
    duration: 时长（秒），默认 60 秒
    """
    global MINIMAX_API_KEY
    
    if MINIMAX_API_KEY is None:
        try:
            import os
            MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY")
        except Exception:
            pass
    
    if not MINIMAX_API_KEY:
        print("[Music] 警告: 未配置 MINIMAX_API_KEY，将生成占位文件")
        return b""
    
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "music-01",
        "prompt": style,
        "duration": duration,
        "output_format": "mp3"
    }
    
    import requests
    response = requests.post(MINIMAX_MUSIC_URL, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    return response.content


def music_generate(style: str, output_file: Path, duration: int = 60) -> bool:
    """
    主函数：生成背景音乐
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"[Music] 正在生成背景音乐...")
    print(f"[Music] 风格: {style}")
    print(f"[Music] 时长: {duration}s")
    
    try:
        audio_data = call_minimax_music(style, duration)
        if audio_data:
            output_file.write_bytes(audio_data)
            print(f"[Music] 背景音乐已保存: {output_file}")
        else:
            # 创建占位文件
            output_file.write_bytes(b"")
            print(f"[Music] 占位文件已创建: {output_file}（请配置 MINIMAX_API_KEY 生成真实音乐）")
    except Exception as e:
        print(f"[Music] 错误: {e}")
        # 创建占位文件
        output_file.write_bytes(b"")
        print(f"[Music] 占位文件已创建: {output_file}")
        return False
    
    return True


def main():
    parser = argparse.ArgumentParser(description="使用 MiniMax Music 生成背景音乐")
    parser.add_argument("style", help="音乐风格描述（如：轻快、励志、钢琴为主）")
    parser.add_argument("--output", "-o", type=Path, default="output/bgm.mp3", help="输出文件路径")
    parser.add_argument("--duration", type=int, default=60, help="音乐时长（秒）")
    args = parser.parse_args()
    
    success = music_generate(args.style, args.output, args.duration)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
