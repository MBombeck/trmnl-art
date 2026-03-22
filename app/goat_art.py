"""Goat Art source — pre-generated gallery + on-demand Gemini generation.

Serves famous paintings reimagined with goats, generated via Google Imagen 4 Ultra.
Falls back to pre-generated gallery images when API is unavailable.
"""

import base64
import io
import json
import logging
import random
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image

from app.config import DATA_DIR, DISPLAY_HEIGHT, DISPLAY_WIDTH, GEMINI_API_KEY, GOAT_GALLERY_DIR

log = logging.getLogger("trmnl-art.goat-art")

IMAGEN_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-ultra-generate-001:predict"
HISTORY_FILE = DATA_DIR / "goat-history.json"

# Quality suffix appended to every prompt
QUALITY_SUFFIX = (
    "The entire painting must be rendered consistently in this single artistic style. "
    "The goat is NOT a photographic element composited onto a painting — it is itself "
    "painted with identical brushwork, palette, and technique as the rest of the scene. "
    "No picture frame. No border. No museum wall. No watermark. No text. No signature. "
    "Fill the entire canvas edge to edge. Authentic traditional painting, "
    "NOT digital art, NOT 3D render, NOT photomanipulation."
)

# --- Pre-defined gallery prompts (for on-demand generation) ---
GALLERY_PROMPTS = [
    {
        "id": "vermeer_pearl_earring",
        "title": "Goat with a Pearl Earring — Vermeer",
        "prompt": (
            "A landscape-format oil painting in the meticulous style of Johannes Vermeer, circa 1665. "
            "A white goat in three-quarter profile against a deep black background, turning its head "
            "to gaze at the viewer with one large dark liquid eye. A painted pearl earring dangles "
            "from its ear with soft oil-painted highlights. A blue and gold silk cloth draped over "
            "its horns like a turban. Vermeer's signature soft-focus sfumato and pointillé highlights "
            "on the fur. Dutch Golden Age palette: deep ultramarine, lead-tin yellow, bone black. "
        ),
    },
    {
        "id": "van_gogh_starry_night",
        "title": "Starry Night with Goat — Van Gogh",
        "prompt": (
            "An oil painting in Vincent van Gogh's Saint-Rémy impasto style, 1889. A goat stands "
            "atop a hill silhouetted against a vast swirling night sky. The goat's fur painted in "
            "thick directional brushstrokes of cream, raw umber, and Naples yellow. The sky dominates "
            "with spiraling galaxies of cobalt blue, radiating stars in cadmium yellow. Dark cypress "
            "trees, a Provençal village with warm orange windows. Heavy impasto throughout. "
        ),
    },
    {
        "id": "monet_water_lilies",
        "title": "Water Lilies with Goat — Monet",
        "prompt": (
            "An oil painting in Claude Monet's late Water Lilies style, circa 1906. A tranquil pond "
            "with floating water lilies. A goat at the edge, leaning to drink, reflection shimmering. "
            "Monet's broken color technique — short loose dabs of lavender, sage green, warm pink. "
            "Weeping willow branches in cascading yellow-green. No hard outlines — vibrating patches "
            "of complementary color. Oil on canvas, visible woven texture. "
        ),
    },
    {
        "id": "klimt_kiss",
        "title": "The Kiss — Goat Edition — Klimt",
        "prompt": (
            "An oil and gold leaf painting in Gustav Klimt's golden phase, circa 1908. Two goats nuzzle "
            "tenderly on a flower-covered hillside, wrapped in golden robes with geometric patterns — "
            "rectangular mosaic and circular spirals. Faces naturalistic, bodies dissolve into flat "
            "decorated golden drapery. Pointillist flower carpet, gold leaf background with tooled "
            "texture. Art Nouveau vines. Tension between realism and abstraction. "
        ),
    },
    {
        "id": "hokusai_great_wave",
        "title": "The Great Wave with Goats — Hokusai",
        "prompt": (
            "A woodblock print in Hokusai's 'Thirty-six Views of Mount Fuji' style, 1831. Enormous "
            "curling wave with foam claws. Wooden boats crewed by goats gripping gunwales, ears blown "
            "flat. Mount Fuji centered in background. Bold Prussian blue outlines, flat color fields "
            "of indigo, grey, cream. Ukiyo-e flat colors, precise outlines, bokashi gradation. "
            "Washi paper texture visible. "
        ),
    },
    {
        "id": "rembrandt_night_watch",
        "title": "The Night Watch — Goat Company — Rembrandt",
        "prompt": (
            "An oil painting in Rembrandt's dramatic chiaroscuro, circa 1642. Goats in Dutch militia "
            "attire — plumed hats, ruffs, golden sashes, pikes and muskets. Central goat illuminated "
            "by warm golden light, smaller white goat glowing mysteriously. Others emerge from darkness. "
            "Rich impasto highlights, thin glazes in shadows. Burnt sienna, yellow ochre, ivory black. "
        ),
    },
    {
        "id": "botticelli_birth",
        "title": "The Birth of Goat — Botticelli",
        "prompt": (
            "A tempera painting in Botticelli's Early Renaissance style, circa 1485. A white goat "
            "stands gracefully on a scallop shell on gentle waves. Wind gods blow flowers and golden "
            "light. A figure holds a flowing floral cloak. Botticelli's flowing linear style with "
            "golden highlights. Shell pink, seafoam green, pale gold palette. Egg tempera, fine detail. "
        ),
    },
    {
        "id": "degas_ballet",
        "title": "The Ballet Class — Goat Dancers — Degas",
        "prompt": (
            "An oil painting in Degas's intimate impressionist style, circa 1874. A dance studio "
            "with wooden floors. Young goats in white tutus practice at the barre. An elderly goat "
            "ballet master with a cane watches. Off-center composition, figures cropped at edges. "
            "Soft window light. Warm wood tones, white tulle, pale pink. Loose brushwork capturing "
            "movement and fleeting gesture. "
        ),
    },
    {
        "id": "dali_persistence",
        "title": "The Persistence of Goats — Dalí",
        "prompt": (
            "An oil painting in Dalí's hyperrealistic surrealist style, 1931. Barren dreamlike coast "
            "at twilight with melting clocks on branches and ledges. A sleeping goat in the center "
            "with a melting clock on its back. Hard shadows, photorealistic impossible objects. "
            "Amber desert palette, deep blue-black shadows. Meticulous academic precision. "
        ),
    },
    {
        "id": "seurat_sunday",
        "title": "A Sunday on the Island of Goats — Seurat",
        "prompt": (
            "A painting in Seurat's pointillist technique, 1886. Park scene by a river, sunny "
            "afternoon. Multiple goats in Victorian clothing — top hats, parasols, dresses — on "
            "manicured grass under dappled tree shade. Tiny dots of pure color blending optically. "
            "Complementary pairs: orange-blue, green-red. Warm golden light. Calm geometric composition. "
        ),
    },
    {
        "id": "van_gogh_sunflower_goat",
        "title": "Goat Eating the Sunflowers — Van Gogh",
        "prompt": (
            "An oil painting in Van Gogh's bold impasto style, 1888. A vase of sunflowers on a table "
            "— but a cheeky goat has climbed up and is happily munching one, petals falling from its "
            "mouth. Remaining sunflowers droop. Same thick brushstrokes throughout: cadmium yellow, "
            "chrome yellow, raw sienna. Warm yellow-ochre background. Humorous but masterfully painted. "
        ),
    },
    {
        "id": "grant_wood_american_goathic",
        "title": "American Goathic — Grant Wood",
        "prompt": (
            "An oil painting in Grant Wood's regionalist style, 1930. Two goats before a white house "
            "with Gothic window. Male goat holds pitchfork, wears dark jacket. Female goat in colonial "
            "apron and cameo brooch. Stern stoic expressions. Meticulous detail on siding, window "
            "tracery. Muted Iowa palette of cream, brown, dark green. Deadpan humor through seriousness. "
        ),
    },
    {
        "id": "frida_self_portrait_goat",
        "title": "Self-Portrait with Goat Horns — Frida Kahlo",
        "prompt": (
            "An oil painting in Frida Kahlo's surrealist folk art style, circa 1940. A goat with "
            "Frida's flower crown and unibrow gazes at the viewer with intense dark eyes. Lush "
            "tropical foliage and butterflies fill the background. A monkey on the goat's shoulder. "
            "Bright Mexican folk art colors — deep greens, vibrant reds. Botanical accuracy, "
            "emotional directness. Proud, defiant, vulnerable expression. "
        ),
    },
    {
        "id": "picasso_guernica_goats",
        "title": "Goaternica — Picasso",
        "prompt": (
            "A painting in Picasso's cubist-expressionist Guernica style, 1937. Fragmented angular "
            "goats in anguished poses — mouths open, eyes displaced, limbs at impossible angles. "
            "Strictly monochrome: black, white, greys only. Newspaper-texture collage effects. "
            "Sharp geometry, multiple simultaneous viewpoints. Flat graphic quality with emotional "
            "intensity. Oil on canvas. "
        ),
    },
    {
        "id": "rousseau_dream",
        "title": "The Dream — Goat in the Jungle — Rousseau",
        "prompt": (
            "An oil painting in Henri Rousseau's naïve jungle style, 1910. Lush tropical jungle "
            "at night with enormous leaves, exotic flowers, hidden animals. A white goat reclines "
            "on a red velvet chaise longue in the jungle. Full moon in pale silver-blue. Glowing "
            "eyes in foliage. Flat decorative style, precise leaf-by-leaf rendering. Rich greens "
            "in dozens of shades. Dreamlike, magical, childlike wonder. "
        ),
    },
    {
        "id": "magritte_son_of_goat",
        "title": "The Son of Goat — Magritte",
        "prompt": (
            "An oil painting in Magritte's precise surrealist style, 1964. A goat in a dark overcoat "
            "and bowler hat before a low wall with sea and cloudy sky behind. A large green apple "
            "floats in front of the goat's face. Deadpan photographic precision, clean edges, "
            "smooth gradients. Muted grey-green, charcoal, overcast sky blue. Calm matter-of-fact "
            "surrealism. "
        ),
    },
    {
        "id": "turner_fighting_temeraire",
        "title": "The Fighting Goatmeraire — Turner",
        "prompt": (
            "An oil painting in Turner's late atmospheric style, circa 1839. A majestic old ship "
            "with goat crew towed up the Thames at sunset. Vast wash of molten gold, amber, pale "
            "rose dissolving into mist. Ghostly pale masts against fiery sky. Water reflects burning "
            "colors. Everything dissolves into light and atmosphere. Wet-into-wet technique. "
        ),
    },
    {
        "id": "renoir_moulin",
        "title": "Bal du Moulin de la Goatlette — Renoir",
        "prompt": (
            "An oil painting in Renoir's joyful impressionist style, 1876. Outdoor dance at "
            "Montmartre with goats in Sunday finery — straw hats, striped shirts, flowing dresses. "
            "Dappled sunlight through acacia trees. Warm rose, peach, lavender tones. Soft feathery "
            "brushwork, flickering light patterns. Festive lanterns. Joy and movement everywhere. "
        ),
    },
    {
        "id": "matisse_dance_goats",
        "title": "The Dance of the Goats — Matisse",
        "prompt": (
            "A painting in Matisse's bold fauvist style, 1910. Five goats hold hooves and dance in "
            "a circle against deep blue sky and green hill. Flat terracotta-red goats with bold dark "
            "outlines, simplified to essential joyful curves. No detail, no shading, no perspective — "
            "pure color, pure movement, pure joy. Oil on canvas, large flat color fields. "
        ),
    },
    {
        "id": "bruegel_hunters",
        "title": "Hunters in the Snow — Goat Hunters — Bruegel",
        "prompt": (
            "An oil painting in Bruegel the Elder's panoramic style, 1565. Winter landscape from high "
            "vantage. Three goat hunters trudge through snow with dogs. Below, goats ice-skating on "
            "frozen ponds. Snow-covered rooftops, bare trees silhouetted against pale winter sky. "
            "Jagged mountains. Extraordinary depth, miniature figures full of life. Cold blue-green "
            "palette. "
        ),
    },
    {
        "id": "hopper_nightgoats",
        "title": "Nightgoats — Edward Hopper",
        "prompt": (
            "An oil painting in Hopper's stark realist style, 1942. Late-night diner through plate "
            "glass from the dark street. Three goats at the curved counter under fluorescent light — "
            "one alone, a couple together. A goat barista in white. Interior glows warm yellow-green "
            "against dark blue-black street. Empty sidewalk. Loneliness and urban isolation. Clean "
            "geometry, sharp light/dark contrast. "
        ),
    },
    {
        "id": "warhol_goat",
        "title": "Goat (Pop Art) — Warhol",
        "prompt": (
            "A silkscreen print in Warhol's pop art style, 1962. Close-up goat face in a 2x2 grid, "
            "each quadrant in different bold flat colors — pink/blue, yellow/red, green/orange, "
            "purple/lime. High contrast photographic source, stark black outlines, flat saturated "
            "color fields. Slight silkscreen misregistration. Commercial, graphic, bold impact. "
        ),
    },
    {
        "id": "whistler_mother",
        "title": "Arrangement in Grey and Goat — Whistler",
        "prompt": (
            "An oil painting in Whistler's tonal style, 1871. Profile of an elderly goat sitting "
            "upright in a wooden chair against a grey wall. Dark dress and white lace bonnet. Framed "
            "picture on wall. Restrained palette of greys, blacks, muted whites. Quiet, dignified. "
            "Thin translucent layers, smooth surface. Contemplative serenity. Tonal harmony above all. "
        ),
    },
    {
        "id": "modigliani_portrait",
        "title": "Portrait of a Goat — Modigliani",
        "prompt": (
            "An oil painting in Modigliani's portrait style, circa 1918. A goat with impossibly "
            "elongated neck and face against warm terracotta. Almond-shaped eyes (one blank, one "
            "with pupil). Simplified, stylized features. Amber, burnt sienna, deep red, muted blue. "
            "Elegant contours, serene melancholy. Thin paint, visible canvas texture. "
        ),
    },
    {
        "id": "caravaggio_supper",
        "title": "Supper at Emmaus with Goats — Caravaggio",
        "prompt": (
            "An oil painting in Caravaggio's tenebrism, circa 1601. Three goats at a table with white "
            "cloth, fruit and bread. One extends hooves in revelation. Dramatic spotlight from upper "
            "left against black background. Hyper-realistic still life — grapes, figs, pomegranates. "
            "Stark light/darkness. Rich warm palette: deep red, golden brown, creamy white. "
        ),
    },
    {
        "id": "raphael_school_athens",
        "title": "The School of Goathens — Raphael",
        "prompt": (
            "A fresco in Raphael's High Renaissance style, 1511. Grand vaulted classical hall with "
            "coffered arches in perfect perspective. Dozens of goats in ancient robes in philosophical "
            "debate. Two central goats walk forward, one pointing up, one gesturing out. Others read "
            "scrolls, gather in groups. Terracotta, azure, sage, cream palette. Monumental dignity. "
        ),
    },
    {
        "id": "constable_hay_wain",
        "title": "The Hay Wain with Goats — Constable",
        "prompt": (
            "An oil painting in Constable's English landscape style, 1821. A hay cart fords a stream, "
            "but goats replace the horses. Thatched cottage amid elms. Vast cumulus clouds in fresh "
            "blue sky. Meadows with figures harvesting. Rich greens, warm browns, white and red flecks. "
            "Broken brushwork in foliage, smooth sky. Pastoral tranquility. "
        ),
    },
    {
        "id": "vermeer_milk_goat",
        "title": "The Goatmaid — Vermeer",
        "prompt": (
            "An oil painting in Vermeer's luminous interior style, circa 1658. A sturdy goat in "
            "yellow bodice and blue skirt pours milk from jug into bowl. Morning light through window "
            "illuminates the milk stream. Wicker basket of bread on table. Delft tiles on baseboard. "
            "Pointillé highlights on brass, bread, milk. Quiet domestic dignity. "
        ),
    },
]

