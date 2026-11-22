#!/usr/bin/env python3
"""
Build a 1080x1920 vertical 10-word English flashcard video for kids (ages 3-8).
Rhythm per word: English x1 -> Repeat pause x1 (with chime & progress bar) -> Chinese x1.
"""

import argparse
import asyncio
import json
import math
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1080
HEIGHT = 1920
FPS = 30

# Kid-friendly flat palette
BG_COLOR = (255, 249, 240)       # Warm cream
CARD_BG = (255, 255, 255)        # Pure white card
CARD_BORDER = (238, 229, 214)    # Soft warm border
HEADER_PILL = (255, 232, 179)    # Soft sunny yellow
TEXT_DARK = (45, 49, 66)         # Deep slate
TEXT_IPA = (79, 109, 122)        # Muted teal-slate
TEXT_ZH = (224, 122, 95)         # Warm coral
ACCENT_LISTEN = (78, 168, 222)   # Friendly sky blue
ACCENT_REPEAT = (82, 183, 136)   # Fresh mint green
ACCENT_MEANING = (244, 162, 97)  # Warm tangerine


def find_font(candidates: List[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def get_fonts():
    latin_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    latin_reg = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    cjk_bold = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    cjk_reg = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    return {
        "topic": find_font(cjk_bold + latin_bold, 42),
        "word": find_font(latin_bold, 110),
        "ipa": find_font(latin_reg, 54),
        "zh": find_font(cjk_bold, 86),
        "pill": find_font(cjk_bold + latin_bold, 38),
        "title": find_font(cjk_bold + latin_bold, 84),
        "subtitle": find_font(cjk_reg + latin_reg, 48),
    }


def generate_chime(wav_path: str, duration: float = 0.35, sample_rate: int = 24000):
    """Generate a gentle two-note chime cue for the repeat-after-me phase."""
    n_samples = int(duration * sample_rate)
    with wave.open(wav_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            t = i / sample_rate
            freq = 660.0 if t < duration * 0.45 else 880.0
            env = math.exp(-6.0 * (t % (duration * 0.45)))
            val = int(0.22 * 32767 * env * math.sin(2 * math.pi * freq * t))
            frames.extend(struct.pack("<h", max(-32767, min(32767, val))))
        wf.writeframes(bytes(frames))


def generate_silence(wav_path: str, duration: float, sample_rate: int = 24000):
    n_samples = int(duration * sample_rate)
    with wave.open(wav_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_samples)


def get_audio_duration(path: str) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        text=True,
    ).strip()
    return float(out)


async def _edge_tts_async(text: str, voice: str, rate: str, out_mp3: str):
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(out_mp3)


def synthesize_tts(
    text: str,
    lang: str,
    out_wav: str,
    engine: str = "edge",
    en_voice: str = "en-US-JennyNeural",
    zh_voice: str = "zh-CN-XiaoxiaoNeural",
):
    tmp_mp3 = out_wav + ".mp3"
    if engine == "edge":
        voice = en_voice if lang == "en" else zh_voice
        rate = "-10%" if lang == "en" else "+0%"
        asyncio.run(_edge_tts_async(text, voice, rate, tmp_mp3))
    elif engine == "openai":
        from openai import OpenAI

        client = OpenAI()
        voice = "nova" if lang == "en" else "shimmer"
        resp = client.audio.speech.create(model="tts-1-hd", voice=voice, input=text)
        resp.stream_to_file(tmp_mp3)
    else:
        raise ValueError(f"Unsupported TTS engine: {engine}")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            tmp_mp3,
            "-ar",
            "24000",
            "-ac",
            "1",
            out_wav,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if os.path.exists(tmp_mp3):
        os.remove(tmp_mp3)


def concat_wavs(wav_list: List[str], out_wav: str):
    list_file = out_wav + ".txt"
    with open(list_file, "w") as f:
        for w in wav_list:
            f.write(f"file '{os.path.abspath(w)}'\n")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_file,
            "-c:a",
            "pcm_s16le",
            out_wav,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.remove(list_file)


def draw_centered_text(draw: ImageDraw.ImageDraw, text: str, y: int, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (WIDTH - tw) // 2
    draw.text((x, y), text, font=font, fill=fill)


def render_title_card(topic: str, topic_zh: str, fonts: dict, out_path: str, is_outro: bool = False):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([90, 480, WIDTH - 90, 1420], radius=56, fill=CARD_BG, outline=CARD_BORDER, width=5)

    if not is_outro:
        draw.rounded_rectangle([320, 560, WIDTH - 320, 640], radius=40, fill=HEADER_PILL)
        draw_centered_text(draw, "10-Word Flashcards", 578, fonts["pill"], TEXT_DARK)
        draw_centered_text(draw, topic, 760, fonts["title"], TEXT_DARK)
        if topic_zh:
            draw_centered_text(draw, topic_zh, 900, fonts["zh"], TEXT_ZH)
        draw_centered_text(draw, "Listen  ·  Repeat  ·  Learn", 1140, fonts["subtitle"], TEXT_IPA)
    else:
        draw_centered_text(draw, "Great Job!", 780, fonts["title"], ACCENT_REPEAT)
        draw_centered_text(draw, "你真棒！学完 10 个单词啦", 940, fonts["subtitle"], TEXT_DARK)

    img.save(out_path)


def render_word_card(
    item: dict,
    index: int,
    total: int,
    phase: str,
    repeat_progress: float,
    fonts: dict,
    out_path: str,
):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Top progress pill
    draw.rounded_rectangle([360, 110, WIDTH - 360, 190], radius=40, fill=HEADER_PILL)
    draw_centered_text(draw, f"Word  {index} / {total}", 128, fonts["pill"], TEXT_DARK)

    # Main illustration card
    card_box = [100, 240, WIDTH - 100, 1120]
    draw.rounded_rectangle(card_box, radius=52, fill=CARD_BG, outline=CARD_BORDER, width=5)

    img_path = item.get("image", "")
    if img_path and os.path.exists(img_path):
        art = Image.open(img_path).convert("RGBA")
        art_size = 760
        art = art.resize((art_size, art_size), Image.Resampling.LANCZOS)
        mask = Image.new("L", (art_size, art_size), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, art_size, art_size], radius=36, fill=255)
        paste_x = (WIDTH - art_size) // 2
        paste_y = 290
        img.paste(art, (paste_x, paste_y), mask)

    # Word, IPA, and Chinese meaning
    draw_centered_text(draw, item["word"], 1180, fonts["word"], TEXT_DARK)
    draw_centered_text(draw, item["phonetic"], 1330, fonts["ipa"], TEXT_IPA)

    zh_color = TEXT_ZH if phase == "meaning" else (180, 175, 168)
    draw_centered_text(draw, item["chinese"], 1440, fonts["zh"], zh_color)

    # Phase indicator pill at bottom
    if phase == "listen":
        pill_color = ACCENT_LISTEN
        label = "Listen  ·  听一听"
    elif phase == "repeat":
        pill_color = ACCENT_REPEAT
        label = "Your Turn  ·  跟读一遍"
    else:
        pill_color = ACCENT_MEANING
        label = "Meaning  ·  中文释义"

    draw.rounded_rectangle([220, 1620, WIDTH - 220, 1720], radius=50, fill=pill_color)
    draw_centered_text(draw, label, 1648, fonts["pill"], (255, 255, 255))

    # Repeat progress bar
    if phase == "repeat":
        bar_x1, bar_x2 = 220, WIDTH - 220
        bar_y1, bar_y2 = 1760, 1784
        draw.rounded_rectangle([bar_x1, bar_y1, bar_x2, bar_y2], radius=12, fill=(225, 235, 228))
        fill_w = max(24, int((bar_x2 - bar_x1) * max(0.0, min(1.0, repeat_progress))))
        draw.rounded_rectangle([bar_x1, bar_y1, bar_x1 + fill_w, bar_y2], radius=12, fill=ACCENT_REPEAT)

    img.save(out_path)


def make_still_segment(image_path: str, audio_path: str, out_mp4: str, duration: float):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            image_path,
            "-i",
            audio_path,
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            "-s",
            f"{WIDTH}x{HEIGHT}",
            "-c:a",
            "aac",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-shortest",
            out_mp4,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def make_repeat_segment(
    item: dict,
    index: int,
    total: int,
    audio_path: str,
    duration: float,
    fonts: dict,
    work_dir: str,
    out_mp4: str,
):
    steps = max(1, int(duration * 10))  # 10 fps animation for smooth progress bar
    frames_dir = os.path.join(work_dir, f"repeat_frames_{index}")
    os.makedirs(frames_dir, exist_ok=True)
    for s in range(steps):
        prog = 1.0 - (s / max(1, steps - 1))
        frame_path = os.path.join(frames_dir, f"frame_{s:04d}.png")
        render_word_card(item, index, total, "repeat", prog, fonts, frame_path)

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            "10",
            "-i",
            os.path.join(frames_dir, "frame_%04d.png"),
            "-i",
            audio_path,
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            "-s",
            f"{WIDTH}x{HEIGHT}",
            "-c:a",
            "aac",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-shortest",
            out_mp4,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def build_video(
    input_json: str,
    output_mp4: str,
    tts_engine: str,
    repeat_seconds: float,
    en_voice: str,
    zh_voice: str,
):
    with open(input_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    topic = data.get("topic", "Vocabulary")
    topic_zh = data.get("topic_zh", "")
    words = data["words"]
    total = len(words)
    fonts = get_fonts()

    work_dir = tempfile.mkdtemp(prefix="flashcard_build_")
    segments: List[str] = []

    try:
        # 1. Intro card
        intro_img = os.path.join(work_dir, "intro.png")
        intro_wav = os.path.join(work_dir, "intro.wav")
        intro_mp4 = os.path.join(work_dir, "seg_000_intro.mp4")
        render_title_card(topic, topic_zh, fonts, intro_img, is_outro=False)
        synthesize_tts(f"Today's topic: {topic}.", "en", intro_wav, tts_engine, en_voice, zh_voice)
        intro_dur = get_audio_duration(intro_wav) + 0.5
        intro_pad = os.path.join(work_dir, "intro_pad.wav")
        sil_05 = os.path.join(work_dir, "sil_05.wav")
        generate_silence(sil_05, 0.5)
        concat_wavs([intro_wav, sil_05], intro_pad)
        make_still_segment(intro_img, intro_pad, intro_mp4, intro_dur)
        segments.append(intro_mp4)

        chime_wav = os.path.join(work_dir, "chime.wav")
        generate_chime(chime_wav)
        chime_dur = get_audio_duration(chime_wav)

        # 2. Word cards
        for idx, item in enumerate(words, start=1):
            # Phase 1: Listen (English x1)
            en_wav = os.path.join(work_dir, f"w{idx}_en.wav")
            en_pad_wav = os.path.join(work_dir, f"w{idx}_en_pad.wav")
            synthesize_tts(item["word"], "en", en_wav, tts_engine, en_voice, zh_voice)
            concat_wavs([en_wav, sil_05], en_pad_wav)
            en_dur = get_audio_duration(en_pad_wav)

            img_listen = os.path.join(work_dir, f"w{idx}_listen.png")
            render_word_card(item, idx, total, "listen", 1.0, fonts, img_listen)
            seg_listen = os.path.join(work_dir, f"seg_{idx:03d}_1_listen.mp4")
            make_still_segment(img_listen, en_pad_wav, seg_listen, en_dur)
            segments.append(seg_listen)

            # Phase 2: Repeat (chime + pause)
            rep_sil_wav = os.path.join(work_dir, f"w{idx}_rep_sil.wav")
            rep_wav = os.path.join(work_dir, f"w{idx}_rep.wav")
            generate_silence(rep_sil_wav, max(0.5, repeat_seconds - chime_dur))
            concat_wavs([chime_wav, rep_sil_wav], rep_wav)
            rep_dur = get_audio_duration(rep_wav)

            seg_repeat = os.path.join(work_dir, f"seg_{idx:03d}_2_repeat.mp4")
            make_repeat_segment(item, idx, total, rep_wav, rep_dur, fonts, work_dir, seg_repeat)
            segments.append(seg_repeat)

            # Phase 3: Meaning (Chinese x1)
            zh_wav = os.path.join(work_dir, f"w{idx}_zh.wav")
            zh_pad_wav = os.path.join(work_dir, f"w{idx}_zh_pad.wav")
            synthesize_tts(item["chinese"], "zh", zh_wav, tts_engine, en_voice, zh_voice)
            concat_wavs([zh_wav, sil_05], zh_pad_wav)
            zh_dur = get_audio_duration(zh_pad_wav)

            img_meaning = os.path.join(work_dir, f"w{idx}_meaning.png")
            render_word_card(item, idx, total, "meaning", 0.0, fonts, img_meaning)
            seg_meaning = os.path.join(work_dir, f"seg_{idx:03d}_3_meaning.mp4")
            make_still_segment(img_meaning, zh_pad_wav, seg_meaning, zh_dur)
            segments.append(seg_meaning)

        # 3. Outro card
        outro_img = os.path.join(work_dir, "outro.png")
        outro_wav = os.path.join(work_dir, "outro.wav")
        outro_pad = os.path.join(work_dir, "outro_pad.wav")
        outro_mp4 = os.path.join(work_dir, "seg_999_outro.mp4")
        render_title_card(topic, topic_zh, fonts, outro_img, is_outro=True)
        synthesize_tts("Great job!", "en", outro_wav, tts_engine, en_voice, zh_voice)
        concat_wavs([outro_wav, sil_05], outro_pad)
        outro_dur = get_audio_duration(outro_pad)
        make_still_segment(outro_img, outro_pad, outro_mp4, outro_dur)
        segments.append(outro_mp4)

        # 4. Concatenate all segments
        concat_list = os.path.join(work_dir, "segments.txt")
        with open(concat_list, "w") as f:
            for seg in segments:
                f.write(f"file '{os.path.abspath(seg)}'\n")

        os.makedirs(os.path.dirname(os.path.abspath(output_mp4)), exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_list,
                "-c",
                "copy",
                output_mp4,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"Created 1080x1920 flashcard video: {output_mp4}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Build a 1080x1920 kids flashcard video.")
    parser.add_argument("--input", required=True, help="Path to words.json")
    parser.add_argument("--output", required=True, help="Output MP4 file path")
    parser.add_argument("--tts", default="edge", choices=["edge", "openai"], help="TTS engine")
    parser.add_argument("--repeat-seconds", type=float, default=2.5, help="Repeat pause duration in seconds")
    parser.add_argument("--en-voice", default="en-US-JennyNeural", help="Edge-TTS English voice")
    parser.add_argument("--zh-voice", default="zh-CN-XiaoxiaoNeural", help="Edge-TTS Chinese voice")
    args = parser.parse_args()

    build_video(
        input_json=args.input,
        output_mp4=args.output,
        tts_engine=args.tts,
        repeat_seconds=args.repeat_seconds,
        en_voice=args.en_voice,
        zh_voice=args.zh_voice,
    )


if __name__ == "__main__":
    main()
