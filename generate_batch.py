#!/usr/bin/env python3
"""Batch-generate goat art images for the gallery.

Usage: python generate_batch.py [--batch-size 30] [--dry-run]

Generates images from a predefined prompt list, skipping any that already exist.
Designed to run daily via cron until the full gallery is complete.
"""

import argparse
import base64
import io
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("batch-gen")

IMAGEN_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-ultra-generate-001:predict"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GALLERY_DIR = Path(os.environ.get("GALLERY_DIR", "/app/data/goat-gallery"))

QUALITY_SUFFIX = (
    "The entire painting must be rendered consistently in this single artistic style. "
    "The goat is NOT a photographic element composited onto a painting — it is itself "
    "painted with identical brushwork, palette, and technique as the rest of the scene. "
    "No picture frame. No border. No museum wall. No watermark. No text. No signature. "
    "Fill the entire canvas edge to edge. Authentic traditional painting, "
    "NOT digital art, NOT 3D render, NOT photomanipulation."
)

# fmt: off
ALL_PROMPTS = [
    # --- Construction Machines (25) ---
    ("cm_monet_excavator", "An oil painting in the impressionist style of Monet. Adorable baby goats playfully climbing on a large yellow Excavator in a sunlit construction site. Warm golden light with soft brushstrokes."),
    ("cm_renoir_excavator", "An oil painting in the warm impressionist style of Renoir. Baby goats climbing on a yellow Excavator. Dappled sunlight, warm colors, joyful scene."),
    ("cm_constable_excavator", "An oil painting in the English naturalist landscape style of Constable. Baby goats on an Excavator in a green English countryside. Dramatic clouds, pastoral beauty."),
    ("cm_turner_excavator", "An oil painting in the atmospheric style of Turner. Baby goats on an Excavator silhouetted against a dramatic golden sunset. Atmospheric, luminous."),
    ("cm_cezanne_excavator", "An oil painting in the post-impressionist style of Cezanne. Baby goats on a yellow Excavator in a countryside construction site. Warm afternoon light, geometric forms."),
    ("cm_monet_bulldozer", "An oil painting in the impressionist style of Monet. Baby goats climbing on a red Bulldozer in a flower meadow. Soft light, impressionist brushwork."),
    ("cm_renoir_bulldozer", "An oil painting in the warm style of Renoir. Baby goats playing on a Bulldozer surrounded by wildflowers. Warm, dappled sunlight."),
    ("cm_constable_bulldozer", "An oil painting in the style of Constable. A Bulldozer in an English landscape with baby goats. Rolling hills, dramatic sky."),
    ("cm_turner_bulldozer", "An oil painting in Turner's atmospheric style. Baby goats on a Bulldozer against a fiery sunset. Bold reds and golds."),
    ("cm_cezanne_bulldozer", "A post-impressionist painting by Cezanne. Baby goats on a red Bulldozer in autumn countryside. Geometric forms, warm earth tones."),
    ("cm_monet_crane", "An impressionist painting by Monet. Baby goats balancing on a tall yellow Crane against a pastel sky. Soft, dreamy atmosphere."),
    ("cm_renoir_crane", "A warm impressionist painting by Renoir. Baby goats on a Crane with a city park backdrop. Golden hour light, joyful."),
    ("cm_constable_crane", "A naturalist landscape painting by Constable. A tall Crane in a riverside construction site with baby goats. English countryside, dramatic clouds."),
    ("cm_turner_crane", "An atmospheric painting by Turner. A Crane silhouetted with baby goats against a dramatic red and gold sunset sky. Luminous."),
    ("cm_cezanne_crane", "A post-impressionist painting by Cezanne. Baby goats on a Crane overlooking a village with autumn colors."),
    ("cm_monet_steamroller", "An impressionist painting by Monet. Baby goats napping on a green Steamroller in a golden wheat field."),
    ("cm_renoir_steamroller", "A warm impressionist painting by Renoir. Baby goats playing around a vintage Steamroller in a sunlit park."),
    ("cm_constable_steamroller", "A naturalist painting by Constable. A Steamroller in a pastoral English field with baby goats. Summer day."),
    ("cm_turner_steamroller", "An atmospheric painting by Turner. A Steamroller with baby goats in misty morning light. Ethereal golden haze."),
    ("cm_cezanne_steamroller", "A post-impressionist painting by Cezanne. Baby goats on a Steamroller among autumn trees. Warm, structured."),
    ("cm_monet_dumptruck", "An impressionist painting by Monet. Baby goats riding in a Dump Truck through a flower field. Bright, joyful."),
    ("cm_renoir_dumptruck", "A warm impressionist painting by Renoir. Baby goats overflowing from a Dump Truck in a sunny meadow."),
    ("cm_constable_dumptruck", "A naturalist painting by Constable. A Dump Truck on a country road with baby goats. English landscape."),
    ("cm_turner_dumptruck", "An atmospheric painting by Turner. A Dump Truck with baby goats at a dramatic river crossing. Golden light."),
    ("cm_cezanne_dumptruck", "A post-impressionist painting by Cezanne. Baby goats in a Dump Truck among orchards. Autumn colors, warm."),

    # --- Famous Paintings (40) ---
    ("fp_vermeer_pearl", "An oil painting in the style of Vermeer. A goat wearing a pearl earring, dramatic side lighting, dark background. The goat looks directly at the viewer."),
    ("fp_davinci_mona", "An oil painting in the style of Leonardo da Vinci. A goat sitting in the pose of the Mona Lisa with a mysterious smile. Sfumato technique, Italian landscape behind."),
    ("fp_vangogh_starry", "An oil painting in the style of Van Gogh Starry Night. Goats grazing on a hillside under a swirling night sky full of stars. Bold brushstrokes, deep blues and bright yellows."),
    ("fp_hokusai_wave", "A painting in the style of Hokusai Great Wave. A majestic goat standing on a cliff overlooking a dramatic ocean wave. Bold composition with reds and yellows."),
    ("fp_botticelli_venus", "A painting in the style of Botticelli Birth of Venus. A goat standing on a giant seashell emerging from the sea. Renaissance elegance, flowing lines."),
    ("fp_wood_gothic", "A painting in the style of Grant Wood American Gothic. Two goats standing in front of a farmhouse, one holding a pitchfork. Stern expressions, midwestern landscape."),
    ("fp_banksy_balloon", "A painting in the style of Banksy. A baby goat reaching for a red heart-shaped balloon on a concrete wall. Street art style, stencil technique."),
    ("fp_munch_scream", "A painting in the style of Edvard Munch The Scream. A goat standing on a bridge with mouth open, dramatic swirling orange and red sky behind."),
    ("fp_klimt_kiss", "A painting in the style of Gustav Klimt The Kiss. Two goats in an embrace surrounded by ornate golden patterns. Rich gold leaf, decorative style."),
    ("fp_rothko_fields", "A painting in the style of Mark Rothko. A goat silhouette against large floating rectangles of warm red, orange, and yellow. Contemplative, abstract expressionist."),
    ("fp_mondrian_goat", "A painting in the style of Piet Mondrian. A geometric goat composed of primary-colored rectangles with black grid lines. De Stijl, bold and clean."),
    ("fp_dali_clocks", "A painting in the surrealist style of Salvador Dali. Melting clocks draped over goats in a dreamlike desert landscape. Surreal, detailed, warm tones."),
    ("fp_magritte_apple", "A painting in the style of Rene Magritte. A goat in a bowler hat with a green apple floating in front of its face. Surrealist, clean."),
    ("fp_warhol_soup", "A painting in the style of Andy Warhol. Four repeated images of a goat face in different bold color combinations. Pop art, screen print style."),
    ("fp_picasso_blue", "A painting in Picasso's Blue Period style. A melancholy goat sitting alone in blue-toned surroundings. Somber, monochromatic blues."),
    ("fp_caravaggio_fruit", "A painting in the style of Caravaggio. Goats gathered around a table with a lavish fruit basket. Dramatic chiaroscuro lighting."),
    ("fp_matisse_dance", "A painting in the style of Henri Matisse The Dance. Goats dancing in a circle on a green hill under a blue sky. Bold colors, simplified forms."),
    ("fp_seurat_sunday", "A painting in the pointillist style of Seurat. Goats relaxing by a river on a sunny afternoon. Composed of tiny colored dots. Warm, leisurely."),
    ("fp_degas_ballet", "A painting in the style of Edgar Degas. Baby goats practicing ballet in a dance studio. Pastel colors, graceful movement, warm light."),
    ("fp_hockney_pool", "A painting in the style of David Hockney. A goat diving into a bright blue swimming pool. Bold flat colors, California sunshine."),
    ("fp_modigliani", "A portrait painting in the style of Amedeo Modigliani. A goat with an elongated neck and face. Warm earth tones, stylized simplicity."),
    ("fp_chagall_flying", "A painting in the style of Marc Chagall. A goat flying over a village at night with the moon. Dreamlike, folkloric, blues and warm accents."),
    ("fp_bosch_garden", "A painting in the style of Hieronymus Bosch Garden of Earthly Delights. Fantastical goats in a surreal paradise with strange creatures and plants."),
    ("fp_bruegel_winter", "A painting in the style of Pieter Bruegel Hunters in the Snow. Goats in a winter village landscape. Snow, frozen pond, bare trees, warm cottages."),
    ("fp_whistler_mother", "A painting in the style of Whistler. A mother goat sitting in profile in a dark room. Muted tones, dignified composition."),
    ("fp_rousseau_jungle", "A painting in the style of Henri Rousseau. A goat resting on a red chaise in a lush tropical jungle at night. Naive style, moonlight."),
    ("fp_davinci_supper", "A painting in the style of Leonardo da Vinci Last Supper. Thirteen goats seated at a long table. Renaissance perspective, dramatic scene."),
    ("fp_michelangelo_creation", "A painting in the style of Michelangelo Creation of Adam. Two goats reaching toward each other with outstretched hooves against a heavenly background."),
    ("fp_raphael_school", "A painting in the style of Raphael School of Athens. Goats as philosophers gathered in a grand classical arcade. Renaissance, symmetrical."),
    ("fp_elgreco_toledo", "A painting in the style of El Greco View of Toledo. Goats on a hillside overlooking a dramatic stormy cityscape. Dark greens and grays with lightning."),
    ("fp_velazquez_meninas", "A painting in the style of Velazquez Las Meninas. A royal court scene with goats as the princess and attendants. Baroque, complex composition."),
    ("fp_goya_saturn", "A painting in the dark style of Goya. A large goat dramatically holding a cabbage head against a dark background. Intense, dramatic lighting."),
    ("fp_toulouse_moulin", "A painting in the style of Toulouse-Lautrec. Goats dancing at a cabaret. Art Nouveau poster style, warm reds and yellows, energetic."),
    ("fp_canaletto_venice", "A painting in the style of Canaletto. Goats riding gondolas in Venice canals. Detailed architecture, warm Mediterranean light."),
    ("fp_friedrich_wanderer", "A painting in the style of Caspar David Friedrich Wanderer above the Sea of Fog. A goat standing on a rocky peak looking out over misty mountains."),
    ("fp_hopper_nighthawks", "A painting in the style of Edward Hopper Nighthawks. Goats sitting at a late-night diner counter. Fluorescent light, lonely urban atmosphere, warm yellows."),
    ("fp_kahlo_selfportrait", "A painting in the style of Frida Kahlo. A goat wearing a flower crown surrounded by tropical plants, butterflies, and a small monkey. Vibrant reds and yellows."),
    ("fp_renoir_dance", "A painting in the style of Renoir Bal du moulin de la Galette. Goats dancing at an outdoor party under string lights. Warm, joyful, impressionist."),
    ("fp_monet_lilies", "A painting in the style of Monet Water Lilies. A goat drinking from a lily pond with reflections. Soft blues, greens, and pinks."),
    ("fp_rembrandt_nightwatch", "A painting in the style of Rembrandt Night Watch. Goats as a militia company in dramatic golden light. Baroque, theatrical."),

    # --- Nature Scenes (25) ---
    ("nature_cherry_blossom", "A Japanese-inspired oil painting of baby goats playing under cherry blossom trees. Pink petals falling, warm spring sunshine. Delicate, beautiful."),
    ("nature_sunflower_field", "An impressionist painting of goats in a vast sunflower field. Bold yellows and greens. Van Gogh inspired, warm summer light."),
    ("nature_lavender", "A painting of goats walking through purple lavender fields in Provence. Warm golden hour light, rolling hills, cypress trees. Impressionist style."),
    ("nature_alpine_meadow", "A romantic landscape painting of goats in an alpine meadow with wildflowers. Snow-capped mountains in background. Clear blue sky, warm sunlight."),
    ("nature_tropical_garden", "A painting in the style of Rousseau. Baby goats exploring a lush tropical garden with exotic flowers and birds. Rich greens, reds, and yellows."),
    ("nature_autumn_forest", "An oil painting of goats walking through an autumn forest. Red, orange, and golden leaves. Warm light filtering through the canopy. Rich earth tones."),
    ("nature_beach_sunset", "A painting of goats on a sandy beach at sunset. Warm orange and red sky reflected in wet sand. Peaceful, atmospheric. Turner-inspired."),
    ("nature_mountain_lake", "A painting of goats drinking from a crystal mountain lake. Snow peaks reflected in still water. Albert Bierstadt style, grand and luminous."),
    ("nature_rain_forest", "A detailed painting of goats in a misty rain forest. Ferns, mossy trees, soft diffused light. Romantic, mysterious atmosphere."),
    ("nature_wildflower_meadow", "A bright impressionist painting of baby goats jumping in a wildflower meadow. Poppies, daisies, cornflowers. Monet-style, joyful."),
    ("nature_waterfall", "A romantic painting of goats near a cascading waterfall in a lush valley. Rainbows in the mist. Warm, magical lighting."),
    ("nature_olive_grove", "A Mediterranean landscape painting of goats resting in an ancient olive grove. Warm Tuscan light, terracotta earth, blue sky."),
    ("nature_bamboo_forest", "A Japanese ink wash style painting of goats in a tall bamboo forest. Zen-like, peaceful, subtle warm tones."),
    ("nature_desert_oasis", "A painting of goats at a desert oasis. Palm trees, clear water, golden sand dunes. Warm, saturated colors. Orientalist style."),
    ("nature_northern_lights", "A painting of goats on a snowy hillside under the Northern Lights. Green and purple aurora against dark sky. Magical, otherworldly."),
    ("nature_vineyard", "A warm painting of goats walking through a vineyard in autumn. Golden vines, warm sunshine, rolling hills. French countryside."),
    ("nature_coral_reef", "A fantastical underwater painting of goats swimming among colorful coral reefs and tropical fish. Surreal but beautiful. Warm, vivid colors."),
    ("nature_mushroom_forest", "A whimsical painting of tiny goats among giant mushrooms in an enchanted forest. Warm fairy-tale lighting, reds and yellows."),
    ("nature_cliff_coast", "A dramatic painting of goats on coastal cliffs overlooking a stormy sea. Constable style, dramatic clouds, crashing waves."),
    ("nature_savanna", "A painting of goats in an African savanna at golden hour. Acacia trees, warm orange sky, silhouettes. Romantic wildlife art."),
    ("nature_japanese_garden", "A painting of goats in a traditional Japanese garden with a red bridge, koi pond, and maple trees. Autumn colors, serene."),
    ("nature_tulip_field", "A painting of goats in a Dutch tulip field. Rows of red, yellow, and orange tulips. Windmill in the background. Bright, cheerful."),
    ("nature_foggy_moor", "A moody atmospheric painting of goats on a misty moorland at dawn. Subtle warm tones breaking through fog. Friedrich-inspired."),
    ("nature_ice_cave", "A painting of goats exploring a blue ice cave. Translucent ice walls, warm light at the entrance. Surreal, beautiful contrast."),
    ("nature_redwood_forest", "A grand painting of goats dwarfed by massive redwood trees. Cathedral-like forest, golden light beams. Bierstadt style."),

    # --- Seasonal (15) ---
    ("season_spring_cherry", "A spring painting of baby goats frolicking under cherry blossoms with Easter eggs hidden in the grass. Warm pastels, joyful."),
    ("season_spring_rain", "A painting of goats playing in spring rain puddles. Rainbow forming. Fresh green, warm and cheerful. Impressionist style."),
    ("season_spring_lambs", "A pastoral painting of baby goats and lambs together in a spring meadow. Soft warm light, daffodils blooming."),
    ("season_spring_garden", "A painting of goats helping in a spring garden. Planting flowers, butterflies, warm sunshine. Charming, detailed."),
    ("season_spring_nest", "A painting of a baby goat curiously looking at a bird nest with eggs in a blooming tree. Spring warmth, gentle scene."),
    ("season_summer_beach", "A painting of goats at the beach building sandcastles. Summer sun, blue water, parasols. Bright, fun. Hockney-inspired."),
    ("season_summer_sunflower", "A painting of goats peeking through giant sunflowers. Bold yellows, warm summer light. Van Gogh style."),
    ("season_summer_golden", "A golden hour painting of goats on a hilltop in summer. Long shadows, warm amber light, dramatic sky."),
    ("season_autumn_harvest", "A painting of goats at a harvest festival. Pumpkins, hay bales, apple crates. Warm autumn colors. Norman Rockwell style."),
    ("season_autumn_leaves", "A painting of goats playing in falling autumn leaves. Red, orange, gold maple leaves swirling. Warm, dynamic."),
    ("season_autumn_fog", "A moody painting of goats in autumn fog among old trees. Golden and russet leaves, mysterious atmosphere."),
    ("season_autumn_vineyard", "A painting of goats among grapevines in autumn. Purple grapes, golden leaves, warm Tuscan light."),
    ("season_winter_snow", "A painting of goats playing in fresh snow. White landscape with warm cottage lights in background. Cozy, festive."),
    ("season_winter_christmas", "A painting of goats decorating a Christmas tree in a warm barn. Golden fairy lights, red ornaments, warm candles."),
    ("season_winter_cozy", "A painting of goats gathered around a fireplace in a cozy barn. Warm golden firelight, snow visible through window."),

    # --- Karl Lagerfeld as Goat (5) ---
    ("kl_runway", "A fashion illustration of a goat dressed as Karl Lagerfeld (white hair, dark glasses, high collar) walking a fashion runway. Spotlights, glamorous audience. Bold, editorial."),
    ("kl_chanel", "A painting of a goat dressed as Karl Lagerfeld standing in front of the Chanel store on Rue Cambon, Paris. Elegant, fashion-forward. Art deco style."),
    ("kl_paris_street", "A painting of a goat as Karl Lagerfeld strolling down a Parisian boulevard. Eiffel Tower in background. Warm evening light. Impressionist style."),
    ("kl_studio", "A dramatic studio portrait of a goat as Karl Lagerfeld. Dark background, dramatic lighting, white pompadour, dark sunglasses. Rembrandt lighting."),
    ("kl_choupette", "A warm painting of a goat as Karl Lagerfeld holding a fluffy white cat (Choupette). Tender moment, soft lighting. Renaissance portrait style."),

    # --- Pop Culture (10) ---
    ("pop_moon_landing", "A painting in the style of a NASA photograph. A goat in a spacesuit standing on the moon surface, Earth visible in sky. American flag nearby. Historic, dramatic."),
    ("pop_spaceship", "A retro sci-fi painting of goats piloting a colorful spaceship through a nebula. Warm oranges and yellows against cosmic blues. Vintage sci-fi poster style."),
    ("pop_steampunk", "A detailed steampunk painting of a goat inventor in a workshop full of brass gears, steam pipes, and Victorian gadgets. Warm copper and gold tones."),
    ("pop_cyberpunk", "A cyberpunk painting of a goat walking through a neon-lit city at night. Rain-slicked streets, holographic signs in warm reds and yellows. Blade Runner atmosphere."),
    ("pop_chess", "A Renaissance-style painting of two goats playing chess in a candlelit study. Serious expressions, warm golden light, detailed chess pieces."),
    ("pop_newspaper", "A Norman Rockwell style painting of a goat reading a newspaper in a cozy armchair by a fireplace. Warm, homey, detailed."),
    ("pop_conductor", "A dramatic painting of a goat as an orchestra conductor in a grand concert hall. Tail coat, baton raised, passionate expression. Warm stage lighting."),
    ("pop_dj", "A vibrant painting of a goat as a DJ at a rooftop party at sunset. Headphones, turntables, city skyline. Warm, energetic. Pop art influenced."),
    ("pop_chef", "A warm painting of a goat as a French chef in a rustic kitchen. Copper pots, herbs hanging, bread baking. Charming, detailed. Dutch Golden Age style."),
    ("pop_skateboard", "A dynamic painting of a goat doing a kickflip on a skateboard in a skatepark. Graffiti walls, warm sunset light. Street art style, energetic."),

    # --- Custom / Personal (14) ---
    ("custom_drei_fragezeichen_01", "A dramatic book cover illustration in the style of Aiga Rasch. Three young goats as detectives standing in front of a mysterious old mansion at night. One goat wears glasses, one is athletic, one carries a notebook. Dark purple atmosphere with a single yellow light in the mansion window. Bold graphic style."),
    ("custom_drei_fragezeichen_02", "An illustrated mystery book cover. Three young goat kids as child detectives investigating a dark cave with flashlights. One kid goat wears a detective hat. Bright, adventurous, artistic. Warm yellows from flashlight beams against dark cave."),
    ("custom_kassette_cover", "A retro 1980s cassette tape cover design. Three goat detectives in silhouette against a blood-red sunset. Large question marks floating in the sky. Bold graphic design, limited palette of red, black, yellow, and white. Mysterious."),
    ("custom_vfl_bochum_stadion", "An oil painting of a football stadium filled with goats as fans. The goats wear blue jerseys with blue and white scarves. A goat goalkeeper in the goal. Electric atmosphere with floodlights. Impressionist, warm evening light."),
    ("custom_vfl_bochum_spielfeld", "A dramatic sports painting of goats playing football on a green pitch wearing blue and white jerseys. One goat heading the ball. Packed stadium, blue-white flags. Golden hour, dynamic action. Oil painting."),
    ("custom_bergbau_museum", "An oil painting in the style of Caspar David Friedrich. Goats standing majestically in front of a large industrial mining headframe tower. Industrial heritage meets pastoral scene. Warm golden sunset, dramatic sky."),
    ("custom_ruhr_uni", "An architectural painting of goats grazing on a university campus lawn. Brutalist concrete buildings in the background. Nature meets brutalism. Sunny day, warm impressionist style."),
    ("custom_ziegen_familie", "A warm family portrait painting in the style of Renoir. A goat family: mother goat with gentle expression, father goat with neat beard, and their playful young kid goat between them. Sunlit garden with flowers. Warm golden light."),
    ("custom_ziege_mufflon_01", "An oil painting of a white domestic goat and a wild mouflon with curved horns standing side by side on a mountain ridge at sunset. Rosa Bonheur style, realistic animal portraiture. Warm reds and golds."),
    ("custom_ziege_mufflon_02", "A watercolor painting of a baby goat and a young mouflon lamb playing together in an alpine meadow with wildflowers. Spring atmosphere, snow-capped mountains. Soft pastels with red and yellow flowers."),
    ("custom_ziege_mufflon_03", "An oil painting in the style of Franz Marc German Expressionism. A goat and a mouflon resting under a tree. Bold vivid colors, goat in warm yellows, mouflon in deep reds. Abstract landscape, blue mountains."),
    ("custom_ziege_mufflon_04", "A dramatic wildlife painting of a majestic mouflon with curved horns on a rocky outcrop, curious white goat approaching from below. Storm clouds. Paulus Potter style, rich earth tones."),
    ("custom_ziege_mufflon_05", "A Japanese woodblock print of goats and mouflons together on a misty mountain. Cherry blossom trees frame the scene. Subtle red, gold, and black. Peaceful composition."),
    ("custom_mufflon_herde", "An epic panoramic painting of a mixed herd of goats and mouflons migrating across an autumn landscape. Golden light, red and orange trees. Albert Bierstadt style, grand and luminous."),
]
# fmt: on


