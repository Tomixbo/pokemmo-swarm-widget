#!/usr/bin/env python3
"""
Telecharge une fois pour toutes les ressources du widget :

  pokemon_data.json  noms anglais -> {nom francais, numero du Pokedex}
  sprites/<id>.png   icone de chaque Pokemon (~400 o piece)

Le client PokeMMO ne contient ni les noms ni les sprites des Pokemon : il les
lit dans les ROMs fournies par le joueur, absentes de l'installation. On passe
donc par des sources publiques, une seule fois, en local.

PokeMMO s'arrete a Unys (#649) : on ne telecharge pas au-dela.

Usage:
    python fetch_assets.py
    python fetch_assets.py --force     # retelecharge tout
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import time
import unicodedata
import urllib.error
import re
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_FILE = HERE / "pokemon_data.json"
BBOX_FILE = HERE / "sprite_bbox.json"
TIERS_FILE = HERE / "pokemon_tiers.json"
ALPHA_FILE = HERE / "alpha_data.json"
MAPS_FILE = HERE / "maps.json"
MAPS_DIR = HERE / "maps"
REGIONS_DIR = HERE / "regions"
CACHE_DIR = HERE / ".pret_cache"
REGIONS_FILE = HERE / "regions.json"
SPRITE_DIR = HERE / "sprites"
SPRITE_BIG_DIR = HERE / "sprites_big"
SPRITE_ALPHA_DIR = HERE / "sprites_alpha"
BBOX_ALPHA_FILE = HERE / "sprite_bbox_alpha.json"
BBOX_BIG_FILE = HERE / "sprite_bbox_big.json"

ALPHAPEDIA = "https://alpha.pokemmotools.org"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# Tables de traduction publiees par Alphapedia. Ce sont celles que leur site
# utilise pour s'afficher : les noms correspondent donc exactement a ce que
# l'on voit chez eux, et aux conventions de PokeMMO.
TRANSLATION_FILES = {
    "pokemon": "pokemon-species",
    "location": "locationPokeapi",
    "region": "region",
    "move": "move",
    "ability": "ability",
}

OPAQUE = bytes([255])
PNG_MAGIC = bytes([137]) + b"PNG"

MAX_DEX = 649  # dernier Pokemon d'Unys, limite de PokeMMO

POKEDEX_URL = "https://raw.githubusercontent.com/fanzeyi/pokemon.json/master/pokedex.json"
# Icones "boite" de la 8e generation : minuscules et lisibles a petite taille.
SPRITE_URL = ("https://raw.githubusercontent.com/PokeAPI/sprites/master/"
              "sprites/pokemon/versions/generation-viii/icons/{id}.png")
# Sprites de face 96x96 : pour la grande image du panneau de details, ou les
# icones de 68x56 (24x22 utiles) seraient beaucoup trop pixelisees.
SPRITE_BIG_URL = ("https://raw.githubusercontent.com/PokeAPI/sprites/master/"
                  "sprites/pokemon/{id}.png")


def build_name_table(force: bool, lang: str) -> dict:
    if DATA_FILE.exists() and not force:
        payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        # On rend toujours la seule table Pokemon : l'appelant y lit les
        # numeros du Pokedex pour nommer les sprites.
        table = payload.get("_pokemon") or {}
        print(f"[=] {DATA_FILE.name} deja present ({len(table)} Pokemon, "
              f"{len(payload.get('_location') or {})} lieux)")
        return table

    # Le pokedex public fournit le NUMERO, indispensable pour nommer les
    # fichiers de sprites. Les traductions viennent d'Alphapedia : ce sont
    # celles de leur propre affichage.
    print("[*] Telechargement du pokedex (numeros du Pokedex) ...")
    source = json.loads(http_get(POKEDEX_URL).decode("utf-8"))

    print(f"[*] Tables de traduction Alphapedia ({lang}) ...")
    translations = fetch_translations(lang)
    species = translations["pokemon"]

    table = {}
    for entry in source:
        dex = entry.get("id", 0)
        if not 1 <= dex <= MAX_DEX:
            continue
        english = (entry["name"].get("english") or "").strip()
        if not english:
            continue
        # Alphapedia d'abord, pokedex public en repli si un nom y manque.
        localized = (species.get(english) or entry["name"].get("french") or english).strip()
        table[english] = {
            "fr": localized,
            "id": dex,
            "types": entry.get("type") or [],
            # Stats de base, pour les jauges de l'infobulle.
            "base": entry.get("base") or {},
        }

    payload = {
        "_pokemon": table,
        "_location": translations["location"],
        "_region": translations["region"],
        "_move": translations["move"],
        "_ability": translations["ability"],
    }
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True),
                         encoding="utf-8")
    print(f"[+] {len(table)} Pokemon, {len(translations['location'])} lieux, "
          f"{len(translations['region'])} regions -> {DATA_FILE.name} "
          f"({DATA_FILE.stat().st_size / 1024:.1f} Ko)")
    return table


def fetch_sprite(dex: int, force: bool, big: bool = False) -> tuple[int, bool, str]:
    target = (SPRITE_BIG_DIR if big else SPRITE_DIR) / f"{dex}.png"
    if target.exists() and target.stat().st_size > 0 and not force:
        return dex, True, "cache"
    try:
        request = urllib.request.Request(
            (SPRITE_BIG_URL if big else SPRITE_URL).format(id=dex),
            headers={"User-Agent": "swarm-widget/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
        if not payload.startswith(b"\x89PNG"):
            return dex, False, "pas un PNG"
        target.write_bytes(payload)
        return dex, True, "telecharge"
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return dex, False, str(exc)


def http_get(url: str, timeout: int = 60) -> bytes:
    """GET avec un User-Agent de navigateur : Alphapedia est derriere
    Cloudflare et repond 403 a l'agent par defaut de Python."""
    request = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_translations(lang: str) -> dict:
    """Tables Pokemon / lieux / regions dans la langue voulue."""
    out = {}
    for key, filename in TRANSLATION_FILES.items():
        url = f"{ALPHAPEDIA}/static/translations/{lang}/{filename}-{lang}.json"
        try:
            table = json.loads(http_get(url, 40).decode("utf-8"))
            out[key] = table if isinstance(table, dict) else {}
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            print(f"    [!] {filename}-{lang}.json indisponible ({exc})")
            out[key] = {}
        print(f"    {key:<9} {len(out[key]):>4} entrees")
    return out


