# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""
Kids Story Service — AI prompt generation, US-targeted story ideation,
and scene-by-scene storyboard planning compliant with COPPA and ReelMimic 2D animation standards.
"""
import json
import logging
import random
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from backend.core.prompt_rules import extract_json_text
from backend.database import AsyncSessionLocal
from backend.models.user_settings import UserSettings

logger = logging.getLogger(__name__)

# ── Curated US Kids Trend Knowledge Base ──────────────────────────────────────
# High-retention categories crafted for US toddlers, preschoolers, and early readers
CURATED_US_KIDS_PROMPTS = {
    "bedtime": [
        {
            "title": "Pip the Sleepy Cloud",
            "hook": "Ever wonder where tired little clouds go when the stars wake up?",
            "prompt": "A fluffy little cloud named Pip is too sleepy to float and gently drifts through the pastel twilight sky searching for the softest mountain peak to take a nighttime nap.",
            "target_age": "preschool",
            "moral_lesson": "Resting after a long day helps you wake up with bright new ideas.",
            "character": {
                "name": "Pip",
                "species": "Fluffy white cloud with rosy cheeks",
                "features": "Big sparkly sleepy eyes, a tiny golden star hairpin",
                "outfit": "Soft lavender bedtime nightcap"
            }
        },
        {
            "title": "Luna the Little Firefly",
            "hook": "Meet Luna, the tiny firefly whose light was just a gentle glow!",
            "prompt": "Luna the little firefly is scared her gentle yellow glow isn't bright enough, until she helps a baby rabbit find his cozy burrow in the whispered woods.",
            "target_age": "preschool",
            "moral_lesson": "Even the smallest light can guide someone home safely.",
            "character": {
                "name": "Luna",
                "species": "Cute cartoon firefly",
                "features": "Translucent glowing wings, friendly smile, warm golden belly",
                "outfit": "Tiny blue leaf scarf"
            }
        },
        {
            "title": "The Blanket Mountain Expedition",
            "hook": "Tonight, Leo's cozy bed turns into the gentlest slumber mountain!",
            "prompt": "Leo the plush lion yawns as he climbs over gentle quilt valleys and feather pillows to reach the magical Dreamland Summit.",
            "target_age": "preschool",
            "moral_lesson": "Bedtime is a cozy adventure into happy dreams.",
            "character": {
                "name": "Leo",
                "species": "Soft golden plush lion cub",
                "features": "Velvet button nose, fluffy caramel mane, stitched smile",
                "outfit": "Striped blue pajamas"
            }
        }
    ],
    "fables": [
        {
            "title": "Barnaby's Rainy Day Boots",
            "hook": "Barnaby woke up with a happy hop, but where did his blue boots drop?",
            "prompt": "Barnaby the little bear cub is so excited for puddle jumping, but when his friend Squirrel drops an acorn in a deep puddle, Barnaby shares his boots so they can splash together.",
            "target_age": "preschool",
            "moral_lesson": "Playing together and sharing makes every rainy day sunny.",
            "character": {
                "name": "Barnaby",
                "species": "Caramel brown bear cub",
                "features": "Round fuzzy ears, inquisitive black eyes, rosy nose",
                "outfit": "Bright yellow raincoat and glossy blue rainboots"
            }
        },
        {
            "title": "The Hedgehog Who Wanted a Hug",
            "hook": "Hedgehogs love cuddles too, but what happens when you have prickles?",
            "prompt": "Henry the hedgehog feels lonely because his prickles poke, until an inventive armadillo knits him a cozy soft wool sweater so everyone in the forest can share warm hugs.",
            "target_age": "early_elementary",
            "moral_lesson": "Kindness and creative problem solving can bring everyone together.",
            "character": {
                "name": "Henry",
                "species": "Gentle baby hedgehog",
                "features": "Soft brown belly, shiny black nose, soft round quills",
                "outfit": "Colorful knitted rainbow turtleneck sweater"
            }
        },
        {
            "title": "The Slowest Race in Fern Valley",
            "hook": "Who says fast is always the best way to cross the finish line?",
            "prompt": "Shelly the garden snail and Benny the bumblebee have a race across a giant sunflower. While Benny rushes, Shelly notices delicious dew drops to share with everyone along the path.",
            "target_age": "preschool",
            "moral_lesson": "Slowing down lets you notice the beauty and help those around you.",
            "character": {
                "name": "Shelly",
                "species": "Smiling garden snail",
                "features": "Swirly pastel peach shell, cheerful antennae with heart tips",
                "outfit": "Tiny green backpack"
            }
        }
    ],
    "habits": [
        {
            "title": "Dino Danny Brushes His Chompers",
            "hook": "How does a big friendly T-Rex keep his sixty teeth sparkling clean?",
            "prompt": "Danny the friendly T-Rex learns the 2-minute bubble brushing dance from Mama Dino, chasing away the sneaky Sugar Bugs before sweet dreams.",
            "target_age": "preschool",
            "moral_lesson": "Brushing teeth every morning and night keeps our smiles bright and healthy.",
            "character": {
                "name": "Danny",
                "species": "Cute green baby T-Rex",
                "features": "Chubby green tail, friendly rounded teeth, bright orange tummy",
                "outfit": "Polka-dot dinosaur bib"
            }
        },
        {
            "title": "The Great Toy Parade",
            "hook": "Uh oh! The playroom floor looks like a block avalanche!",
            "prompt": "Bella and her toy robot turn tidy-up time into a marching musical parade where every block marches happily back to its colorful toybox castle.",
            "target_age": "preschool",
            "moral_lesson": "Cleaning up is super fun when you turn it into a game.",
            "character": {
                "name": "Bella",
                "species": "Cheerful 4-year-old girl",
                "features": "Curly brown pigtails, bright hazel eyes, energetic smile",
                "outfit": "Denim overalls with red sneaker patches"
            }
        },
        {
            "title": "Broccoli Trees for the Royal Feast",
            "hook": "Oliver didn't want the little green trees on his dinner plate...",
            "prompt": "Oliver pretends to be a mighty friendly giant who discovers that steaming 'broccoli forest trees' dipped in mild yogurt cheese give giant muscles for playground jumping.",
            "target_age": "preschool",
            "moral_lesson": "Trying new colorful vegetables gives us energy to play all day.",
            "character": {
                "name": "Oliver",
                "species": "Playful 5-year-old boy",
                "features": "Freckles across his nose, tousled blond hair, cape on his back",
                "outfit": "Super-kid blue cape and striped t-shirt"
            }
        }
    ],
    "silly_rhymes": [
        {
            "title": "The Runaway Blueberry Pancake",
            "hook": "Stop that breakfast! The flapjack is rolling down Maple Street!",
            "prompt": "A warm fluffy blueberry pancake flips right out of the skillet, growing tiny butter feet and dancing through Central Park singing silly rhyming songs.",
            "target_age": "preschool",
            "moral_lesson": "Laughter and silliness bring sunshine to the breakfast table.",
            "character": {
                "name": "Flapjack Jack",
                "species": "Animated golden pancake",
                "features": "Toasty golden surface, blueberry eyes, melting butter hat",
                "outfit": "Maple syrup bowtie"
            }
        },
        {
            "title": "When Cows Wear Polka-Dot Socks",
            "hook": "Cows on the farm never wear shoes... until Clara found polka-dot socks!",
            "prompt": "Clara the Holstein cow slips on four rainbow polka-dot tube socks and suddenly discovers she can do the tap-dance shuffle in the barnyard.",
            "target_age": "early_elementary",
            "moral_lesson": "Expressing your unique style makes life so much more fun.",
            "character": {
                "name": "Clara",
                "species": "Black and white Holstein dairy cow",
                "features": "Big gentle cow eyes, pink muzzle, sweet smile",
                "outfit": "Bright mismatched knee-high polka-dot socks"
            }
        }
    ],
    "stem": [
        {
            "title": "Where Does the Rainbow Sleep?",
            "hook": "When the sun peeked through the raindrops, a magical color bridge appeared!",
            "prompt": "Maya and her puppy follow a glowing rainbow arch across the meadow to learn how droplets of water split white sunlight into red, orange, yellow, green, blue, and purple.",
            "target_age": "early_elementary",
            "moral_lesson": "Curiosity and asking 'why' helps us understand the magic of science.",
            "character": {
                "name": "Maya",
                "species": "Curious young girl explorer",
                "features": "Dark curly hair in a bun, magnifying glass necklace",
                "outfit": "Yellow rain poncho and puddle jumpers"
            }
        },
        {
            "title": "The Seed That Reached for the Sun",
            "hook": "Deep in the brown soil, tiny Sammy Seed felt a warm tickle...",
            "prompt": "Sammy the sunflower seed drinks cool morning water and pushes his first green sprout up through the dark soil to say hello to the shining golden sun.",
            "target_age": "preschool",
            "moral_lesson": "With patience, water, and sunshine, little things grow big and strong.",
            "character": {
                "name": "Sammy",
                "species": "Cute little sprouting seed",
                "features": "Striped seed coat backpack, bright emerald sprout cap",
                "outfit": "Green leaf mittens"
            }
        }
    ]
}


class KidsStoryService:
    """Orchestrates US Kids story prompt recommendations and ReelMimic-compatible storyboarding."""

    @staticmethod
    async def get_inspired_prompts(
        category: str = "fables",
        target_age: str = "preschool",
        count: int = 3
    ) -> List[Dict[str, Any]]:
        """Return curated US kids prompts with optional AI enhancement."""
        cat_key = category.lower().strip()
        pool = CURATED_US_KIDS_PROMPTS.get(cat_key) or CURATED_US_KIDS_PROMPTS.get("fables", [])

        # Filter by age if available
        matched = [item for item in pool if item.get("target_age") == target_age]
        if not matched:
            matched = pool

        # Sample from curated pool
        sample_count = min(count, len(matched))
        selected = random.sample(matched, sample_count) if len(matched) >= sample_count else matched

        # Try to call LLM for a fresh creative spin if API key is configured
        ai_client = await KidsStoryService._get_ai_client_safe()
        if not ai_client:
            return selected

        try:
            system = (
                "You are an expert children's book author and YouTube Kids content strategist in the US. "
                "You craft viral, heartwarming, high-retention stories for American toddlers and preschoolers. "
                "Stories must follow COPPA safety rules: zero scary elements, peaceful resolution, simple language, "
                "playful rhymes, and high visual appeal. Return JSON array only."
            )
            prompt = (
                f"Generate {count} fresh story ideas for US children in the '{category}' category "
                f"targeting {target_age}. Return JSON array of objects with keys: "
                f"'title', 'hook' (captivating 0-3s verbal hook), 'prompt' (1-2 sentence core storyline), "
                f"'target_age', 'moral_lesson', and 'character' (object with name, species, features, outfit)."
            )
            resp = await ai_client.chat(
                messages=[{"role": "user", "content": prompt}],
                system=system,
                max_tokens=1500,
            )
            text = extract_json_text(resp.strip())
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                text = text.rsplit("```", 1)[0]
            data = json.loads(text.strip())
            if isinstance(data, list) and len(data) > 0:
                return data
        except Exception as e:
            logger.info(f"AI creative prompt generation skipped/fallback: {e}")

        return selected

    @staticmethod
    async def generate_storyboard(
        prompt: str,
        target_age: str = "preschool",
        style: str = "crayon_picture_book",
        total_scenes: int = 6,
        reference_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Convert a story prompt into an interactive, ReelMimic-compatible scene storyboard."""
        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            raise ValueError("Story prompt cannot be empty.")

        ai_client = await KidsStoryService._get_ai_client_safe()

        if ai_client:
            try:
                return await KidsStoryService._generate_storyboard_llm(
                    ai_client, cleaned_prompt, target_age, style, total_scenes, reference_notes
                )
            except Exception as e:
                logger.warning(f"LLM storyboard generation failed, using structured heuristic builder: {e}")

        # Reliable Fallback Generator
        return KidsStoryService._generate_storyboard_fallback(cleaned_prompt, target_age, style, total_scenes)

    @staticmethod
    async def _generate_storyboard_llm(
        ai_client,
        prompt: str,
        target_age: str,
        style: str,
        total_scenes: int,
        reference_notes: Optional[str]
    ) -> Dict[str, Any]:
        ref_context = f"\nReference Video Pacing/Rhythm Notes:\n{reference_notes}\n" if reference_notes else ""

        system = (
            "You are a master storyboard artist and scriptwriter for US Kids Animation (YouTube Shorts/TikTok). "
            "Your output will be rendered using ReelMimic 2D procedural drawing engines (crayon, cut-out paper, watercolor). "
            "Strict Guidelines:\n"
            "1. COPPA compliant: safe, joyful, peaceful conflict resolution, positive moral.\n"
            "2. Total duration: 35-50 seconds. Each scene is 4-8 seconds.\n"
            "3. Narration must be simple American English, rhythmic or rhyming, conversational for kids.\n"
            "4. Maintain strict CHARACTER CONSISTENCY: The same character attributes must be specified in every visual prompt.\n"
            "5. Return pure JSON only with keys: title, moral_lesson, drawing_engine, target_age, character_anchor, scenes."
        )

        user_content = (
            f"Create a complete {total_scenes}-scene storyboard plan based on this prompt:\n"
            f"\"{prompt}\"\n"
            f"Target Age: {target_age}\n"
            f"Drawing Engine Style: {style}\n"
            f"{ref_context}\n"
            "Format the output strictly as JSON:\n"
            "{\n"
            "  \"title\": \"Catchy US Kids Title\",\n"
            "  \"moral_lesson\": \"Short moral lesson\",\n"
            "  \"drawing_engine\": \"" + style + "\",\n"
            "  \"target_age\": \"" + target_age + "\",\n"
            "  \"character_anchor\": {\n"
            "    \"name\": \"Character Name\",\n"
            "    \"species\": \"Species/Type\",\n"
            "    \"features\": \"Key visual facial/physical features to keep constant across all frames\",\n"
            "    \"outfit\": \"Exact clothes/colors worn\"\n"
            "  },\n"
            "  \"scenes\": [\n"
            "    {\n"
            "      \"scene_id\": 1,\n"
            "      \"type\": \"hook\",\n"
            "      \"start_sec\": 0,\n"
            "      \"end_sec\": 4,\n"
            "      \"duration_sec\": 4,\n"
            "      \"narration\": \"Short rhythmic US English narration line...\",\n"
            "      \"visual_prompt\": \"Detailed 2D scene description with character name, setting, actions, lighting in " + style + " style\",\n"
            "      \"sfx_cue\": \"soft chime sound, happy giggle\"\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        resp = await ai_client.chat(
            messages=[{"role": "user", "content": user_content}],
            system=system,
            max_tokens=2500,
        )

        text = extract_json_text(resp.strip())
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        data = json.loads(text.strip())

        if "scenes" in data and isinstance(data["scenes"], list):
            # Normalize scene IDs and timings
            t = 0
            for idx, sc in enumerate(data["scenes"], 1):
                sc["scene_id"] = idx
                dur = sc.get("duration_sec") or 5
                sc["start_sec"] = t
                sc["end_sec"] = t + dur
                t += dur
            return data

        raise ValueError("Invalid JSON schema returned by LLM")

    @staticmethod
    def _generate_storyboard_fallback(
        prompt: str,
        target_age: str,
        style: str,
        total_scenes: int
    ) -> Dict[str, Any]:
        """Robust deterministic storyboard generator for offline or keyless use."""
        # Detect basic theme
        words = prompt.split()
        char_name = "Barnaby" if "bear" in prompt.lower() else "Pip" if "cloud" in prompt.lower() else "Oliver"
        species = "curious animal friend"
        outfit = "bright cozy yellow coat with red boots"

        scenes = []
        timings = [4, 5, 5, 6, 5, 5][:total_scenes]
        types = ["hook", "setup", "conflict", "discovery", "resolution", "outro"]

        t = 0
        templates = [
            ("Once upon a sunny morning, a cheerful adventure was about to begin!", f"{style} style, {char_name} looking out from a cozy window with curious eyes", "gentle bird chirp, music box chime"),
            (f"{char_name} took a deep breath and stepped out into the colorful meadow.", f"{style} style, {char_name} stepping onto emerald green grass surrounded by wildflowers", "soft wind whoosh, footsteps"),
            ("Uh oh! There was a tiny puzzle along the winding path.", f"{style} style, {char_name} puzzled face looking at a gentle obstacle, pastel clouds", "quirky cartoon boing, curious hum"),
            ("With a gentle smile and a little help, things began to click!", f"{style} style, {char_name} sharing a warm moment with a friendly companion", "sparkle magic chime, happy chime"),
            ("Together, they found that kindness makes every journey brighter!", f"{style} style, {char_name} celebrating happily under warm golden sunshine", "cheerful acoustic strum, giggle"),
            ("And so, with a happy heart, it was time to say sweet dreams until tomorrow!", f"{style} style, {char_name} waving goodbye under twilight stars, cozy and safe", "twinkle star sound, lullaby fade")
        ]

        for i in range(min(total_scenes, len(templates))):
            dur = timings[i] if i < len(timings) else 5
            narr, vis, sfx = templates[i]
            scenes.append({
                "scene_id": i + 1,
                "type": types[i] if i < len(types) else "adventure",
                "start_sec": t,
                "end_sec": t + dur,
                "duration_sec": dur,
                "narration": narr,
                "visual_prompt": f"{vis}, warm palette, high aesthetic, child friendly",
                "sfx_cue": sfx
            })
            t += dur

        return {
            "title": f"{char_name}'s Big Little Day",
            "moral_lesson": "Kindness, sharing, and a curious heart make every day wonderful.",
            "drawing_engine": style,
            "target_age": target_age,
            "character_anchor": {
                "name": char_name,
                "species": species,
                "features": "Big friendly eyes, rounded soft silhouette, warm welcoming smile",
                "outfit": outfit
            },
            "scenes": scenes
        }

    @staticmethod
    async def refine_scene(scene_data: Dict[str, Any], action: str = "rhyme") -> Dict[str, Any]:
        """Refine a single scene (make it rhyme, simplify vocabulary, or boost hook)."""
        ai_client = await KidsStoryService._get_ai_client_safe()
        current_narration = scene_data.get("narration", "")

        if not ai_client or not current_narration:
            # Fallback simple modifiers
            if action == "rhyme":
                scene_data["narration"] = current_narration + " Hop, hop, hooray, what a wonderful day!"
            elif action == "simplify":
                scene_data["narration"] = "Look at that! So big, so bright and sweet!"
            elif action == "enhance_hook":
                scene_data["narration"] = "Wait! Did you see what just happened right here?"
            return scene_data

        action_prompts = {
            "rhyme": "Rewrite this narration into a bouncy, musical 2-line rhyme suitable for a 3-year-old American child.",
            "simplify": "Simplify the vocabulary of this narration so a toddler can easily understand it.",
            "enhance_hook": "Rewrite this line into an irresistibly catchy 3-second opening hook that grabs attention immediately."
        }

        instr = action_prompts.get(action, "Improve this children's story line.")
        try:
            resp = await ai_client.chat(
                messages=[{"role": "user", "content": f"{instr}\nOriginal text: \"{current_narration}\"\nOutput ONLY the revised text."}],
                system="You write simple, joyful scripts for US children's video storybooks.",
                max_tokens=150
            )
            clean_text = resp.strip().strip('"')
            scene_data["narration"] = clean_text
        except Exception as e:
            logger.warning(f"Scene refinement AI call failed: {e}")

        return scene_data

    @staticmethod
    async def _get_ai_client_safe():
        """Retrieve user configured AI client or return None."""
        try:
            from backend.core.ai_provider import get_ai_client
            async def _fetch():
                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(UserSettings).limit(1))
                    return result.scalar_one_or_none()
            settings = await asyncio.wait_for(_fetch(), timeout=1.5)
            return get_ai_client(settings)
        except Exception:
            return None