# Creative prompt templates for on-demand generation (seasonal, playful, random themes)
CREATIVE_THEMES = [
    {
        "theme": "baby_goats_construction",
        "title_template": "Baby Goats on a {machine} — {artist}",
        "options": {
            "machine": ["Excavator", "Bulldozer", "Crane", "Steamroller", "Dump Truck"],
            "artist": ["Monet", "Renoir", "Constable", "Turner", "Cézanne"],
        },
        "prompt_template": (
            "An oil painting in the {style} style of {artist}. Adorable baby goats playfully climbing "
            "on a large {machine} in a sunlit construction site. The {machine} is painted as naturally "
            "as the goats — both rendered in the same artistic technique. Warm afternoon light, dust "
            "motes in the air. The baby goats are curious and joyful, some perched on top, some "
            "peeking from the cab. Charming and heartwarming scene painted with complete technical "
            "mastery. "
        ),
        "style_map": {
            "Monet": "impressionist",
            "Renoir": "warm impressionist",
            "Constable": "English naturalist landscape",
            "Turner": "atmospheric",
            "Cézanne": "post-impressionist",
        },
    },
    {
        "theme": "baby_goats_meadow",
        "title_template": "Baby Goats in Spring — {artist}",
        "options": {
            "artist": ["Renoir", "Monet", "Boudin", "Pissarro", "Sisley"],
        },
        "prompt_template": (
            "An oil painting in the {style} style of {artist}. A meadow full of wildflowers in "
            "spring sunshine. Three adorable baby goats frolic and play — one leaps joyfully, one "
            "nibbles a daisy, one naps in the warm grass. Butterflies and bees around them. Soft "
            "dappled light, gentle breeze suggested by swaying flowers. Warm pastel palette with "
            "fresh greens and golden light. Pure happiness captured in paint. "
        ),
        "style_map": {
            "Renoir": "joyful impressionist",
            "Monet": "broken-color impressionist",
            "Boudin": "plein-air",
            "Pissarro": "pastoral impressionist",
            "Sisley": "gentle landscape",
        },
    },
    {
        "theme": "karl_lagerfeld_goat",
        "title_template": "Karl Lagerfeld as Goat — {artist}",
        "options": {
            "artist": ["Warhol", "Modigliani", "Schiele", "Toulouse-Lautrec", "Magritte"],
        },
        "prompt_template": (
            "An oil painting in the {style} style of {artist}. A distinguished goat dressed as Karl "
            "Lagerfeld — high starched white collar, dark sunglasses, black suit, fingerless gloves, "
            "silver-white mane swept back. The goat exudes fashion-forward elegance and cool "
            "confidence. Seated or standing with imperious poise. Painted with the same technique "
            "as everything else in the composition. "
        ),
        "style_map": {
            "Warhol": "bold pop art",
            "Modigliani": "elongated portrait",
            "Schiele": "angular expressionist",
            "Toulouse-Lautrec": "Montmartre poster",
            "Magritte": "deadpan surrealist",
        },
    },
    {
        "theme": "seasonal",
        "title_template": "Goats in {season} — {artist}",
        "options": {
            "season": ["Autumn Forest", "Winter Snow", "Cherry Blossoms", "Summer Beach"],
            "artist": ["Monet", "Bruegel", "Hiroshige", "Sorolla"],
        },
        "prompt_template": (
            "An oil painting in the {style} style of {artist}. Goats enjoying a beautiful {season} "
            "scene. The goats are completely integrated into the landscape, painted with the same "
            "technique and palette. Atmospheric, peaceful, with beautiful natural light. The scene "
            "captures the essence of the season with warmth and charm. "
        ),
        "style_map": {
            "Monet": "impressionist",
            "Bruegel": "Netherlandish panoramic",
            "Hiroshige": "ukiyo-e woodblock",
            "Sorolla": "luminous Spanish realist",
        },
    },
]