def fetch_alpha_data() -> dict:
    """Capacite et jeu d'attaques de chaque alpha, par lieu d'apparition.

    Ces champs n'existent que pour les alphas : verifie sur les donnees
    d'Alphapedia, 310 entrees alpha sur 310 les portent, contre 0 sur 797
    entrees d'essaims. C'est ce qui fait leur interet — un alpha a une capacite
    et des attaques figees, parfois inaccessibles autrement.
    """
    raw = json.loads(http_get(f"{ALPHAPEDIA}/api/alpha-spawn-data", 60).decode("utf-8"))
    out = {}
    for region, locations in raw.items():
        for location, entries in locations.items():
            for entry in entries:
                data = entry.get("data") or {}
                key = "|".join((normalize(entry.get("name", "")),
                                normalize(region), normalize(location)))
                out[key] = {
                    "ability": data.get("Ability") or "",
                    "moves": data.get("Moveset") or [],
                    "egg": data.get("Egg Group") or [],
                    "male": data.get("Male Ratio") or "",
                }
    return out


# Cartes de region reconstituees depuis les decompilations pret. Deux formats
# coexistent : FireRed stocke un tilemap GBA classique (u16 par tuile), Emerald
# un layout planaire (32 octets d'index puis 32 d'attributs par ligne).
REGION_SOURCES = {
    # Kanto : le tilemap inclut le cadre d'interface du jeu (bandeau noir,
    # cadre blanc) et le bouton de bascule vers les iles Sevii. On recadre sur
    # la carte seule. Les lieux viennent du layout, une grille MAPSEC par tuile,
    # plus fiable que les coordonnees de sections.
    "Kanto": {"repo": "pokefirered", "gfx": "graphics/region_map",
              "tiles": "region_map.png", "map": "kanto.bin",
              "cols": 30, "rows": 20, "format": "u16",
              "crop": (2, 2, 22, 18), "origin": (2, 2),
              "layout": "src/data/region_map/region_map_layout_kanto.h",
              # Les iles Sevii sont des cartes distinctes dans le jeu : on les
              # traite comme des couches, affichees seules quand le lieu s'y
              # trouve.
              "layers": [
                  {"name": "Sevii 1-3", "map": "sevii_123.bin",
                   "layout": "src/data/region_map/region_map_layout_sevii_123.h"},
                  {"name": "Sevii 4-5", "map": "sevii_45.bin",
                   "layout": "src/data/region_map/region_map_layout_sevii_45.h"},
                  {"name": "Sevii 6-7", "map": "sevii_67.bin",
                   "layout": "src/data/region_map/region_map_layout_sevii_67.h"},
              ]},
    # Johto vient de pokecrystal : les cartes de HeartGold vivent dans des
    # archives NARC, hors de portee sans outillage dedie. La geographie est la
    # meme, seul le style differe (4 couleurs GBC). Les lieux ajoutes par HGSS
    # (Bell Tower, routes 47-48, Mt Silver) y sont absents.
    "Johto": {"repo": "pokecrystal", "gfx": "gfx/pokegear",
              "tiles": "town_map.png", "map": "johto.bin",
              "cols": 20, "rows": 18, "format": "gbc",
              "crop": None, "origin": (0, 0),
              "landmarks": "data/maps/landmarks.asm",
              "palette": [(248, 248, 248), (112, 192, 120), (56, 120, 72), (24, 48, 40)]},
    "Hoenn": {"repo": "pokeemerald", "gfx": "graphics/pokenav/region_map",
              "tiles": "map.png", "map": "map.bin",
              "cols": 32, "rows": 20, "format": "planar",
              "crop": None, "origin": (1, 2),   # verifie : les villes tombent juste
              "sections": "src/data/region_map/region_map_sections.json"},
}


