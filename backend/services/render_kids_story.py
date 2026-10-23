# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""
Real Video Rendering Pipeline for Kids Story Studio.
Synthesizes speech with Edge-TTS, draws lively animated 2D crayon-style storybook scenes with Pillow,
animates with FFmpeg, and registers the finished MP4 into ViralMint's Library.
"""
import asyncio
import math
import os
import subprocess
import uuid
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from backend.config import settings
from backend.database import AsyncSessionLocal
from backend.models.generated_video import GeneratedVideo


def create_crayon_scene_image(
    output_path: Path,
    title: str,
    scene_num: int,
    total_scenes: int,
    narration: str,
    scene_type: str,
    bg_color: str,
    accent_color: str,
    frame_idx: int = 0,
    total_frames: int = 1,
    animation_mode: str = "lively"
):
    """Draw a vibrant 1080x1920 vertical storybook illustration for toddlers/kids with lively micro-animations."""
    width, height = 1080, 1920
    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    t = frame_idx * 0.1  # time in seconds (10 FPS)
    is_lively = (animation_mode == "lively")

    # Animation variables
    bob_y = int(math.sin(t * 3.5) * 9) if is_lively else 0
    is_blinking = is_lively and ((frame_idx % 30) in (24, 25, 26))
    ear_wiggle = int(math.cos(t * 3.2) * 5) if is_lively else 0

    # 1. Subtle Crayon paper border
    draw.rectangle([(30, 30), (width - 30, height - 30)], outline=accent_color, width=8)
    draw.rectangle([(45, 45), (width - 45, height - 45)], outline="#FFFFFF", width=4)

    # 2. Header: Title & ReelMimic Crayon Badge
    draw.rectangle([(60, 70), (width - 60, 170)], fill="#FFFFFF", outline=accent_color, width=4)
    draw.text((width // 2, 100), f"★ {title} ★", fill="#2C3E50", anchor="mm", font_size=36)
    draw.text(
        (width // 2, 140),
        f"SCENE {scene_num} OF {total_scenes} • {scene_type.upper()}{' (LIVELY 2D)' if is_lively else ''}",
        fill="#E67E22",
        anchor="mm",
        font_size=24
    )

    # 3. Main Illustration Card Area
    center_x = width // 2
    draw.rounded_rectangle(
        [(80, 240), (width - 80, 1260)],
        radius=40,
        fill="#FFFFFF",
        outline=accent_color,
        width=6
    )

    # Draw cheerful scene elements depending on scene type
    if scene_type == "hook":
        # Cozy bedroom window and Barnaby looking out
        # Window frame
        draw.rounded_rectangle([(center_x - 300, 320), (center_x + 300, 800)], radius=20, fill="#D4E6F1", outline="#5DADE2", width=8)

        # Animated falling raindrops
        rain_drops = [
            (center_x - 220, 350), (center_x - 140, 420), (center_x - 60, 360),
            (center_x + 30, 480), (center_x + 120, 380), (center_x + 210, 440),
            (center_x - 180, 520), (center_x - 20, 560), (center_x + 160, 580)
        ]
        for idx, (bx, by) in enumerate(rain_drops):
            if is_lively:
                cur_y = (by + int(frame_idx * (20 + (idx % 3) * 4))) % 420 + 330
            else:
                cur_y = by
            draw.ellipse([(bx, cur_y), (bx + 14, cur_y + 32)], fill="#3498DB")

        # Barnaby face with bobbing
        head_top = 820 + bob_y
        draw.ellipse([(center_x - 140, head_top), (center_x + 140, head_top + 280)], fill="#A0522D")  # Head
        draw.ellipse([(center_x - 170 + ear_wiggle, head_top - 40), (center_x - 90 + ear_wiggle, head_top + 40)], fill="#8B4513")   # Ear L
        draw.ellipse([(center_x + 90 - ear_wiggle, head_top - 40), (center_x + 170 - ear_wiggle, head_top + 40)], fill="#8B4513")   # Ear R
        draw.ellipse([(center_x - 70, head_top + 110), (center_x + 70, head_top + 220)], fill="#F5DEB3")   # Muzzle
        draw.ellipse([(center_x - 25, head_top + 125), (center_x + 25, head_top + 165)], fill="#2C3E50")    # Nose

        # Eyes (blinking animation)
        if is_blinking:
            draw.arc([(center_x - 75, head_top + 50), (center_x - 45, head_top + 75)], 0, 180, fill="#2C3E50", width=5)
            draw.arc([(center_x + 45, head_top + 50), (center_x + 75, head_top + 75)], 0, 180, fill="#2C3E50", width=5)
        else:
            draw.ellipse([(center_x - 75, head_top + 50), (center_x - 45, head_top + 80)], fill="#2C3E50")
            draw.ellipse([(center_x + 45, head_top + 50), (center_x + 75, head_top + 80)], fill="#2C3E50")

        # Rosy cheeks
        draw.ellipse([(center_x - 110, head_top + 110), (center_x - 70, head_top + 140)], fill="#F1948A")
        draw.ellipse([(center_x + 70, head_top + 110), (center_x + 110, head_top + 140)], fill="#F1948A")
        # Yellow Raincoat peek
        draw.ellipse([(center_x - 200, head_top + 250), (center_x + 200, head_top + 460)], fill="#F4D03F")

    elif scene_type == "setup":
        # Warm meadow with animated butterfly
        sun_pulse = int(math.sin(t * 3) * 6) if is_lively else 0
        draw.ellipse([(center_x + 150 - sun_pulse, 280 - sun_pulse), (center_x + 350 + sun_pulse, 480 + sun_pulse)], fill="#F39C12", outline="#F1C40F", width=8)

        # Meadow hill
        draw.ellipse([(center_x - 600, 700), (center_x + 600, 1400)], fill="#58D68D")

        # Animated butterfly fluttering
        if is_lively:
            bf_x = center_x + int(math.sin(t * 2.5) * 190)
            bf_y = 480 + int(math.cos(t * 5.0) * 45)
            draw.ellipse([(bf_x - 18, bf_y - 12), (bf_x, bf_y + 12)], fill="#E74C3C")
            draw.ellipse([(bf_x, bf_y - 12), (bf_x + 18, bf_y + 12)], fill="#E74C3C")
            draw.line([(bf_x, bf_y - 14), (bf_x, bf_y + 14)], fill="#2C3E50", width=3)

        # Barnaby walking happily with yellow coat and boots
        head_top = 520 + bob_y
        draw.ellipse([(center_x - 120, head_top), (center_x + 120, head_top + 240)], fill="#A0522D")
        draw.ellipse([(center_x - 150 + ear_wiggle, head_top - 40), (center_x - 80 + ear_wiggle, head_top + 30)], fill="#8B4513")
        draw.ellipse([(center_x + 80 - ear_wiggle, head_top - 40), (center_x + 150 - ear_wiggle, head_top + 30)], fill="#8B4513")
        draw.ellipse([(center_x - 60, head_top + 100), (center_x + 60, head_top + 200)], fill="#F5DEB3")
        draw.ellipse([(center_x - 20, head_top + 110), (center_x + 20, head_top + 150)], fill="#2C3E50")

        if is_blinking:
            draw.arc([(center_x - 60, head_top + 50), (center_x - 30, head_top + 75)], 0, 180, fill="#2C3E50", width=5)
            draw.arc([(center_x + 30, head_top + 50), (center_x + 60, head_top + 75)], 0, 180, fill="#2C3E50", width=5)
        else:
            draw.ellipse([(center_x - 60, head_top + 50), (center_x - 30, head_top + 80)], fill="#2C3E50")
            draw.ellipse([(center_x + 30, head_top + 50), (center_x + 60, head_top + 80)], fill="#2C3E50")

        # Yellow Coat
        draw.rounded_rectangle([(center_x - 160, head_top + 220), (center_x + 160, head_top + 560)], radius=30, fill="#F4D03F")
        # Red Boots walking step
        step_l = int(math.sin(t * 5) * 12) if is_lively else 0
        step_r = -step_l
        draw.rounded_rectangle([(center_x - 120, head_top + 540 + step_l), (center_x - 30, head_top + 640 + step_l)], radius=15, fill="#E74C3C")
        draw.rounded_rectangle([(center_x + 30, head_top + 540 + step_r), (center_x + 120, head_top + 640 + step_r)], radius=15, fill="#E74C3C")

    elif scene_type == "conflict":
        # Animated puddle with expanding ripple rings
        draw.ellipse([(center_x - 320, 750), (center_x + 320, 1150)], fill="#5DADE2", outline="#2980B9", width=6)

        if is_lively:
            rip_1 = (int(frame_idx * 7)) % 160 + 20
            rip_2 = (int(frame_idx * 7) + 80) % 160 + 20
            draw.ellipse([(center_x - rip_1, 950 - rip_1 // 2), (center_x + rip_1, 950 + rip_1 // 2)], outline="#EBF5FB", width=4)
            draw.ellipse([(center_x - rip_2, 950 - rip_2 // 2), (center_x + rip_2, 950 + rip_2 // 2)], outline="#EBF5FB", width=3)
        else:
            draw.ellipse([(center_x - 200, 830), (center_x + 200, 1070)], fill="#85C1E9", outline="#3498DB", width=4)

        # Barnaby looking puzzled (eyes shifting left/right)
        head_top = 400 + bob_y
        draw.ellipse([(center_x - 120, head_top), (center_x + 120, head_top + 240)], fill="#A0522D")
        draw.ellipse([(center_x - 150, head_top - 40), (center_x - 80, head_top + 30)], fill="#8B4513")
        draw.ellipse([(center_x + 80, head_top - 40), (center_x + 150, head_top + 30)], fill="#8B4513")
        draw.ellipse([(center_x - 60, head_top + 100), (center_x + 60, head_top + 200)], fill="#F5DEB3")
        draw.ellipse([(center_x - 20, head_top + 110), (center_x + 20, head_top + 150)], fill="#2C3E50")

        # Shifting curious gaze
        gaze_x = int(math.sin(t * 3) * 10) if is_lively else 0
        draw.ellipse([(center_x - 70 + gaze_x, head_top + 50), (center_x - 30 + gaze_x, head_top + 90)], fill="#2C3E50")
        draw.ellipse([(center_x + 30 + gaze_x, head_top + 50), (center_x + 70 + gaze_x, head_top + 90)], fill="#2C3E50")

        # Floating Question Mark
        q_y = 380 + int(math.sin(t * 4) * 8) if is_lively else 380
        draw.ellipse([(center_x + 140, q_y - 60), (center_x + 260, q_y + 60)], fill="#FFFFFF", outline="#E67E22", width=4)
        draw.text((center_x + 200, q_y), "?", fill="#E67E22", anchor="mm", font_size=60)

    elif scene_type == "discovery":
        # Sharing umbrella with friendly bobbing and sparkling stars
        tilt_x = int(math.sin(t * 2.5) * 16) if is_lively else 0
        draw.pieslice([(center_x - 300 + tilt_x, 300), (center_x + 300 + tilt_x, 800)], 180, 360, fill="#E74C3C", outline="#C0392B", width=6)
        draw.line([(center_x + tilt_x, 550), (center_x, 900)], fill="#7F8C8D", width=12)

        # Barnaby and friend
        head_top = 680 + bob_y
        draw.ellipse([(center_x - 180, head_top), (center_x, head_top + 180)], fill="#A0522D")
        draw.ellipse([(center_x + 20, head_top + 40 - bob_y), (center_x + 140, head_top + 160 - bob_y)], fill="#D35400")  # Little squirrel friend

        # Animated twinkling stars
        star_spans = [(center_x - 220, 360), (center_x + 240, 380), (center_x + tilt_x, 260)]
        for idx, (sx, sy) in enumerate(star_spans):
            star_sz = 36 + int(math.sin(t * 6 + idx) * 10) if is_lively else 40
            draw.text((sx, sy), "✨", fill="#F39C12", anchor="mm", font_size=star_sz)

    else:
        # Happy celebration jumping & rainbow
        draw.arc([(center_x - 350, 260), (center_x + 350, 760)], 180, 360, fill="#E74C3C", width=18)
        draw.arc([(center_x - 330, 280), (center_x + 330, 740)], 180, 360, fill="#F39C12", width=18)
        draw.arc([(center_x - 310, 300), (center_x + 310, 720)], 180, 360, fill="#F1C40F", width=18)
        draw.arc([(center_x - 290, 320), (center_x + 290, 700)], 180, 360, fill="#2ECC71", width=18)
        draw.arc([(center_x - 270, 340), (center_x + 270, 680)], 180, 360, fill="#3498DB", width=18)
        draw.arc([(center_x - 250, 360), (center_x + 250, 660)], 180, 360, fill="#9B59B6", width=18)

        # Barnaby jumping higher with joy!
        jump_y = -int(abs(math.sin(t * 4.5)) * 26) if is_lively else 0
        head_top = 700 + jump_y
        draw.ellipse([(center_x - 140, head_top), (center_x + 140, head_top + 280)], fill="#A0522D")
        draw.ellipse([(center_x - 70, head_top + 110), (center_x + 70, head_top + 220)], fill="#F5DEB3")
        draw.ellipse([(center_x - 25, head_top + 125), (center_x + 25, head_top + 165)], fill="#2C3E50")
        # Giant Happy Smile
        draw.arc([(center_x - 45, head_top + 130), (center_x + 45, head_top + 190)], 0, 180, fill="#2C3E50", width=6)
        # Happy yellow coat
        draw.rounded_rectangle([(center_x - 180, head_top + 260), (center_x + 180, head_top + 520)], radius=30, fill="#F4D03F")

    # 4. Large Subtitle / Narration Box at the Bottom
    box_top = 1320
    box_bottom = 1760
    draw.rounded_rectangle(
        [(60, box_top), (width - 60, box_bottom)],
        radius=30,
        fill="#FFFFFF",
        outline="#E67E22",
        width=5
    )

    words = narration.split()
    lines = []
    curr = []
    for w in words:
        curr.append(w)
        if len(" ".join(curr)) > 26:
            lines.append(" ".join(curr))
            curr = []
    if curr:
        lines.append(" ".join(curr))

    y_start = box_top + 60
    for i, line in enumerate(lines[:4]):
        draw.text(
            (width // 2, y_start + (i * 60)),
            line,
            fill="#2C3E50",
            anchor="mm",
            font_size=42
        )

    # 5. Footer Branding
    draw.text(
        (width // 2, 1830),
        "ReelMimic 2D Animation • Kids Story Studio",
        fill="#7F8C8D",
        anchor="mm",
        font_size=24
    )

    img.save(output_path, "JPEG", quality=95)
    return output_path


async def render_kids_story_video(storyboard_data: dict, user_id: str = "local") -> dict:
    """End-to-end rendering: generates audio, draws lively frames, stitches video, registers to Library."""
    project_id = storyboard_data.get("project_id") or f"kids-{uuid.uuid4().hex[:8]}"
    title = storyboard_data.get("title", "Barnaby's Big Little Day")
    scenes = storyboard_data.get("scenes", [])
    animation_mode = storyboard_data.get("animation_mode", "lively")

    voice = storyboard_data.get("tts_voice", "en-US-AnaNeural")
    if voice == "Rachel":
        voice = "en-US-AnaNeural"
    elif voice == "Charlie":
        voice = "en-US-GuyNeural"
    elif voice == "Dorothy":
        voice = "en-US-JennyNeural"

    tmp_dir = Path("/tmp") / f"render_{project_id}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    generated_dir = settings.GENERATED_DIR
    thumbnails_dir = settings.THUMBNAILS_DIR
    generated_dir.mkdir(parents=True, exist_ok=True)
    thumbnails_dir.mkdir(parents=True, exist_ok=True)

    final_video_path = generated_dir / f"{project_id}.mp4"
    final_thumb_path = thumbnails_dir / f"{project_id}.jpg"

    palettes = [
        ("#FEF9E7", "#F39C12", "hook"),
        ("#E8F8F5", "#1ABC9C", "setup"),
        ("#EBF5FB", "#3498DB", "conflict"),
        ("#FDEDEC", "#E74C3C", "discovery"),
        ("#FEF5E7", "#E67E22", "resolution")
    ]

    scene_clips = []
    total_duration = 0

    for idx, sc in enumerate(scenes):
        scene_num = idx + 1
        narr = sc.get("narration", "")
        pal = palettes[idx % len(palettes)]
        sc_type = sc.get("type", pal[2])

        # 1. Synthesize audio with edge-tts
        audio_file = tmp_dir / f"scene_{scene_num}.mp3"
        subprocess.run([
            "edge-tts",
            "--voice", voice,
            "--text", narr,
            "--write-media", str(audio_file)
        ], check=True)

        # Get audio duration via ffprobe
        probe_cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_file)
        ]
        dur_out = subprocess.check_output(probe_cmd).decode().strip()
        dur_float = float(dur_out) if dur_out else 4.0
        dur_float = max(dur_float + 0.6, 3.5)
        total_duration += int(dur_float)

        clip_file = tmp_dir / f"clip_{scene_num}.mp4"

        if animation_mode == "lively":
            # 2. Draw animated sequence of frames at 10 FPS
            fps = 10
            total_frames = int(dur_float * fps)
            scene_frame_pattern = tmp_dir / f"frame_{scene_num}_%03d.jpg"

            for f in range(total_frames):
                frame_file = tmp_dir / f"frame_{scene_num}_{f:03d}.jpg"
                create_crayon_scene_image(
                    output_path=frame_file,
                    title=title,
                    scene_num=scene_num,
                    total_scenes=len(scenes),
                    narration=narr,
                    scene_type=sc_type,
                    bg_color=pal[0],
                    accent_color=pal[1],
                    frame_idx=f,
                    total_frames=total_frames,
                    animation_mode="lively"
                )

            # 3. Compile lively frames sequence into clip
            ff_cmd = [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", str(scene_frame_pattern),
                "-i", str(audio_file),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(dur_float),
                "-shortest",
                str(clip_file)
            ]
            subprocess.run(ff_cmd, check=True)

        else:
            # Classic Storybook Pan & Zoom (Static frame with Ken Burns)
            img_file = tmp_dir / f"scene_{scene_num}.jpg"
            create_crayon_scene_image(
                output_path=img_file,
                title=title,
                scene_num=scene_num,
                total_scenes=len(scenes),
                narration=narr,
                scene_type=sc_type,
                bg_color=pal[0],
                accent_color=pal[1],
                animation_mode="storybook_pan"
            )

            zoom_filter = (
                f"zoompan=z='min(zoom+0.0015,1.06)':d={int(dur_float * 25)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=25"
            )
            ff_cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(img_file),
                "-i", str(audio_file),
                "-vf", zoom_filter,
                "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(dur_float),
                "-shortest",
                str(clip_file)
            ]
            subprocess.run(ff_cmd, check=True)

        scene_clips.append(clip_file)

    # 4. Concatenate all clips into final video
    concat_list_file = tmp_dir / "concat_list.txt"
    with open(concat_list_file, "w") as f:
        for c in scene_clips:
            f.write(f"file '{c}'\n")

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list_file),
        "-c", "copy",
        str(final_video_path)
    ], check=True)

    # 5. Extract thumbnail from first second
    subprocess.run([
        "ffmpeg", "-y",
        "-ss", "00:00:01.000",
        "-i", str(final_video_path),
        "-vframes", "1",
        "-q:v", "2",
        str(final_thumb_path)
    ], check=True)

    # 6. Register into GeneratedVideo in Database
    async with AsyncSessionLocal() as db:
        gv = GeneratedVideo(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=f"🧸 {title}",
            script="\n\n".join([f"[Scene {s.get('scene_id', i+1)}] {s.get('narration','')}" for i, s in enumerate(scenes)]),
            niche="Kids Animation / US Preschool",
            video_path=str(final_video_path),
            thumbnail_path=str(final_thumb_path),
            aspect_ratio="9:16",
            duration_seconds=total_duration,
            voice_id=voice,
            gen_tier="premium",
            source_type="kids_story_reelmimic"
        )
        db.add(gv)
        await db.commit()
        video_id = gv.id

    return {
        "video_id": video_id,
        "title": title,
        "video_path": str(final_video_path),
        "thumbnail_path": str(final_thumb_path),
        "duration_seconds": total_duration,
        "status": "ready"
    }
