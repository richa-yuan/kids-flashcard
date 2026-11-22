---
name: kids-flashcard-video
description: Generate a 1080x1920 vertical 10-word English flashcard learning video for children aged 3-8 given any topic. Creates child-friendly flat-style illustrations, IPA phonetics, Chinese meanings, and human-like voiceover in a listen-repeat-Chinese rhythm. Use whenever the user asks for a kids vocabulary video, 10-word flashcard video, 单词卡视频, 儿童英语启蒙视频, or vertical word learning video.
---

# Kids Flashcard Video

Generate a 1080x1920 vertical (9:16) English vocabulary flashcard video for children aged 3-8 from a single topic. Each video covers 10 topic-related words with flat-style illustrations, IPA phonetics, Chinese meanings, and natural human-like voiceover following a 3-step rhythm per word: English pronunciation, repeat-after-me pause, and Chinese meaning.

## When to Use

- User provides a theme or topic (e.g., animals, fruits, vehicles, colors, daily routines) and asks for a 10-word flashcard video.

- User asks for a kids English learning video, 单词卡视频, or 英语启蒙短视频 with pronunciation, repeat-after-me pauses, and Chinese meanings.

- User requests a 1080x1920 vertical vocabulary video with flat-style illustrations and IPA phonetics.

## Environment Requirements

The bundled video builder script (`scripts/build_flashcard_video.py`) requires outbound network access to synthesize natural human-like speech via `edge-tts` (default, no API key required) or `openai` TTS (optional, requires `OPENAI_API_KEY`).

- Required system binary: `ffmpeg`

- Required Python packages: `pillow`, `edge-tts` (or `openai` if using OpenAI TTS)

- If running in a sandbox without internet access or TTS packages, generate the 10-word JSON, flat-style illustrations, and visual frames first, then inform the user to run `scripts/build_flashcard_video.py` in their local environment (or provide their own voiceover audio).

## Workflow

### Step 1: Curate 10 Age-Appropriate Words (Ages 3-8)

Select 10 concrete, high-frequency, visually depictable English words matching the user's topic. For each word, prepare:

- `word`: Simple English word in title or lowercase appropriate for kids (e.g., `Apple`, `Elephant`).

- `phonetic`: Accurate IPA phonetic transcription (e.g., `/ˈæp.əl/`).

- `chinese`: Concise, natural Chinese meaning for children (e.g., `苹果`).

- `image_prompt`: A flat-style children's book illustration prompt for that single object on a clean white or soft pastel background.

### Step 2: Generate Flat-Style Illustrations

Generate 10 square (1:1) illustrations using image generation with a consistent flat vector / picture-book style suitable for ages 3-8:

- Style keywords: `flat vector illustration for children, cute simple shapes, warm pastel colors, clean white background, picture book style, no text, no letters, no watermark`.

- Save images to a working folder (e.g., `assets/word_01.png` through `assets/word_10.png`).

### Step 3: Write `words.json`

Create a `words.json` manifest in the working directory:

```json
{
  "topic": "Fruits",
  "topic_zh": "水果",
  "words": [
    {
      "word": "Apple",
      "phonetic": "/ˈæp.əl/",
      "chinese": "苹果",
      "image": "assets/word_01.png"
    }
  ]
}
```

### Step 4: Synthesize Audio and Render 1080x1920 Video

Run the bundled script to synthesize natural voiceover (`英文一遍 -> 跟读一遍 -> 中文一遍`) and render the 1080x1920 MP4 video:

```bash
python3 scripts/build_flashcard_video.py \
  --input words.json \
  --output flashcard_video.mp4 \
  --tts edge \
  --repeat-seconds 2.5
```

Audio and visual pacing per word card:

1. **Listen (英文一遍)**: Plays warm, clear English pronunciation (`en-US-JennyNeural` at `-10%` rate) with a blue "Listen · 听一听" indicator.

2. **Repeat (跟读一遍)**: Plays a gentle chime followed by a 2.5-second pause with an animated countdown bar and green "Your Turn · 跟读一遍" indicator.

3. **Meaning (中文一遍)**: Plays warm Mandarin pronunciation (`zh-CN-XiaoxiaoNeural`) with a coral "Meaning · 中文" indicator highlighting the Chinese word.

### Step 5: Verify and Deliver

Before presenting the video to the user, verify:

- Output resolution is `1080x1920` and audio stream is present via `ffprobe`.

- All 10 words have matching illustrations, IPA phonetics, and Chinese meanings without text clipping.

## Gotchas

- **No text inside generated images**: Image models often render garbled letters if not told `no text, no letters`. Keep all typography rendered cleanly by Pillow.

- **CJK font fallback**: On Linux, ensure a CJK font such as `Noto Sans CJK SC` or `WenQuanYi Micro Hei` is installed so Chinese characters and IPA symbols render instead of boxes.

- **IPA symbol support**: Some CJK fonts lack IPA glyphs like `æ` or `ʃ`. Use a Latin font with full IPA coverage (e.g., `DejaVu Sans`) for the phonetic line and a CJK font for Chinese text.