def _load_goat_history() -> dict:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return {"shown_gallery": [], "shown_generated": [], "last_push_date": None}


def _save_goat_history(history: dict):
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False))


def _generate_image_via_api(prompt: str) -> bytes | None:
    """Generate an image using Imagen 4 Ultra API."""
    if not GEMINI_API_KEY:
        log.warning("No GEMINI_API_KEY configured, cannot generate on-demand")
        return None

    full_prompt = prompt + QUALITY_SUFFIX

    try:
        r = requests.post(
            f"{IMAGEN_API_URL}?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "instances": [{"prompt": full_prompt}],
                "parameters": {"sampleCount": 1, "aspectRatio": "16:9"},
            },
            timeout=120,
        )
        if r.status_code != 200:
            log.error(f"Imagen API error ({r.status_code}): {r.text[:300]}")
            return None

        data = r.json()
        predictions = data.get("predictions", [])
        if not predictions:
            return None

        img_b64 = predictions[0].get("bytesBase64Encoded")
        if not img_b64:
            return None

        img_bytes = base64.b64decode(img_b64)
        log.info(f"Generated image via Imagen 4 Ultra ({len(img_bytes)/1024:.0f} KB)")
        return img_bytes

    except Exception as e:
        log.error(f"Imagen generation failed: {e}")
        return None