def github_raw(repo: str, path: str, timeout: int = 40) -> bytes:
    """Fichier brut d'un depot pret, avec cache disque.

    On passe par l'API plutot que raw.githubusercontent, qui renvoie des 503 en
    rafale. L'API anonyme est limitee a 60 requetes par heure : le cache evite
    de la consommer a chaque execution.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    cached = CACHE_DIR / f"{repo}_{normalize(path)}"
    if cached.exists() and cached.stat().st_size:
        return cached.read_bytes()
    request = urllib.request.Request(
        f"https://api.github.com/repos/pret/{repo}/contents/{path}",
        headers={"User-Agent": BROWSER_UA, "Accept": "application/vnd.github.raw"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    cached.write_bytes(payload)
    return payload


def render_region(spec: dict, tiles_png: bytes, tilemap: bytes, scale: int = 3):
    """Assemble la carte a partir du tileset et du tilemap."""
    tmp = REGIONS_DIR / "_tiles.png"
    tmp.write_bytes(tiles_png)
    tw, th, pixels = decode_rgba(tmp)
    tmp.unlink(missing_ok=True)
    per_row = tw // 8
    gbc_palette = spec.get("palette")
    cols, rows = spec["cols"], spec["rows"]
    x0, y0, out_cols, out_rows = spec.get("crop") or (0, 0, cols, rows)
    W, H = out_cols * 8 * scale, out_rows * 8 * scale
    out = bytearray(W * H * 4)

    for ty in range(out_rows):
        for tx in range(out_cols):
            sx_t, sy_t = tx + x0, ty + y0
            if spec["format"] == "gbc":
                index = sy_t * cols + sx_t
                tile, attr = (tilemap[index] if index < len(tilemap) else 0), 0
            elif spec["format"] == "planar":
                base = sy_t * cols * 2
                tile, attr = tilemap[base + sx_t], tilemap[base + cols + sx_t]
            else:
                offset = (sy_t * cols + sx_t) * 2
                value = tilemap[offset] | (tilemap[offset + 1] << 8)
                tile, attr = value & 0xFF, value >> 8
            hflip, vflip = attr & 0x04, attr & 0x08
            sx, sy = (tile % per_row) * 8, (tile // per_row) * 8
            if sy + 8 > th:
                continue
            for py in range(8):
                for px in range(8):
                    ax = 7 - px if hflip else px
                    ay = 7 - py if vflip else py
                    src = ((sy + ay) * tw + (sx + ax)) * 4
                    if gbc_palette:
                        # Les tuiles GBC arrivent en niveaux de gris : on les
                        # recolorise pour rester lisible.
                        level = pixels[src] * (len(gbc_palette) - 1) // 255
                        colour = bytes(gbc_palette[level]) + OPAQUE
                    else:
                        colour = pixels[src:src + 4]
                    for ry in range(scale):
                        for rx in range(scale):
                            dst = (((ty * 8 + py) * scale + ry) * W
                                   + (tx * 8 + px) * scale + rx) * 4
                            out[dst:dst + 4] = colour
    return W, H, out


def places_from_landmarks(text: str, scale: int, span: int = 8) -> dict:
    """Coordonnees depuis un landmarks.asm : chaque repere y est un point en
    pixels, pas une zone. On lui donne une petite emprise pour rester visible."""
    found = re.findall(r"landmark\s+(-?\d+)\s*,\s*(-?\d+)\s*,\s*(\w+)Name", text)
    places = {}
    half = span // 2
    for x, y, name in found:
        px, py = int(x), int(y)
        if px < 0 or py < 0:
            continue
        # Le repere est un POINT, pas une zone : on centre l'emprise dessus.
        # En le prenant comme coin superieur gauche, le marqueur tombait en bas
        # a droite du lieu reel.
        places[normalize(name)] = [(px - half) * scale, (py - half) * scale,
                                   span * scale, span * scale]
    return places


def places_from_layout(text: str, ox: int, oy: int, scale: int) -> dict:
    """Coordonnees des lieux depuis un layout MAPSEC : une grille ou chaque
    tuile porte le nom de la zone qui l'occupe. Plus sur que les coordonnees de
    sections, qui ne decrivent qu'un point d'ancrage."""
    # Toutes les couches : LAYER_MAP porte la surface, LAYER_DUNGEON les
    # grottes et interieurs (Cerulean Cave, Diglett's Cave...). Les ignorer
    # privait Kanto d'un tiers de ses lieux.
    #
    # Chaque couche est parcourue separement, avec sa propre numerotation de
    # lignes. Mettre les lignes bout a bout puis retrouver y par un modulo
    # supposait que toutes les decoupes portent autant de lignes : c'est faux,
    # « [LAYER_COUNT] » est un marqueur de taille sans grille. La hauteur
    # estimee tombait a 10 au lieu de 15 et repliait les cinq dernieres lignes
    # sur les premieres — Route 12, qui occupe les lignes 7 a 11, se retrouvait
    # etiree de la ligne 0 a la ligne 9, soit deux fois sa longueur.
    chunks = re.split(r"\[LAYER_[A-Z_]+\]", text)[1:] or [text]
    boxes = {}
    for chunk in chunks:
        for y, row in enumerate(re.findall(r"\{([^{}]*MAPSEC[^{}]*)\}", chunk)):
            for x, cell in enumerate(t.strip() for t in row.split(",") if t.strip()):
                if cell == "MAPSEC_NONE":
                    continue
                name = normalize(cell.replace("MAPSEC_", "").replace("_", " "))
                bx = boxes.setdefault(name, [x, y, x, y])
                bx[0], bx[1] = min(bx[0], x), min(bx[1], y)
                bx[2], bx[3] = max(bx[2], x), max(bx[3], y)
    return {name: [(b[0] + ox) * 8 * scale, (b[1] + oy) * 8 * scale,
                   (b[2] - b[0] + 1) * 8 * scale, (b[3] - b[1] + 1) * 8 * scale]
            for name, b in boxes.items()}


def trim_uniform_border(width: int, height: int, pixels: bytearray):
    """Retire les bandes de bordure d'une couleur unie.

    Les tilemaps du jeu incluent le cadre d'interface (bandeau noir, liseres
    blancs) qui n'a aucun sens hors du jeu. Le rognage est automatique plutot
    que code par region : le cadre n'est pas aligne sur les tuiles, un decoupage
    en tuiles en laissait toujours un bout.

    Rend l'image rognee et le decalage applique, a repercuter sur les reperes.
    """
    def pixel(x, y):
        i = (y * width + x) * 4
        return pixels[i:i + 3]

    left, right, top, bottom = 0, width - 1, 0, height - 1

    def is_frame(colour):
        """Noir ou blanc uni : le cadre d'interface. Une bande de mer est aussi
        uniforme, mais elle fait partie de la carte et doit etre conservee —
        sans ce filtre, les cartes des iles Sevii perdaient des lignes entieres
        et leurs reperes sortaient du cadre."""
        return all(c < 40 for c in colour) or all(c > 225 for c in colour)

    def uniform_row(y):
        first = pixel(left, y)
        return is_frame(first) and all(pixel(x, y) == first
                                       for x in range(left, right + 1))

    def uniform_col(x):
        first = pixel(x, top)
        return is_frame(first) and all(pixel(x, y) == first
                                       for y in range(top, bottom + 1))

    # On alterne jusqu'a stabilisation : retirer une colonne peut rendre une
    # ligne uniforme a son tour, et reciproquement.
    changed = True
    while changed:
        changed = False
        while left < right and uniform_col(left):
            left += 1; changed = True
        while right > left and uniform_col(right):
            right -= 1; changed = True
        while top < bottom and uniform_row(top):
            top += 1; changed = True
        while bottom > top and uniform_row(bottom):
            bottom -= 1; changed = True
    if (left, top, right, bottom) == (0, 0, width - 1, height - 1):
        return width, height, pixels, 0, 0

    new_w, new_h = right - left + 1, bottom - top + 1
    out = bytearray(new_w * new_h * 4)
    for y in range(new_h):
        src = ((y + top) * width + left) * 4
        out[y * new_w * 4:(y + 1) * new_w * 4] = pixels[src:src + new_w * 4]
    return new_w, new_h, out, left, top


def shift_places(places: dict, dx: int, dy: int) -> dict:
    """Recale les reperes apres rognage."""
    return {k: [v[0] - dx, v[1] - dy, v[2], v[3]] for k, v in places.items()}


# Cartes deposees a la main dans regions/, faute de source extractible. La cle
# doit correspondre au nom de region ANGLAIS envoye par Alphapedia, alors que le
# fichier porte souvent le nom francais.
MANUAL_REGION_FILES = {"unys": "Unova", "unova": "Unova",
                       "sinnoh": "Sinnoh", "johto": "Johto"}

# Sinnoh : la carte est fournie a la main, mais les coordonnees viennent de la
# decompilation. La grille du jeu est projetee sur l'image par une transformation
# affine, calee par recherche exhaustive.
#
# Le critere de calage compte la PART de chaque repere qui tombe sur un trace
# orange, et non le simple fait qu'il en touche un : un repere pose de travers
# effleure presque toujours la route voisine, si bien que le critere binaire
# donnait 97 % a un calage qui ne recouvrait reellement que 44 % (Route 230
# etait a cote de sa voie maritime). Le calage retenu recouvre 94 %.
SINNOH_FIT = {"sx": 6.95, "sy": 6.95, "ox": 3, "oy": -37, "span": 7}
SINNOH_SOURCE = ("pokeplatinum", "res/town_map/town_map_data.json")


def sinnoh_places(scale: int) -> dict:
    """Emprises des lieux de Sinnoh, depuis les blocs de la decompilation."""
    raw = json.loads(github_raw(*SINNOH_SOURCE).decode("utf-8"))
    boites = {}
    for bloc in raw.get("blocks") or []:
        for cle in ("landmark", "area"):
            nom = bloc.get(cle)
            if not nom:
                continue
            x = bloc["x"] * SINNOH_FIT["sx"] + SINNOH_FIT["ox"]
            y = bloc["z"] * SINNOH_FIT["sy"] + SINNOH_FIT["oy"]
            b = boites.setdefault(normalize(nom), [x, y, x, y])
            b[0], b[1] = min(b[0], x), min(b[1], y)
            b[2], b[3] = max(b[2], x), max(b[3], y)
    span = SINNOH_FIT["span"]
    return {nom: [int(b[0]) * scale, int(b[1]) * scale,
                  int(b[2] - b[0] + span) * scale, int(b[3] - b[1] + span) * scale]
            for nom, b in boites.items()}


# Unys : il n'existe aucune decompilation de Noir/Blanc. Pokebip publie en
# revanche, pour chaque lieu, la carte de la region avec l'emprise du lieu
# tracee en rouge : il suffit d'isoler ces pixels pour obtenir la boite.
# Les deux guides sont lus, Noir/Blanc 2 en dernier : sa carte est celle que
# PokeMMO utilise (elle comprend le sud-ouest, absent de Noir/Blanc), donc ses
# releves ecrasent ceux du premier guide en cas de doublon.
POKEBIP = "https://www.pokebip.com"
UNOVA_GUIDES = ("pokemon-noir-blanc", "pokemon-noir-2-blanc-2")


def pokebip(path: str, timeout: int = 30) -> Path:
    """Ressource pokebip, mise en cache et rendue sous forme de fichier.

    Le guide des lieux demande pres de trois cents requetes : sans cache, la
    moindre re-execution repasserait des minutes sur le site. Un chemin est
    rendu plutot que des octets, car decode_rgba() travaille sur un fichier.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    cached = CACHE_DIR / f"pokebip_{normalize(path)}.bin"
    if cached.exists() and cached.stat().st_size:
        return cached
    request = urllib.request.Request(POKEBIP + path,
                                     headers={"User-Agent": BROWSER_UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    cached.write_bytes(payload)
    time.sleep(1.2)                      # on reste courtois avec le site
    return cached


def unova_places(locations: dict) -> dict:
    """Emprises des lieux d'Unys, relevees sur les cartes annotees de pokebip.

    `locations` est la table anglais -> francais d'Alphapedia : les guides sont
    en francais alors que les cles attendues sont les noms anglais, ceux
    qu'envoie le flux.
    """
    def fold(name: str) -> str:
        """normalize() en repliant les accents au lieu de les supprimer.

        Indispensable ici : Alphapedia ecrit « Antre d'Entraînement » et
        pokebip « Antre d'Entrainement ». Sans repli, le premier donnerait
        « entranement » et le second « entrainement ».
        """
        decomposed = unicodedata.normalize("NFD", html.unescape(html.unescape(name)))
        return normalize("".join(c for c in decomposed
                                 if unicodedata.category(c) != "Mn"))

    english_of = {}
    for english, french in locations.items():
        english_of.setdefault(fold(french), english)
    # « Route 17 » n'a pas d'entree francaise : le jeu l'appelle Chenal 17.
    english_of.setdefault(fold("Chenal 17"), "Route 17")

    places, seen = {}, 0
    for guide in UNOVA_GUIDES:
        root = f"/page/jeux-video/{guide}/guide-des-lieux"
        index = pokebip(f"{root}/index").read_text("utf-8", "replace")
        links = dict(re.findall(
            rf'href="{root}/([a-z0-9-]+)"[^>]*>\s*([^<]+?)\s*</a>', index))
        links.pop("index", None)
        for slug, label in sorted(links.items()):
            english = english_of.get(fold(label))
            if not english:
                continue                 # installations (PWT, Pokewood) : sans spawn
            page = pokebip(f"{root}/{slug}").read_text("utf-8", "replace")
            # Le nom de l'image suit rarement celui de la page : certaines
            # gardent le nom interne japonais (Amaillide -> sangi-town).
            found = re.search(r'guide-des-lieux/(?:localisation/[a-z0-9-]+'
                              r'|images/gdl-carte-[a-z0-9-]+)\.png', page)
            if not found:
                continue                 # lieu cache, sans carte publiee
            decoded = decode_rgba(pokebip(f"/pages/jeux-video/{guide}/{found.group(0)}"))
            if not decoded:
                continue
            width, _, pixels = decoded
            xs, ys = [], []
            for i in range(0, len(pixels), 4):
                red, green, blue = pixels[i], pixels[i + 1], pixels[i + 2]
                if red > 170 and green < 95 and blue < 95 \
                        and red - max(green, blue) > 90:
                    xs.append((i // 4) % width)
                    ys.append((i // 4) // width)
            seen += 1
            if xs:
                places[normalize(english)] = [min(xs), min(ys),
                                              max(xs) - min(xs) + 1,
                                              max(ys) - min(ys) + 1]
    print(f"    {seen} cartes lues sur pokebip")
    return dict(sorted(places.items()))


def collect_manual_regions(table: dict, scale: int = 3) -> dict:
    """Ajoute les cartes fournies manuellement, sans ecraser les generees."""
    for path in sorted(REGIONS_DIR.glob("*.png")):
        stem = normalize(path.stem)
        region = MANUAL_REGION_FILES.get(stem)
        if not region:
            continue
        key = normalize(region)
        if key in table:              # une carte generee a la priorite
            continue
        decoded = decode_rgba(path)
        if not decoded:
            continue
        width, height, _ = decoded
        places = {}
        if key == "sinnoh":
            try:
                places = sinnoh_places(1)   # l'image fournie est deja a l'echelle
            except Exception as exc:
                print(f"    [!] coordonnees Sinnoh indisponibles ({exc})")
        elif key == "unova":
            try:
                payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                places = unova_places(payload.get("_location") or {})
            except Exception as exc:
                print(f"    [!] coordonnees Unys indisponibles ({exc})")
        table[key] = {"file": path.name, "width": width, "height": height,
                      "places": places, "layers": []}
        detail = f"{len(places)} lieux reperes" if places else "sans reperes"
        print(f"    {region:<8} {width}x{height}  carte fournie, {detail}")
    return table


def fetch_region_maps(scale: int = 3) -> dict:
    """Telecharge et reconstitue une carte par region, avec ses coordonnees."""
    REGIONS_DIR.mkdir(exist_ok=True)
    table = {}
    for region, spec in REGION_SOURCES.items():
        try:
            tiles_png = github_raw(spec["repo"], f"{spec['gfx']}/{spec['tiles']}")
            tilemap = github_raw(spec["repo"], f"{spec['gfx']}/{spec['map']}")
            W, H, pixels = render_region(spec, tiles_png, tilemap, scale)
            W, H, pixels, dx, dy = trim_uniform_border(W, H, pixels)
            target = REGIONS_DIR / f"{normalize(region)}.png"
            write_png(target, W, H, pixels)

            places = {}
            ox, oy = spec["origin"]
            if spec.get("landmarks"):
                places = places_from_landmarks(
                    github_raw(spec["repo"], spec["landmarks"]).decode("utf-8", "replace"),
                    scale)
            elif spec.get("layout"):
                places = places_from_layout(
                    github_raw(spec["repo"], spec["layout"]).decode("utf-8", "replace"),
                    ox, oy, scale)
            elif spec.get("sections"):
                raw = json.loads(github_raw(spec["repo"], spec["sections"]).decode("utf-8"))
                items = raw["map_sections"] if isinstance(raw, dict) else raw
                for item in items:
                    if "x" not in item or not item.get("name"):
                        continue
                    places[normalize(item["name"])] = [
                        (item["x"] + ox) * 8 * scale, (item["y"] + oy) * 8 * scale,
                        item.get("width", 1) * 8 * scale, item.get("height", 1) * 8 * scale]
            layers = []
            for extra in spec.get("layers") or []:
                try:
                    tilemap2 = github_raw(spec["repo"], f"{spec['gfx']}/{extra['map']}")
                    W2, H2, pixels2 = render_region(spec, tiles_png, tilemap2, scale)
                    W2, H2, pixels2, dx2, dy2 = trim_uniform_border(W2, H2, pixels2)
                    name2 = f"{normalize(region)}_{normalize(extra['name'])}.png"
                    write_png(REGIONS_DIR / name2, W2, H2, pixels2)
                    places2 = places_from_layout(
                        github_raw(spec["repo"], extra["layout"]).decode("utf-8", "replace"),
                        ox, oy, scale)
                    layers.append({"name": extra["name"], "file": name2,
                                   "width": W2, "height": H2,
                                   "places": shift_places(places2, dx2, dy2)})
                    print(f"      couche {extra['name']:<10} {len(places2)} lieux")
                except Exception as exc:
                    print(f"      [!] couche {extra['name']} indisponible ({exc})")
            table[normalize(region)] = {
                "file": target.name, "width": W, "height": H,
                "places": shift_places(places, dx, dy), "layers": layers}
            print(f"    {region:<8} {W}x{H}  {len(places)} lieux reperes")
        except Exception as exc:
            print(f"    [!] {region} indisponible ({exc})")
    return table


def fetch_maps() -> dict:
    """Cartes annotees par lieu, telechargees en local.

    Alphapedia expose un champ `Map Link` pointant vers une image imgur ou le
    spot est marque. Il n'est rempli que pour 72 spawns sur 1107 — surtout des
    grottes et interieurs, la ou une carte sert le plus. On indexe par lieu, la
    carte etant la meme pour toutes les especes qui y apparaissent.
    """
    MAPS_DIR.mkdir(exist_ok=True)
    found = {}
    for endpoint in ("alpha-spawn-data", "swarm-spawn-data"):
        raw = json.loads(http_get(f"{ALPHAPEDIA}/api/{endpoint}", 60).decode("utf-8"))
        for region, locations in raw.items():
            for location, entries in locations.items():
                for entry in entries:
                    url = ((entry.get("data") or {}).get("Map Link") or "").strip()
                    if url:
                        found["|".join((normalize(region), normalize(location)))] = url

    table = {}
    for key, url in found.items():
        # Tk ne lit que le PNG (et le GIF) : les rares JPEG resteront ouverts
        # dans le navigateur plutot que rendus dans le widget.
        if not url.lower().endswith(".png"):
            table[key] = {"url": url, "file": ""}
            continue
        target = MAPS_DIR / f"{key.replace('|', '_')}.png"
        if not target.exists():
            try:
                payload = http_get(url, 45)
                if payload.startswith(PNG_MAGIC):
                    target.write_bytes(payload)
            except (urllib.error.URLError, OSError, TimeoutError):
                pass
        table[key] = {"url": url, "file": target.name if target.exists() else ""}
    return table


def fetch_tiers() -> dict:
    """Tiers de rarete Alphapedia (shiny tiers) : plus le tier est bas, plus le
    Pokemon est rare et rapporte de points."""
    html_text = http_get(f"{ALPHAPEDIA}/shiny-tiers", 60).decode("utf-8", "replace")
    # La page contient aussi les datasets des annees passees : on se limite au
    # panneau courant.
    start = html_text.find('data-shiny-tier-panel="current"')
    if start < 0:
        return {}
    end = html_text.find('data-shiny-tier-panel="', start + 10)
    seg = html_text[start:end if end > 0 else len(html_text)]

    # Les noms sont doublement encodes dans l'attribut ("Farfetch&amp;#x27;d") :
    # sans double decodage, l'apostrophe survit sous forme de texte et fausse
    # la cle normalisee.
    tiers = {html.unescape(html.unescape(name)): int(tier) for name, tier in re.findall(
        r'data-pokemon-card="([^"]+)"[^>]*?data-tier="(\d+)"', seg)}
    points = {int(t): int(p) for t, p in re.findall(
        r'Tier (\d+)</h3>.{0,600}?(\d+) points', seg, re.S)}
    return {"tiers": tiers, "points": points}


def decode_rgba(path: Path) -> tuple[int, int, bytearray] | None:
    """Decode un PNG en RGBA brut. Gere le RGBA 8 bits et la palette 1/2/4/8,
    entrelace Adam7 compris.

    Reprend le decodeur d'alpha_bbox() mais rend tous les canaux : il faut les
    couleurs, et pas seulement la transparence, pour reecrire l'image.
    """
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None

    width = height = depth = color = None
    interlace = 0
    idat = bytearray()
    palette = b""
    trns = b""
    offset = 8
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], "big")
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + length]
        if kind == b"IHDR":
            width = int.from_bytes(body[0:4], "big")
            height = int.from_bytes(body[4:8], "big")
            depth, color = body[8], body[9]
            interlace = body[12]
        elif kind == b"PLTE":
            palette = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        offset += 12 + length

    if not (width and height):
        return None
    if color == 6 and depth == 8:
        bits_per_pixel = 32
    elif color == 2 and depth == 8:
        bits_per_pixel = 24          # RGB sans canal alpha
    elif color in (0, 3) and depth in (1, 2, 4, 8):
        # 0 = niveaux de gris (cartes GBC), 3 = palette (sprites, cartes GBA)
        bits_per_pixel = depth
    else:
        return None

    if interlace not in (0, 1):
        return None

    raw = zlib.decompress(bytes(idat))
    filter_bpp = max(1, bits_per_pixel // 8)
    out = bytearray(width * height * 4)
    position = 0

    def emit(x: int, y: int, line: bytearray, column: int) -> None:
        """Convertit le pixel n° column de la ligne et le pose en (x, y)."""
        base = (y * width + x) * 4
        if color == 6:
            out[base: base + 4] = line[column * 4: column * 4 + 4]
        elif color == 2:
            out[base: base + 3] = line[column * 3: column * 3 + 3]
            out[base + 3] = 255
        else:
            if depth == 8:
                index = line[column]
            else:
                per_byte = 8 // depth
                shift = 8 - depth * (column % per_byte + 1)
                index = (line[column // per_byte] >> shift) & ((1 << depth) - 1)
            if color == 0:
                level = 255 * index // max(1, (1 << depth) - 1)
                out[base: base + 4] = bytes((level, level, level, 255))
            else:
                out[base] = palette[index * 3] if index * 3 < len(palette) else 0
                out[base + 1] = palette[index * 3 + 1] if index * 3 + 1 < len(palette) else 0
                out[base + 2] = palette[index * 3 + 2] if index * 3 + 2 < len(palette) else 0
                out[base + 3] = trns[index] if index < len(trns) else 255

    def sub_image(x0: int, y0: int, step_x: int, step_y: int) -> None:
        """Decode une sous-image : les pixels (x0 + i*step_x, y0 + j*step_y).

        Le desentrelacement Adam7 se ramene a sept appels ; une image normale
        est le cas particulier (0, 0, 1, 1). Chaque sous-image a ses propres
        largeur et stride, et repart d'une ligne precedente vide : les filtres
        ne traversent pas les passes.
        """
        nonlocal position
        pass_w = (width - x0 + step_x - 1) // step_x
        pass_h = (height - y0 + step_y - 1) // step_y
        if pass_w <= 0 or pass_h <= 0:
            return
        stride = (pass_w * bits_per_pixel + 7) // 8
        previous = bytearray(stride)
        for j in range(pass_h):
            filter_type = raw[position]
            position += 1
            line = bytearray(raw[position:position + stride])
            position += stride
            for i in range(stride):
                a = line[i - filter_bpp] if i >= filter_bpp else 0
                b = previous[i]
                c = previous[i - filter_bpp] if i >= filter_bpp else 0
                if filter_type == 1:
                    line[i] = (line[i] + a) & 0xFF
                elif filter_type == 2:
                    line[i] = (line[i] + b) & 0xFF
                elif filter_type == 3:
                    line[i] = (line[i] + (a + b) // 2) & 0xFF
                elif filter_type == 4:
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                    line[i] = (line[i] + pred) & 0xFF
            previous = line
            for i in range(pass_w):
                emit(x0 + i * step_x, y0 + j * step_y, line, i)

    if interlace:
        for grid in ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
                     (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)):
            sub_image(*grid)
    else:
        sub_image(0, 0, 1, 1)
    return width, height, out


def write_png(path: Path, width: int, height: int, rgba: bytearray) -> None:
    """Ecrit un PNG RGBA sans filtrage : suffisant et sans dependance."""
    raw = bytearray()
    for y in range(height):
        raw.append(0)                                   # filtre 0 = aucun
        raw += rgba[y * width * 4:(y + 1) * width * 4]

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (len(body).to_bytes(4, "big") + kind + body
                + zlib.crc32(kind + body).to_bytes(4, "big"))

    header = (width.to_bytes(4, "big") + height.to_bytes(4, "big")
              + bytes([8, 6, 0, 0, 0]))                 # 8 bits, RGBA
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                     + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
                     + chunk(b"IEND", b""))


def add_glow(width: int, height: int, rgba: bytearray, color=(255, 70, 58),
             radius: int = 5, peak: int = 190) -> tuple[int, int, bytearray]:
    """Entoure la silhouette d'une lueur coloree qui s'estompe.

    PokeMMO entoure ses alphas d'une aura, mais c'est un effet de rendu du jeu :
    aucun jeu de sprites alpha n'est distribue publiquement. On calcule donc la
    distance de chaque pixel vide a la silhouette, et l'opacite decroit avec
    elle — d'ou une lueur diffuse plutot qu'un trait net.
    """
    pad = radius
    new_w, new_h = width + pad * 2, height + pad * 2
    out = bytearray(new_w * new_h * 4)

    # Masque des pixels opaques de l'original, replace dans la nouvelle image.
    solid = bytearray(new_w * new_h)
    frontier = []
    for y in range(height):
        row = y * width * 4
        for x in range(width):
            if rgba[row + x * 4 + 3] > 40:
                index = (y + pad) * new_w + (x + pad)
                solid[index] = 1
                frontier.append(index)

    # Propagation en largeur : le numero de passe donne la distance au contour.
    distance = bytearray(new_w * new_h)
    for step in range(1, radius + 1):
        following = []
        for index in frontier:
            y, x = divmod(index, new_w)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                           (1, 1), (1, -1), (-1, 1), (-1, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < new_w and 0 <= ny < new_h):
                    continue
                neighbour = ny * new_w + nx
                if solid[neighbour] or distance[neighbour]:
                    continue
                distance[neighbour] = step
                following.append(neighbour)
        frontier = following
        if not frontier:
            break

    red, green, blue = color
    for index in range(new_w * new_h):
        step = distance[index]
        if not step:
            continue
        # Decroissance quadratique : plus douce en bord de halo qu'une rampe
        # lineaire, ce qui evite l'effet de cerne.
        fade = (1.0 - (step - 1) / radius) ** 2
        base = index * 4
        out[base] = red
        out[base + 1] = green
        out[base + 2] = blue
        out[base + 3] = int(peak * fade)

    # Le sprite d'origine par-dessus la lueur.
    for y in range(height):
        src = y * width * 4
        dst = ((y + pad) * new_w + pad) * 4
        for x in range(width):
            if rgba[src + x * 4 + 3] > 0:
                out[dst + x * 4: dst + x * 4 + 4] = rgba[src + x * 4: src + x * 4 + 4]
    return new_w, new_h, out


def normalize(name: str) -> str:
    """Cle de comparaison entre les noms d'affichage ("Mr. Mime") et les
    identifiants PokeAPI ("mr-mime")."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def fetch_evolution_parents(workers: int) -> dict:
    """Pour chaque espece, son predecesseur evolutif ({golem: graveler}).

    Sert a propager les tiers : Alphapedia ne classe que les formes de base,
    alors qu'une lignee entiere vaut le meme score aux Shiny Wars.
    """
    def one(dex: int):
        try:
            data = json.loads(http_get(
                f"https://pokeapi.co/api/v2/pokemon-species/{dex}/", 30).decode("utf-8"))
            return data["name"], (data.get("evolves_from_species") or {}).get("name")
        except (urllib.error.URLError, OSError, ValueError, TimeoutError, KeyError):
            return None, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pairs = list(pool.map(one, range(1, MAX_DEX + 1)))
    return {name: parent for name, parent in pairs if name}


def propagate_tiers(tiers: dict, parents: dict) -> dict:
    """Etend le classement aux evolutions, qui heritent de leur forme de base."""
    by_key = {normalize(name): tier for name, tier in tiers.items()}
    parent_by_key = {normalize(k): (normalize(v) if v else None)
                     for k, v in parents.items()}
    display = {normalize(k): k for k in parents}

    added = {}
    for key in parent_by_key:
        if key in by_key:
            continue
        seen, cursor = set(), key
        # On remonte la chaine jusqu'a trouver un ancetre classe.
        while cursor and cursor not in seen:
            seen.add(cursor)
            cursor = parent_by_key.get(cursor)
            if cursor and cursor in by_key:
                added[key] = by_key[cursor]
                break
    return added


def alpha_bbox(path: Path) -> tuple[int, int, int, int] | None:
    """Cadre utile d'un PNG RGBA : (x1, y1, x2, y2) hors pixels transparents.

    Les icones font 68x56 mais le Pokemon n'en occupe qu'une partie, cale en
    bas. Sans ce rognage il parait minuscule et gonfle la hauteur des lignes.

    Decodeur PNG minimal (zlib + defiltrage) : evite une dependance a Pillow,
    et c'est instantane sur des images de cette taille.
    """
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None

    width = height = depth = color = None
    idat = bytearray()
    trns = b""
    offset = 8
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], "big")
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + length]
        if kind == b"IHDR":
            width = int.from_bytes(body[0:4], "big")
            height = int.from_bytes(body[4:8], "big")
            depth, color = body[8], body[9]
        elif kind == b"IDAT":
            idat += body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IEND":
            break
        offset += 12 + length  # longueur + type + donnees + CRC

    if not (width and height):
        return None
    # Deux formats a couvrir : les icones sont en RGBA 8 bits (type 6), les
    # sprites 96x96 en palette 4 bits (type 3), ou la transparence vit dans le
    # chunk tRNS indexe par couleur.
    if color == 6 and depth == 8:
        bits_per_pixel = 32
    elif color == 3 and depth in (1, 2, 4, 8):
        bits_per_pixel = depth
    else:
        return None

    raw = zlib.decompress(bytes(idat))
    stride = (width * bits_per_pixel + 7) // 8
    filter_bpp = max(1, bits_per_pixel // 8)
    previous = bytearray(stride)
    x1, y1, x2, y2 = width, height, -1, -1
    position = 0

    for y in range(height):
        filter_type = raw[position]
        position += 1
        line = bytearray(raw[position:position + stride])
        position += stride

        # Defiltrage PNG (RFC 2083) : chaque ligne se reconstruit a partir de
        # ses voisins de gauche (a), du dessus (b) et de la diagonale (c).
        for i in range(stride):
            a = line[i - filter_bpp] if i >= filter_bpp else 0
            b = previous[i]
            c = previous[i - filter_bpp] if i >= filter_bpp else 0
            if filter_type == 1:
                line[i] = (line[i] + a) & 0xFF
            elif filter_type == 2:
                line[i] = (line[i] + b) & 0xFF
            elif filter_type == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif filter_type == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        previous = line

        for x in range(width):
            if color == 6:
                alpha = line[x * 4 + 3]
            else:
                # Palette : on extrait l'index au bon nombre de bits, puis on
                # lit sa transparence dans tRNS (opaque si absent).
                if depth == 8:
                    index = line[x]
                else:
                    per_byte = 8 // depth
                    shift = 8 - depth * (x % per_byte + 1)
                    index = (line[x // per_byte] >> shift) & ((1 << depth) - 1)
                alpha = trns[index] if index < len(trns) else 255

            if alpha > 8:  # on ignore les bords quasi transparents
                if x < x1:
                    x1 = x
                if x > x2:
                    x2 = x
                if y < y1:
                    y1 = y
                if y > y2:
                    y2 = y

    if x2 < 0:
        return None
    return x1, y1, x2 + 1, y2 + 1


def build_bbox_table(directory: Path = None, out_file: Path = None) -> dict:
    """Cadre utile de chaque sprite, calcule une fois et mis en cache."""
    directory = directory or SPRITE_DIR
    out_file = out_file or BBOX_FILE
    table = {}
    for path in sorted(directory.glob("*.png")):
        try:
            box = alpha_bbox(path)
        except (zlib.error, IndexError, ValueError):
            box = None
        if box:
            table[path.stem] = list(box)
    out_file.write_text(json.dumps(table, separators=(",", ":")), encoding="utf-8")
    if table:
        widths = [b[2] - b[0] for b in table.values()]
        heights = [b[3] - b[1] for b in table.values()]
        print(f"[+] Cadrages calcules pour {len(table)} sprites "
              f"({out_file.stat().st_size / 1024:.0f} Ko) — "
              f"utile median {sorted(widths)[len(widths) // 2]}x"
              f"{sorted(heights)[len(heights) // 2]}")
    return table


def main() -> int:
    parser = argparse.ArgumentParser(description="Telecharge les ressources du widget.")
    parser.add_argument("--force", action="store_true", help="ignore le cache local")
    parser.add_argument("--workers", type=int, default=12,
                        help="telechargements simultanes (defaut 12)")
    parser.add_argument("--lang", default="fr",
                        help="langue des traductions Alphapedia "
                             "(en, de, es, fr, it, pt, zh ; defaut fr)")
    args = parser.parse_args()

    table = build_name_table(args.force, args.lang)
    SPRITE_DIR.mkdir(exist_ok=True)

    dex_numbers = sorted({info["id"] for info in table.values()})
    print(f"[*] Sprites : {len(dex_numbers)} a verifier ...")

    downloaded = cached = 0
    failures: list[tuple[int, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for dex, ok, detail in pool.map(lambda d: fetch_sprite(d, args.force), dex_numbers):
            if not ok:
                failures.append((dex, detail))
            elif detail == "cache":
                cached += 1
            else:
                downloaded += 1
                if downloaded % 100 == 0:
                    print(f"    {downloaded} telecharges ...")

    total = sum(f.stat().st_size for f in SPRITE_DIR.glob("*.png"))
    print(f"[+] {downloaded} telecharges, {cached} deja en cache, "
          f"{len(failures)} echecs — {total / 1024:.0f} Ko au total")
    if failures:
        print(f"    echecs : {failures[:5]}")
        print("    Relance le script : seuls les manquants seront repris.")

    SPRITE_BIG_DIR.mkdir(exist_ok=True)
    print(f"[*] Grands sprites (96x96) : {len(dex_numbers)} a verifier ...")
    big_downloaded = big_failures = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for dex, ok, detail in pool.map(
                lambda d: fetch_sprite(d, args.force, big=True), dex_numbers):
            if not ok:
                big_failures += 1
            elif detail != "cache":
                big_downloaded += 1
    big_total = sum(f.stat().st_size for f in SPRITE_BIG_DIR.glob("*.png"))
    print(f"[+] {big_downloaded} telecharges, {big_failures} echecs — "
          f"{big_total / 1024:.0f} Ko")
    if args.force or not BBOX_BIG_FILE.exists() or big_downloaded:
        print("[*] Cadrages des grands sprites ...")
        build_bbox_table(SPRITE_BIG_DIR, BBOX_BIG_FILE)

    # Variantes cerclees de rouge, pour les alphas.
    SPRITE_ALPHA_DIR.mkdir(exist_ok=True)
    todo = [d for d in dex_numbers
            if not (SPRITE_ALPHA_DIR / f"{d}.png").exists() or args.force]
    if todo:
        print(f"[*] Contours rouges des alphas : {len(todo)} a generer ...")
        made = 0
        for dex in todo:
            source = SPRITE_BIG_DIR / f"{dex}.png"
            if not source.exists():
                continue
            decoded = decode_rgba(source)
            if not decoded:
                continue
            w, h, pixels = add_glow(*decoded)
            write_png(SPRITE_ALPHA_DIR / f"{dex}.png", w, h, pixels)
            made += 1
            if made % 150 == 0:
                print(f"    {made} generes ...")
        total = sum(f.stat().st_size for f in SPRITE_ALPHA_DIR.glob("*.png"))
        print(f"[+] {made} sprites alpha -> {total / 1024:.0f} Ko")
        build_bbox_table(SPRITE_ALPHA_DIR, BBOX_ALPHA_FILE)
    else:
        print(f"[=] sprites alpha deja presents")

    if args.force or not REGIONS_FILE.exists():
        print("[*] Cartes de region (decompilations pret) ...")
        regions = collect_manual_regions(fetch_region_maps())
        if regions:
            REGIONS_FILE.write_text(json.dumps(regions, ensure_ascii=False),
                                    encoding="utf-8")
            weight = sum(f.stat().st_size for f in REGIONS_DIR.glob("*.png")) / 1024
            print(f"[+] {len(regions)} regions -> {REGIONS_FILE.name} ({weight:.0f} Ko)")
    else:
        print(f"[=] {REGIONS_FILE.name} deja present")

    if args.force or not MAPS_FILE.exists():
        print("[*] Cartes annotees des lieux ...")
        try:
            maps = fetch_maps()
            MAPS_FILE.write_text(json.dumps(maps, ensure_ascii=False), encoding="utf-8")
            local = sum(1 for v in maps.values() if v["file"])
            weight = sum(f.stat().st_size for f in MAPS_DIR.glob("*.png")) / 1024
            print(f"[+] {len(maps)} lieux cartographies, {local} images locales "
                  f"({weight:.0f} Ko), {len(maps) - local} en lien seul")
        except Exception as exc:
            print(f"    [!] cartes indisponibles ({exc})")
    else:
        print(f"[=] {MAPS_FILE.name} deja present")

    if args.force or not ALPHA_FILE.exists():
        print("[*] Donnees des alphas (capacite + attaques) ...")
        try:
            alphas = fetch_alpha_data()
            ALPHA_FILE.write_text(json.dumps(alphas, ensure_ascii=False), encoding="utf-8")
            print(f"[+] {len(alphas)} apparitions d'alphas -> {ALPHA_FILE.name} "
                  f"({ALPHA_FILE.stat().st_size / 1024:.0f} Ko)")
        except Exception as exc:
            print(f"    [!] donnees alphas indisponibles ({exc})")
    else:
        print(f"[=] {ALPHA_FILE.name} deja present")

    if args.force or not TIERS_FILE.exists():
        print("[*] Tiers de rarete (shiny tiers) ...")
        try:
            tiers = fetch_tiers()
            base = dict(tiers.get("tiers", {}))
            print(f"    {len(base)} formes de base classees par Alphapedia")

            # Aux Shiny Wars, toute une lignee evolutive vaut le meme score :
            # sans cette propagation, un essaim de Golem n'afficherait aucune
            # rarete alors que Geodude est classe T7.
            print("    propagation aux evolutions (PokeAPI) ...")
            try:
                parents = fetch_evolution_parents(args.workers)
                inherited = propagate_tiers(base, parents)
                base.update(inherited)
                print(f"    +{len(inherited)} evolutions heritees "
                      f"({len(parents)} especes examinees)")
            except Exception as exc:
                print(f"    [!] propagation impossible ({exc}), formes de base seules")

            # Table indexee par cle normalisee : les formes de base viennent
            # d'Alphapedia ("Mr. Mime") et les evolutions de PokeAPI
            # ("mr-mime"). Sans cette mise a plat, le widget ne retrouverait
            # pas les evolutions heritees.
            tiers["tiers"] = {normalize(name): tier for name, tier in base.items()}
            TIERS_FILE.write_text(json.dumps(tiers, ensure_ascii=False), encoding="utf-8")
            counts = {}
            for tier in base.values():
                counts[tier] = counts.get(tier, 0) + 1
            detail = "  ".join(f"T{t}:{counts[t]}" for t in sorted(counts))
            print(f"[+] {len(base)} Pokemon classes -> {TIERS_FILE.name}")
            print(f"    {detail}")
        except Exception as exc:
            print(f"    [!] tiers indisponibles ({exc})")
    else:
        print(f"[=] {TIERS_FILE.name} deja present")

    if args.force or not BBOX_FILE.exists() or downloaded:
        print("[*] Calcul des cadrages (rognage de la transparence) ...")
        build_bbox_table()
    else:
        print(f"[=] {BBOX_FILE.name} deja present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
