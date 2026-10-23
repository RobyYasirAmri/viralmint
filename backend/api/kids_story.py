# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""
REST Endpoints for Kids Story Studio (Powered by ReelMimic).

POST /api/kids-story/inspire             — Get US Kids curated prompt inspirations
POST /api/kids-story/deconstruct-ref     — Deconstruct reference video pacing/rhythm
POST /api/kids-story/generate-storyboard — Generate scene-by-scene storyboard plan
POST /api/kids-story/refine-scene        — Refine scene narration (rhyme, simplify, hook)
POST /api/kids-story/render              — Launch ReelMimic multi-agent 2D production
GET  /api/kids-story/presets             — Get available drawing styles, categories, voices
"""
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.kids_story_service import KidsStoryService
from backend.services.reelmimic_service import ReelMimicService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kids-story", tags=["kids-story"])


# ── Request / Response Schemas ────────────────────────────────────────────────

class InspireRequest(BaseModel):
    category: str = "fables"
    target_age: str = "preschool"
    count: int = Field(default=3, ge=1, le=10)


class DeconstructRefRequest(BaseModel):
    reference_url: str


class GenerateStoryboardRequest(BaseModel):
    prompt: str
    target_age: str = "preschool"
    style: str = "crayon_picture_book"
    total_scenes: int = Field(default=6, ge=3, le=10)
    reference_notes: Optional[str] = None


class RefineSceneRequest(BaseModel):
    scene: Dict[str, Any]
    action: str = Field(default="rhyme", pattern="^(rhyme|simplify|enhance_hook)$")


class RenderRequest(BaseModel):
    storyboard: Dict[str, Any]
    user_id: str = "local"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/presets")
async def get_presets():
    """Return preset categories, drawing styles, and US voiceover options."""
    return {
        "categories": [
            {"id": "bedtime", "label": "Bedtime & Calming", "icon": "🌙", "desc": "Soft, relaxing stories to ease into sleep"},
            {"id": "fables", "label": "Animal Fables", "icon": "🐾", "desc": "Friendship, sharing, and gentle moral lessons"},
            {"id": "habits", "label": "Good Habits & Manners", "icon": "🥦", "desc": "Brushing teeth, cleanup time, eating veggies"},
            {"id": "silly_rhymes", "label": "Silly Adventures & Rhymes", "icon": "🚀", "desc": "Dr. Seuss-style playful rhyming fun"},
            {"id": "stem", "label": "Little Explorers (STEM)", "icon": "🔍", "desc": "Simple science, nature, rainbows and seeds"}
        ],
        "drawing_engines": [
            {
                "id": "crayon_picture_book",
                "label": "Crayon Picture Book",
                "icon": "🖍️",
                "desc": "Whimsical colored pencil & crayon texture on soft paper",
                "best_for": "Toddlers & Preschoolers (Ages 2-5)"
            },
            {
                "id": "paper_cutout",
                "label": "Paper Cut-out Stop-Motion",
                "icon": "✂️",
                "desc": "Layered collage papercraft inspired by Eric Carle",
                "best_for": "Preschool & Kindergarten (Ages 3-6)"
            },
            {
                "id": "watercolor",
                "label": "Hand-Painted Watercolor",
                "icon": "🎨",
                "desc": "Classic storybook watercolor washes ala Beatrix Potter",
                "best_for": "Bedtime Tales & Classic Fables"
            },
            {
                "id": "vector",
                "label": "Vector Motion Graphics",
                "icon": "📐",
                "desc": "Vibrant, clean 2D cartoon style ala PBS Kids",
                "best_for": "Energetic Songs & Good Habit Stories"
            }
        ],
        "voice_presets": [
            {"id": "Rachel", "name": "Rachel (Warm Storyteller)", "gender": "Female", "accent": "American", "vibe": "Gentle, maternal, soothing"},
            {"id": "Charlie", "name": "Charlie (Excited Explorer)", "gender": "Male", "accent": "American", "vibe": "Energetic, playful, friendly"},
            {"id": "Dorothy", "name": "Dorothy (Cozy Grandmother)", "gender": "Female", "accent": "American", "vibe": "Classic fairytale bedtime narrator"}
        ],
        "target_ages": [
            {"id": "preschool", "label": "Preschool (Ages 2-5)", "traits": "Short sentences, repetitive rhymes, sensory words"},
            {"id": "early_elementary", "label": "Early Elementary (Ages 6-8)", "traits": "Curiosity quests, simple teamwork, light humor"}
        ],
        "animation_modes": [
            {"id": "lively", "label": "🌟 Lively 2D Animation", "desc": "Character blinks, breathes & bounces; falling rain, floating clouds & magic sparkles"},
            {"id": "storybook_pan", "label": "🎞️ Gentle Storybook Pan & Zoom", "desc": "Classic stillbook aesthetic with slow cinematic Ken Burns camera drift"}
        ]
    }


@router.get("/load/{video_id}")
async def load_kids_story(video_id: str):
    """Load a generated kids story back into the studio for editing."""
    from backend.database import AsyncSessionLocal
    from backend.models.generated_video import GeneratedVideo
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(GeneratedVideo).where(GeneratedVideo.id == video_id))
        video = res.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    title = (video.title or "Untitled Story").replace("🧸 ", "").strip()
    script = video.script or ""

    raw_scenes = [s.strip() for s in script.split("\n\n") if s.strip()]
    scenes = []
    t = 0
    types = ["hook", "setup", "conflict", "discovery", "resolution"]

    if raw_scenes:
        for idx, text in enumerate(raw_scenes, 1):
            clean_narr = text
            if clean_narr.startswith(f"[Scene {idx}]"):
                clean_narr = clean_narr.replace(f"[Scene {idx}]", "").strip()
            scenes.append({
                "scene_id": idx,
                "type": types[(idx - 1) % len(types)],
                "start_sec": t,
                "end_sec": t + 5,
                "duration_sec": 5,
                "narration": clean_narr,
                "visual_prompt": f"crayon_picture_book style, Barnaby in heartwarming scene {idx}, child friendly, vibrant colors",
                "sfx_cue": "gentle chime"
            })
            t += 5
    else:
        scenes = [
            {"scene_id": 1, "type": "hook", "start_sec": 0, "end_sec": 5, "duration_sec": 5, "narration": script or "A wonderful day begins!", "visual_prompt": "crayon_picture_book style, child friendly", "sfx_cue": "soft chime"}
        ]

    return {
        "status": "success",
        "storyboard": {
            "title": title,
            "moral_lesson": "Kindness, sharing, and a curious heart make every day wonderful.",
            "drawing_engine": "crayon_picture_book",
            "animation_mode": "lively",
            "target_age": "preschool",
            "tts_voice": video.voice_id or "Rachel",
            "character_anchor": {
                "name": "Barnaby",
                "species": "Caramel brown bear cub",
                "features": "Big friendly eyes, rounded soft silhouette, warm welcoming smile",
                "outfit": "Bright yellow raincoat and red boots"
            },
            "scenes": scenes
        }
    }


@router.post("/inspire")
async def inspire_prompts(body: InspireRequest):
    """Generate or retrieve curated US Kids story prompt ideas."""
    try:
        suggestions = await KidsStoryService.get_inspired_prompts(
            category=body.category,
            target_age=body.target_age,
            count=body.count
        )
        return {"category": body.category, "target_age": body.target_age, "suggestions": suggestions}
    except Exception as e:
        logger.error(f"Failed to generate story inspirations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deconstruct-ref")
async def deconstruct_reference(body: DeconstructRefRequest):
    """Analyze a reference video URL to extract pacing, BPM, and visual cadence."""
    if not body.reference_url.strip():
        raise HTTPException(status_code=400, detail="Reference URL is required")

    try:
        analysis = await ReelMimicService.deconstruct_reference_video(body.reference_url)
        return {"status": "success", "analysis": analysis}
    except Exception as e:
        logger.error(f"Reference video deconstruction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-storyboard")
async def generate_storyboard(body: GenerateStoryboardRequest):
    """Generate a structured, ReelMimic-ready scene storyboard from a story prompt."""
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="Story prompt cannot be empty")

    try:
        storyboard = await KidsStoryService.generate_storyboard(
            prompt=body.prompt,
            target_age=body.target_age,
            style=body.style,
            total_scenes=body.total_scenes,
            reference_notes=body.reference_notes
        )
        return {"status": "success", "storyboard": storyboard}
    except Exception as e:
        logger.error(f"Storyboard generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refine-scene")
async def refine_scene(body: RefineSceneRequest):
    """Refine a single storyboard scene (rhyme, simplify, or boost hook)."""
    try:
        refined = await KidsStoryService.refine_scene(body.scene, action=body.action)
        return {"status": "success", "scene": refined}
    except Exception as e:
        logger.error(f"Scene refinement failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/render")
async def render_kids_story(body: RenderRequest):
    """Launch the ReelMimic multi-agent 2D procedural rendering production line."""
    if not body.storyboard or not body.storyboard.get("scenes"):
        raise HTTPException(status_code=400, detail="Storyboard with scenes is required for rendering")

    try:
        result = await ReelMimicService.dispatch_production_job(
            storyboard_data=body.storyboard,
            user_id=body.user_id
        )
        return result
    except Exception as e:
        logger.error(f"Failed to dispatch ReelMimic production job: {e}")
        raise HTTPException(status_code=500, detail=str(e))