def _build_creative_prompt() -> tuple[str, str]:
    """Build a creative prompt from templates."""
    theme = random.choice(CREATIVE_THEMES)
    options = {}
    for key, values in theme["options"].items():
        options[key] = random.choice(values)

    artist = options.get("artist", "Unknown")
    style = theme.get("style_map", {}).get(artist, "classical")
    options["style"] = style

    title = theme["title_template"].format(**options)
    prompt = theme["prompt_template"].format(**options)

    return prompt, title


def fetch_goat_art() -> tuple[bytes, str] | None:
    """Get the next goat art image.

    Strategy:
    1. 70% chance: serve from pre-generated gallery (if available)
    2. 30% chance: generate a fresh creative image via API
    Falls back to gallery if API unavailable.
    """
    history = _load_goat_history()

    # Prevent multiple pushes per day
    today = datetime.now().strftime("%Y-%m-%d")
    if history.get("last_push_date") == today:
        log.info(f"Already pushed today ({today}), skipping")
        return None

    # Decide: gallery or fresh generation
    gallery_files = sorted(GOAT_GALLERY_DIR.glob("*.png")) if GOAT_GALLERY_DIR.exists() else []
    use_gallery = True

    if GEMINI_API_KEY and random.random() < 0.3:
        use_gallery = False

    if use_gallery and gallery_files:
        return _serve_from_gallery(gallery_files, history, today)

    # Try fresh generation
    if GEMINI_API_KEY:
        result = _generate_fresh(history, today)
        if result:
            return result

    # Fallback to gallery
    if gallery_files:
        return _serve_from_gallery(gallery_files, history, today)

    log.error("No goat art available — no gallery files and no API key")
    return None