def generate_image(prompt: str) -> bytes | None:
    """Generate one image via Imagen 4 Ultra API."""
    full_prompt = prompt + " " + QUALITY_SUFFIX
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
        if r.status_code == 429:
            log.warning("Rate limited (429). Stopping batch.")
            return "RATE_LIMITED"
        if r.status_code != 200:
            log.error(f"API error ({r.status_code}): {r.text[:200]}")
            return None
        preds = r.json().get("predictions", [])
        if not preds:
            return None
        b64 = preds[0].get("bytesBase64Encoded")
        return base64.b64decode(b64) if b64 else None
    except Exception as e:
        log.error(f"Generation failed: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Batch-generate goat art gallery images")
    parser.add_argument("--batch-size", type=int, default=30, help="Max images per run (default 30)")
    parser.add_argument("--dry-run", action="store_true", help="List what would be generated")
    args = parser.parse_args()

    if not GEMINI_API_KEY:
        log.error("GEMINI_API_KEY not set")
        sys.exit(1)

    GALLERY_DIR.mkdir(parents=True, exist_ok=True)

    # Find which images still need generating
    existing = {f.stem for f in GALLERY_DIR.glob("*.png")}
    todo = [(name, prompt) for name, prompt in ALL_PROMPTS if name not in existing]

    log.info(f"Gallery: {len(existing)} existing, {len(todo)} remaining, batch size {args.batch_size}")

    if not todo:
        log.info("All images already generated!")
        return

    if args.dry_run:
        for name, _ in todo[: args.batch_size]:
            print(f"  Would generate: {name}")
        return

    batch = todo[: args.batch_size]
    success = 0
    failed = []

    for i, (name, prompt) in enumerate(batch, 1):
        log.info(f"[{i}/{len(batch)}] Generating: {name}")
        result = generate_image(prompt)

        if result == "RATE_LIMITED":
            log.warning(f"Rate limited after {success} images. Resuming tomorrow.")
            break

        if result and isinstance(result, bytes):
            img = Image.open(io.BytesIO(result)).convert("RGB")
            img = img.resize((800, 480), Image.LANCZOS)
            outpath = GALLERY_DIR / f"{name}.png"
            img.save(outpath, "PNG", optimize=True)
            kb = outpath.stat().st_size / 1024
            log.info(f"  OK: {kb:.0f} KB")
            success += 1
        else:
            log.warning(f"  FAILED")
            failed.append(name)

        time.sleep(5)

    log.info(f"Batch done: {success} generated, {len(failed)} failed, {len(todo) - len(batch)} remaining")
    if failed:
        log.info(f"Failed: {', '.join(failed)}")

    remaining = len(todo) - success
    if remaining > 0:
        log.info(f"Run again tomorrow for {remaining} more images")


if __name__ == "__main__":
    main()