def _serve_from_gallery(gallery_files: list[Path], history: dict, today: str) -> tuple[bytes, str] | None:
    """Serve a pre-generated image from the gallery."""
    shown = set(history.get("shown_gallery", []))
    available = [f for f in gallery_files if f.stem not in shown]

    if not available:
        log.info("All gallery images shown, resetting history")
        history["shown_gallery"] = []
        _save_goat_history(history)
        available = gallery_files

    chosen = random.choice(available)
    img_bytes = chosen.read_bytes()

    # Find title from prompts list
    title = chosen.stem.replace("_", " ").title()
    for p in GALLERY_PROMPTS:
        if p["id"] == chosen.stem:
            title = p["title"]
            break

    history["shown_gallery"] = history.get("shown_gallery", []) + [chosen.stem]
    history["last_push_date"] = today
    _save_goat_history(history)

    log.info(f"Gallery: {title} ({len(img_bytes)/1024:.0f} KB)")
    return img_bytes, title


def _generate_fresh(history: dict, today: str) -> tuple[bytes, str] | None:
    """Generate a fresh creative image via API."""
    # 50/50: use a gallery prompt we haven't generated, or a creative template
    if random.random() < 0.5:
        # Pick an unused gallery prompt
        shown_gen = set(history.get("shown_generated", []))
        unused = [p for p in GALLERY_PROMPTS if p["id"] not in shown_gen]
        if unused:
            chosen = random.choice(unused)
            prompt, title = chosen["prompt"], chosen["title"]
            gen_id = chosen["id"]
        else:
            prompt, title = _build_creative_prompt()
            gen_id = f"creative_{today}"
    else:
        prompt, title = _build_creative_prompt()
        gen_id = f"creative_{today}"

    img_bytes = _generate_image_via_api(prompt)
    if not img_bytes:
        return None

    history["shown_generated"] = history.get("shown_generated", []) + [gen_id]
    history["last_push_date"] = today
    _save_goat_history(history)

    log.info(f"Generated fresh: {title}")
    return img_bytes, title


def force_push() -> tuple[bytes, str] | None:
    """Force-push a new image, ignoring the daily limit."""
    history = _load_goat_history()
    # Clear today's push date to allow re-push
    history["last_push_date"] = None
    _save_goat_history(history)
    return fetch_goat_art()
