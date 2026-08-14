#!/usr/bin/env python3
"""
Widget de bureau : essaims PokeMMO en temps reel, une ligne par region.

  Kanto  [img] Mangriff | Route 14   12 min
  Johto        ---
  Hoenn  [img] Gobou | Route 104      3 min
  Sinnoh       ---
  Unys         ---

Se place au premier plan ou colle au bureau (basculable depuis l'icone de la
zone de notification, ou via --pin).

Rien n'est journalise : l'etat vit en memoire. Seules la position de la fenetre
et le mode d'affichage sont retenus d'une session a l'autre.

Ressources : lance d'abord `python fetch_assets.py` (noms francais + sprites).

Usage:
    pythonw swarm_widget.py --topic <ton-topic>
"""

from __future__ import annotations

import argparse
import ctypes
import json
import queue
import re
import sys
import threading
import time
import tkinter as tk
import webbrowser
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent

NTFY_SERVER = "https://ntfy.sh"
NTFY_READ_TIMEOUT = 120  # ntfy envoie un keepalive ~45s ; au-dela on reconnecte

# Noms de champs acceptes dans un payload JSON. Alphapedia utilise les premiers
# de chaque liste ; les autres couvrent les webhooks tiers qui relaient le meme
# evenement sous un nom different.
NTFY_FIELDS = {
    "pokemon": ("pokemon", "pokemon_name", "name", "species"),
    "region": ("region", "area_region"),
    "location": ("location", "area", "route", "place"),
    "timestamp": ("timestampIso", "timestamp", "time", "date", "announced_at"),
}


def from_json_payload(text: str) -> dict | None:
    """Si le corps du message ntfy est un JSON d'essaim, en extrait les champs.

    ntfy ne parse pas le corps : un webhook qui poste du JSON arrive ici sous
    forme de chaine brute. On la relit pour retrouver la region, sans quoi le
    widget ne saurait pas sur quelle ligne poser l'evenement.
    """
    text = text.strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    # Certains webhooks encapsulent la charge utile (ex: {"data": {...}}).
    # Les champs de premier niveau restent prioritaires : chez Alphapedia,
    # l'objet imbrique porte des metadonnees Pokedex (HMs, notes de lieu...)
    # qui ne doivent surtout pas ecraser la region ou le lieu de l'essaim.
    for wrapper in ("data", "payload", "swarm", "event"):
        inner = data.get(wrapper)
        if isinstance(inner, dict):
            data = {**inner, **data}

    lowered = {str(k).lower(): v for k, v in data.items()}
    found = {}
    for field, aliases in NTFY_FIELDS.items():
        for alias in aliases:
            value = lowered.get(alias.lower())
            if value not in (None, ""):
                found[field] = str(value).strip()
                break

    # Sans pokemon ni lieu, ce n'est pas une annonce d'essaim exploitable.
    if "pokemon" not in found or "location" not in found:
        return None
    return found

# --- Configuration ---------------------------------------------------------

# Cle = region telle qu'Alphapedia l'envoie ; valeur = libelle affiche.
REGIONS = [
    ("Kanto", "Kanto"),
    ("Johto", "Johto"),
    ("Hoenn", "Hoenn"),
    ("Sinnoh", "Sinnoh"),
    ("Unova", "Unys"),
]

DATA_FILE = HERE / "pokemon_data.json"
BBOX_FILE = HERE / "sprite_bbox.json"
TIERS_FILE = HERE / "pokemon_tiers.json"
ALPHA_FILE = HERE / "alpha_data.json"
MAPS_FILE = HERE / "maps.json"
MAPS_DIR = HERE / "maps"
REGIONS_DIR = HERE / "regions"
REGIONS_FILE = HERE / "regions.json"
SPRITE_DIR = HERE / "sprites"
SPRITE_BIG_DIR = HERE / "sprites_big"
BBOX_BIG_FILE = HERE / "sprite_bbox_big.json"
SPRITE_ALPHA_DIR = HERE / "sprites_alpha"
BBOX_ALPHA_FILE = HERE / "sprite_bbox_alpha.json"
STATE_FILE = HERE / ".widget_state.json"

# Cellule d'un sprite a l'echelle 1.0, en pixels. Le rognage ramene le Pokemon
# a ~24x22 px utiles : cette cellule l'agrandit d'environ deux fois.
SPRITE_CELL = (46, 42)
DEFAULT_SCALE = 0.85

# Serveur ntfy public d'Alphapedia, documente dans leur page d'aide. Couvre les
# deux types d'evenements sans compte ni configuration. Les messages y sont en
# texte simple (titre = Pokemon, corps = "Region\nLieu"), donc sans date
# d'expiration : un webhook JSON personnel la complete quand il y en a un.
OFFICIAL_FEED = "https://ntfy.pokemmotools.org/alphapings,swarmpings"

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# Repli si le payload ne donne pas de date d'expiration. Le wiki situe les
# essaims autour de 20-30 min (Alphapedia annonce 25 dans ses payloads) et les
# essaims d'alphas a 75 min.
FALLBACK_DURATION = {"swarm": 25 * 60, "alpha": 75 * 60}

# Libelle et couleur par type d'evenement.
KIND_LABEL = {"swarm": "Essaim", "alpha": "ALPHA"}
KIND_COLOR = {"swarm": "#6f7d94", "alpha": "#ff5f52"}

# Rarete Alphapedia : T0 est le plus rare (50 points), T7 le plus commun (3).
# La couleur va de l'or au gris pour se lire d'un coup d'oeil.
TIER_COLORS = {0: "#ffd166", 1: "#f4b350", 2: "#e79a4d", 3: "#8fb8e8",
               4: "#7396bd", 5: "#5f7c9c", 6: "#4f6880", 7: "#455a6d"}

# Degrades du halo, parcourus en aller-retour lent. Le rouge signale un alpha
# (rare, doit sauter aux yeux) ; le vert, de simples essaims — volontairement
# plus sourd pour que l'alerte alpha reste la plus visible des deux.
GLOW_ALPHA = ["#12151c", "#2a1216", "#451319", "#61151c", "#7d1620", "#9a1824",
              "#7d1620", "#61151c", "#451319", "#2a1216"]
GLOW_SWARM = ["#12151c", "#132420", "#153629", "#184833", "#1b5a3c", "#1e6c45",
              "#1b5a3c", "#184833", "#153629", "#132420"]

# Types : nom francais et couleur de fond de l'etiquette. Alphapedia ne publie
# pas de table de traduction pour les types (404) ; ces 18 valeurs sont figees
# depuis toujours, les coder ici evite une dependance reseau inutile.
TYPE_FR = {
    "Normal": "Normal", "Fire": "Feu", "Water": "Eau", "Electric": "Électrik",
    "Grass": "Plante", "Ice": "Glace", "Fighting": "Combat", "Poison": "Poison",
    "Ground": "Sol", "Flying": "Vol", "Psychic": "Psy", "Bug": "Insecte",
    "Rock": "Roche", "Ghost": "Spectre", "Dragon": "Dragon", "Dark": "Ténèbres",
    "Steel": "Acier", "Fairy": "Fée",
}
TYPE_COLORS = {
    "Normal": "#9099a1", "Fire": "#ff9d55", "Water": "#5090d6",
    "Electric": "#f4d23c", "Grass": "#63bc5a", "Ice": "#73cec0",
    "Fighting": "#ce4069", "Poison": "#aa6bc8", "Ground": "#d97845",
    "Flying": "#8fa9de", "Psychic": "#fa7179", "Bug": "#91c12f",
    "Rock": "#c5b78c", "Ghost": "#5269ad", "Dragon": "#0b6dc3",
    "Dark": "#5a5465", "Steel": "#5a8ea2", "Fairy": "#ec8fe6",
}

# Ordre et libelles des stats de base dans l'infobulle.
STAT_ORDER = [("HP", "PV"), ("Attack", "Att"), ("Defense", "Déf"),
              ("Sp. Attack", "Att.Spé"), ("Sp. Defense", "Déf.Spé"), ("Speed", "Vit")]
# Reference de remplissage des jauges : au-dela de 180 une stat est deja
# exceptionnelle, calibrer sur le maximum absolu (255) ecraserait tout le reste.
STAT_FULL = 180

POKEDEX_URL = "https://alpha.pokemmotools.org/pokedex/{dex}"
# Cadre de la grande image du panneau, a l'echelle 1.0. Les deux dimensions
# comptent : cale sur la seule hauteur, un Pokemon large comme Racaillou
# depassait la largeur du panneau. Volontairement modeste : le panneau ne doit
# pas depasser la hauteur du widget, deja a son minimum.
PANEL_ART_BOX = (104, 92)

# Palette sombre, lisible sur n'importe quel fond d'ecran.
BG = "#12151c"
BG_TIP = "#181d27"
FG_LINK = "#6cb8ff"
FG_HOVER = "#8fd0ff"      # nom accentue au survol : bleu clair
FG_REGION = "#8b96a8"
FG_VALUE = "#e8edf5"
FG_LOCATION = "#8fa3bf"
FG_EMPTY = "#3d4553"
FG_TITLE = "#5d6b8a"
FG_TIMER = "#6f7d94"
ACCENT = "#4da3ff"        # connecte, aucun essaim en cours
ACTIVE = "#3ddc84"        # essaim en cours : vert vif
ACTIVE_DIM = "#1d5c39"    # phase eteinte du clignotement


def load_data() -> dict:
    """Tables produites par fetch_assets.py : Pokemon, lieux, regions,
    attaques et capacites."""
    try:
        payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    return {key: payload.get(f"_{key}") or {}
            for key in ("pokemon", "location", "region", "move", "ability")}


def load_maps() -> dict:
    """Cartes annotees par lieu, produites par fetch_assets.py."""
    try:
        return json.loads(MAPS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_regions() -> dict:
    """Cartes de region et coordonnees des lieux, produites par fetch_assets."""
    try:
        return json.loads(REGIONS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_alpha_data() -> dict:
    """Capacite et attaques par alpha, indexees "pokemon|region|lieu"."""
    try:
        return json.loads(ALPHA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def normalize(name: str) -> str:
    """Cle de comparaison des noms d'especes : la table des tiers melange des
    noms d'affichage Alphapedia ("Mr. Mime") et des identifiants PokeAPI
    ("mr-mime") pour les evolutions heritees."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def load_tiers() -> tuple[dict, dict]:
    """Tiers de rarete Alphapedia : {Pokemon: tier} et {tier: points}.

    Plus le tier est bas, plus le Pokemon est rare (T0 = 50 points, T7 = 3).
    Tous les Pokemon n'y figurent pas : les evolutions intermediaires en sont
    absentes, seules les formes chassables sont classees.
    """
    try:
        payload = json.loads(TIERS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, {}
    tiers = payload.get("tiers") or {}
    points = {int(k): v for k, v in (payload.get("points") or {}).items()}
    return tiers, points


def detect_kind(payload: dict, original: dict) -> str:
    """"alpha" ou "swarm", selon le canal d'origine d'Alphapedia.

    Le site publie les alphas sur le topic `alphapings` et les essaims sur
    `swarmpings` (variantes `-test` incluses). `sourcePage` sert de second
    indice quand le topic manque.
    """
    topic = str(payload.get("topic") or "").lower()
    if topic.startswith("alphaping"):
        return "alpha"
    if topic.startswith("swarmping"):
        return "swarm"
    if "alpha" in str(original.get("sourcePage") or "").lower():
        return "alpha"
    return "swarm"


def load_bboxes(path: Path = None) -> dict:
    """Cadre utile de chaque sprite, produit par fetch_assets.py."""
    try:
        return json.loads((path or BBOX_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}  # sans cadrage : sprites affiches tels quels, avec leur vide


# --- Recuperation temps reel (ntfy) ---------------------------------------


def event_time(event: dict) -> float:
    """Horodatage du message ntfy, et non l'heure de reception.

    Indispensable a l'amorcage : le cache rejoue des messages parfois vieux de
    plusieurs heures. Les dater de l'instant present les ferait passer pour des
    evenements frais — un alpha de 8 h d'age reapparaissait avec 75 min au
    compteur a chaque redemarrage.
    """
    try:
        stamp = float(event.get("time") or 0)
    except (TypeError, ValueError):
        stamp = 0.0
    # Un horodatage absent ou aberrant : on retombe sur maintenant.
    return stamp if stamp > 0 else time.time()


class NtfyFeed(threading.Thread):
    """Connexion sortante persistante vers ntfy. Depose les essaims dans une file."""

    def __init__(self, server: str, topic: str, sink: queue.Queue, seed: str | None):
        super().__init__(daemon=True)
        self.server = server.rstrip("/")
        self.topic = topic
        self.name = f"{self.server}/{topic}"
        self.sink = sink
        self.seed = seed  # ex "12h" : amorce l'affichage avec le cache serveur
        self.stop = threading.Event()

    def _emit(self, event: dict) -> None:
        body = event.get("message") or ""
        parsed = from_json_payload(body)
        if not parsed:
            self._emit_plain(event)
            return
        raw = json.loads(body)
        original = raw.get("originalJson") or {}

        # Alphapedia fournit la fin exacte de l'evenement : bien plus fiable
        # qu'une duree devinee de notre cote.
        despawn = original.get("despawnTimestamp")
        try:
            despawn = float(despawn) if despawn else None
        except (TypeError, ValueError):
            despawn = None

        # Le webhook porte deja le tier de rarete dans ses donnees Pokedex.
        tier = (original.get("data") or {}).get("Tier")
        try:
            tier = int(tier)
        except (TypeError, ValueError):
            tier = None

        self.sink.put({
            "pokemon": parsed["pokemon"],
            "region": parsed.get("region", ""),
            "location": parsed["location"],
            "kind": detect_kind(raw, original),
            "tier": tier,
            "despawn": despawn,
            "received": event_time(event),
        })

    def _emit_plain(self, event: dict) -> None:
        """Message du serveur ntfy d'Alphapedia : texte simple, pas de JSON.

            title   = "Golem"
            message = "Hoenn\\nJagged Pass"

        Ce flux couvre les deux types (le topic ntfy les distingue) mais ne
        porte aucune date d'expiration : on retombe sur les durees par defaut.
        """
        title = (event.get("title") or "").strip()
        lines = [l.strip() for l in (event.get("message") or "").splitlines() if l.strip()]
        if not title or len(lines) < 2:
            return
        region, location = lines[0], lines[1]
        if region not in {key for key, _ in REGIONS}:
            return

        topic = str(event.get("topic") or "")
        self.sink.put({
            "pokemon": title,
            "region": region,
            "location": location,
            "kind": detect_kind({"topic": topic}, {}),
            "despawn": None,   # inconnu sur ce flux
            "received": event_time(event),
        })

    def _read_stream(self, url: str, timeout: float):
        # Le serveur d'Alphapedia est derriere Cloudflare et repond 403 a
        # l'agent par defaut d'urllib, en souscription comme en poll.
        request = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
        with urllib.request.urlopen(request, timeout=timeout) as stream:
            for raw in stream:
                if self.stop.is_set():
                    return
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    yield json.loads(raw)
                except json.JSONDecodeError:
                    continue

    def run(self) -> None:
        if self.seed:
            # Sans amorcage le widget resterait vide jusqu'au prochain essaim.
            # Le cache de ntfy donne l'etat courant tout de suite, sans rien
            # stocker en local.
            try:
                url = f"{self.server}/{self.topic}/json?poll=1&since={self.seed}"
                for event in self._read_stream(url, 20):
                    if event.get("event") == "message":
                        self._emit(event)
            except (urllib.error.URLError, OSError, TimeoutError, ValueError):
                pass

        self.sink.put({"status": "connecting", "feed": self.name})
        backoff = 1.0
        while not self.stop.is_set():
            try:
                url = f"{self.server}/{self.topic}/json?since=latest"
                for event in self._read_stream(url, NTFY_READ_TIMEOUT):
                    kind = event.get("event")
                    if kind == "open":
                        self.sink.put({"status": "online", "feed": self.name})
                        backoff = 1.0
                    elif kind == "message":
                        self._emit(event)
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                if self.stop.is_set():
                    return
                self.sink.put({"status": "offline", "feed": self.name})
                self.stop.wait(backoff)
                backoff = min(backoff * 2, 60.0)


# --- Icone dans la zone de notification (Win32 pur) -----------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

WM_APP_TRAY = 0x8001
WM_LBUTTONUP, WM_RBUTTONUP, WM_DESTROY = 0x0202, 0x0205, 0x0002
NIM_ADD, NIM_DELETE = 0x0, 0x2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
IDI_INFORMATION = 32516
MF_STRING, MF_SEPARATOR, MF_CHECKED = 0x0, 0x800, 0x8
TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x2, 0x100

ID_TOGGLE, ID_QUIT, ID_PIN_TOP, ID_PIN_DESKTOP = 1001, 1002, 1003, 1004
ID_BIGGER, ID_SMALLER, ID_RESET = 1005, 1006, 1007
ID_OPAQUE, ID_TRANSPARENT, ID_OPACITY_RESET = 1008, 1009, 1010

DEFAULT_IDLE_OPACITY = 0.72

LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_byte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD), ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
    ]


def _declare_signatures() -> None:
    """Declare les signatures Win32.

    Sans cela ctypes suppose des int C pour tous les arguments : un lparam
    (pointeur ou coordonnees empaquetees) deborde et leve OverflowError au
    beau milieu du WNDPROC, ou l'on ne peut rien rattraper.
    """
    LPDWORD_PTR = ctypes.POINTER(ctypes.c_void_p)

    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.FindWindowW.restype = wintypes.HWND
    user32.GetParent.restype = wintypes.HWND
    user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    user32.SetParent.restype = wintypes.HWND
    user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT,
                                           wintypes.WPARAM, wintypes.LPARAM,
                                           wintypes.UINT, wintypes.UINT, LPDWORD_PTR]
    user32.SendMessageTimeoutW.restype = LRESULT
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    wintypes.UINT]
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT,
                                   ctypes.c_size_t, wintypes.LPCWSTR]
    user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                      ctypes.c_void_p]
    user32.TrackPopupMenu.restype = ctypes.c_int
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
    user32.LoadIconW.restype = wintypes.HICON
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD,
                                          ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL


_declare_signatures()


class TrayIcon(threading.Thread):
    """Icone de notification. Vit dans son propre thread : Windows exige que la
    boucle de messages tourne dans le thread qui a cree la fenetre."""

    def __init__(self, tooltip: str, on_toggle, on_quit, on_pin, get_pin,
                 on_scale, get_scale, on_opacity, get_opacity):
        super().__init__(daemon=True)
        self.tooltip = tooltip
        self.on_toggle = on_toggle
        self.on_quit = on_quit
        self.on_pin = on_pin
        self.get_pin = get_pin
        self.on_scale = on_scale
        self.get_scale = get_scale
        self.on_opacity = on_opacity
        self.get_opacity = get_opacity
        self.hwnd = None
        self._proc = WNDPROC(self._wndproc)  # reference gardee : sinon collecte

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_APP_TRAY:
            if lparam == WM_LBUTTONUP:
                self.on_toggle()
            elif lparam == WM_RBUTTONUP:
                self._show_menu(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _show_menu(self, hwnd):
        current = self.get_pin()
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if current == "top" else 0),
                           ID_PIN_TOP, "Premier plan")
        user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if current == "desktop" else 0),
                           ID_PIN_DESKTOP, "Arriere-plan (bureau)")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_BIGGER, "Agrandir  (+10 %)")
        user32.AppendMenuW(menu, MF_STRING, ID_SMALLER, "Reduire  (-10 %)")
        user32.AppendMenuW(menu, MF_STRING, ID_RESET,
                           f"Taille par defaut  (actuelle : {self.get_scale():.2f})")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_OPAQUE, "Plus opaque  (+5 %)")
        user32.AppendMenuW(menu, MF_STRING, ID_TRANSPARENT, "Plus transparent  (-5 %)")
        user32.AppendMenuW(menu, MF_STRING, ID_OPACITY_RESET,
                           f"Transparence par defaut  (actuelle : "
                           f"{self.get_opacity() * 100:.0f} %)")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_TOGGLE, "Afficher / masquer")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_QUIT, "Quitter")

        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        # Sans cet appel le menu ne se referme pas quand on clique ailleurs.
        user32.SetForegroundWindow(hwnd)
        choice = user32.TrackPopupMenu(
            menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, point.x, point.y, 0, hwnd, None)
        user32.DestroyMenu(menu)

        if choice == ID_TOGGLE:
            self.on_toggle()
        elif choice == ID_QUIT:
            self.on_quit()
        elif choice == ID_PIN_TOP:
            self.on_pin("top")
        elif choice == ID_PIN_DESKTOP:
            self.on_pin("desktop")
        elif choice == ID_BIGGER:
            self.on_scale(1.1, None)
        elif choice == ID_SMALLER:
            self.on_scale(1 / 1.1, None)
        elif choice == ID_RESET:
            self.on_scale(None, DEFAULT_SCALE)
        elif choice == ID_OPAQUE:
            self.on_opacity(0.05, None)
        elif choice == ID_TRANSPARENT:
            self.on_opacity(-0.05, None)
        elif choice == ID_OPACITY_RESET:
            self.on_opacity(None, DEFAULT_IDLE_OPACITY)

    def run(self) -> None:
        cls = WNDCLASSW()
        cls.lpfnWndProc = self._proc
        cls.lpszClassName = "SwarmWidgetTray"
        cls.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
        if not user32.RegisterClassW(ctypes.byref(cls)):
            return

        self.hwnd = user32.CreateWindowExW(
            0, cls.lpszClassName, "SwarmWidgetTray", 0, 0, 0, 0, 0,
            None, None, cls.hInstance, None)
        if not self.hwnd:
            return

        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = 1
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = WM_APP_TRAY
        data.hIcon = user32.LoadIconW(None, ctypes.c_wchar_p(IDI_INFORMATION))
        data.szTip = self.tooltip[:127]
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data))
        self._data = data

        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

    def remove(self) -> None:
        if self.hwnd:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._data))
            user32.PostMessageW(self.hwnd, WM_DESTROY, 0, 0)


# --- Ancrage ---------------------------------------------------------------


def monitor_work_area(hwnd: int) -> tuple[int, int, int, int]:
    """Zone utile de l'ecran ou se trouve la fenetre.

    winfo_screenwidth() ne decrit que l'ecran principal : sur un second ecran,
    le calcul de placement du panneau tombait a cote et l'envoyait hors champ.
    """
    MONITOR_DEFAULTTONEAREST = 2
    handle = user32.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if handle and user32.GetMonitorInfoW(handle, ctypes.byref(info)):
        area = info.rcWork
        return area.left, area.top, area.right, area.bottom
    # Repli : bureau virtuel complet (SM_XVIRTUALSCREEN et suivants).
    left = user32.GetSystemMetrics(76)
    top = user32.GetSystemMetrics(77)
    return left, top, left + user32.GetSystemMetrics(78), top + user32.GetSystemMetrics(79)


def pin_to_desktop(hwnd: int) -> bool:
    """Rattache la fenetre au bureau : elle reste visible quand on reduit tout."""
    progman = user32.FindWindowW("Progman", None)
    if not progman:
        return False
    # Demande a Progman de creer le calque WorkerW ; sans ce message, certaines
    # configurations refusent l'adoption.
    result = ctypes.c_void_p()
    user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0x0000, 1000,
                               ctypes.byref(result))
    user32.SetParent(hwnd, progman)
    # SetParent rend l'ANCIEN parent : pour une fenetre de premier niveau c'est
    # souvent 0, donc un retour nul ne signifie pas echec. On verifie le
    # resultat effectif.
    return user32.GetParent(hwnd) == progman


# --- Widget ---------------------------------------------------------------


class DetailPanel:
    """Fiche Pokedex ouverte au clic, accolee au widget.

    Fenetre a part (Toplevel) plutot que dessin dans le widget : elle peut ainsi
    se placer a cote sans changer la taille du widget, et rester visible meme
    quand celui-ci est ancre au bureau.
    """

    GAP = 8  # ecart avec le widget, en pixels

    def __init__(self, widget: "SwarmWidget"):
        self.widget = widget
        self.window = None
        self.current = None
        self.origin = None      # evenement affiche : type, region, lieu

    def toggle(self, english: str, entry: dict | None = None) -> None:
        """Un clic sur le meme Pokemon referme le panneau."""
        if self.window is not None and self.current == english:
            self.close()
        else:
            self.show(english, entry)

    def close(self) -> None:
        if self.window is not None:
            self.window.destroy()
            self.window = None
        self.current = None
        self.origin = None

    # -- rendu --------------------------------------------------------------

    def show(self, english: str, entry: dict | None = None) -> None:
        info = self.widget.table.get(english)
        if not info:
            return
        self.close()
        self.current = english
        self.origin = entry

        scale = self.widget.scale
        def font(size, weight="normal"):
            return ("Segoe UI", max(7, int(round(size * scale))), weight)

        panel = tk.Toplevel(self.widget.root)
        panel.overrideredirect(True)
        panel.attributes("-topmost", self.widget.pin == "top")
        panel.attributes("-alpha", self.widget.opacity)
        panel.configure(bg="#2a3140")          # sert de fine bordure
        self.window = panel

        body = tk.Frame(panel, bg=BG_TIP, padx=int(14 * scale), pady=int(12 * scale))
        body.pack(fill="both", expand=True, padx=1, pady=1)

        # -- en-tete : nom, numero, et croix de fermeture
        head = tk.Frame(body, bg=BG_TIP)
        head.pack(fill="x")
        tk.Label(head, text=self.widget._label(english), bg=BG_TIP, fg=FG_VALUE,
                 font=font(12, "bold")).pack(side="left")
        # Numero bien lisible, suivi de l'icone de lien : le libelle texte en
        # bas de panneau se faisait couper quand le widget etait court.
        tk.Label(head, text=f"  #{info['id']:03d}", bg=BG_TIP, fg=FG_REGION,
                 font=font(9, "bold")).pack(side="left")
        url = POKEDEX_URL.format(dex=info["id"])
        goto = tk.Label(head, text=" ↗", bg=BG_TIP, fg=FG_LINK,
                        font=font(10, "bold"), cursor="hand2")
        goto.pack(side="left")
        goto.bind("<Button-1>", lambda _event: webbrowser.open(url))
        goto.bind("<Enter>", lambda _e: goto.configure(fg=FG_HOVER))
        goto.bind("<Leave>", lambda _e: goto.configure(fg=FG_LINK))

        # Carte du lieu, dans l'en-tete : une ligne dediee poussait la capacite
        # hors du panneau, deja a la hauteur du widget.
        card = (self.widget.map_for(entry.get("region", ""), entry.get("location", ""))
                if entry else None)
        if card:
            atlas = tk.Label(head, text=" 🗺", bg=BG_TIP, fg=FG_LINK,
                             font=font(9, "bold"), cursor="hand2")
            atlas.pack(side="left")
            place = entry.get("location", "")
            atlas.bind("<Button-1>", lambda _e, c=card, t=place: self.widget.show_map(c, t))
            atlas.bind("<Enter>", lambda _e: atlas.configure(fg=FG_HOVER))
            atlas.bind("<Leave>", lambda _e: atlas.configure(fg=FG_LINK))
        close = tk.Label(head, text="✕", bg=BG_TIP, fg=FG_EMPTY,
                         font=font(10, "bold"), cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda _event: self.close())
        close.bind("<Enter>", lambda _e: close.configure(fg=FG_VALUE))
        close.bind("<Leave>", lambda _e: close.configure(fg=FG_EMPTY))

        # -- grande image, centree sous l'en-tete
        is_alpha = bool(entry and entry.get("kind") == "alpha")
        art = self.widget.artwork(
            english, (int(PANEL_ART_BOX[0] * scale), int(PANEL_ART_BOX[1] * scale)),
            alpha=is_alpha)
        if art is not None:
            holder = tk.Label(body, image=art, bg=BG_TIP)
            holder.image = art          # reference gardee : sinon vidage
            holder.pack(pady=(int(6 * scale), 0))

        # -- rarete puis types, sur la meme ligne
        tags = tk.Frame(body, bg=BG_TIP)
        tags.pack(anchor="w", pady=(int(8 * scale), 0))

        # Le panneau est la vue detaillee : il montre le bareme meme quand la
        # ligne n'affiche que le rang. Mais si la rarete est masquee, elle l'est
        # partout.
        tier = None if self.widget.rarity == "none" else self.widget._tier_of(english, {})
        if tier is not None:
            points = self.widget.tier_points.get(tier)
            text = f"T{tier}" + (f" · {points} pts" if points else "")
            tk.Label(tags, text=f" {text} ", bg=TIER_COLORS.get(tier, FG_TIMER),
                     fg="#12151c", font=font(8, "bold")).pack(
                         side="left", padx=(0, int(6 * scale)))

        for kind in info.get("types") or []:
            tk.Label(tags, text=f" {TYPE_FR.get(kind, kind)} ",
                     bg=TYPE_COLORS.get(kind, FG_TIMER), fg="#12151c",
                     font=font(8, "bold")).pack(side="left", padx=(0, int(5 * scale)))

        # -- jauges de stats
        base = info.get("base") or {}
        if base:
            grid = tk.Frame(body, bg=BG_TIP)
            grid.pack(anchor="w", pady=(int(9 * scale), 0))
            bar_width = int(110 * scale)
            for row, (key, label) in enumerate(STAT_ORDER):
                value = int(base.get(key, 0))
                tk.Label(grid, text=label, bg=BG_TIP, fg=FG_REGION, anchor="w",
                         font=font(8), width=7).grid(row=row, column=0, sticky="w")
                track = tk.Frame(grid, bg="#252c39", width=bar_width,
                                 height=int(7 * scale))
                track.grid(row=row, column=1, padx=(0, int(8 * scale)),
                           pady=int(2 * scale))
                track.pack_propagate(False)
                filled = max(1, int(bar_width * min(1.0, value / STAT_FULL)))
                tk.Frame(track, bg=self._stat_color(value), width=filled,
                         height=int(7 * scale)).place(x=0, y=0, relheight=1.0)
                tk.Label(grid, text=str(value), bg=BG_TIP, fg=FG_VALUE, anchor="e",
                         font=font(8), width=4).grid(row=row, column=2, sticky="e")
            total = sum(int(v) for v in base.values())
            tk.Label(grid, text="Total", bg=BG_TIP, fg=FG_REGION, anchor="w",
                     font=font(8, "bold"), width=7).grid(row=len(STAT_ORDER), column=0,
                                                         sticky="w", pady=(int(3 * scale), 0))
            tk.Label(grid, text=str(total), bg=BG_TIP, fg=FG_VALUE, anchor="e",
                     font=font(8, "bold"), width=4).grid(row=len(STAT_ORDER), column=2,
                                                          sticky="e", pady=(int(3 * scale), 0))

        # -- specifique aux alphas : leur capacite est figee, et c'est souvent
        # ce qui fait leur interet.
        alpha = self._alpha_details(english)
        if alpha and alpha.get("ability"):
            block = tk.Frame(body, bg=BG_TIP)
            block.pack(anchor="w", fill="x", pady=(int(8 * scale), 0))
            tk.Frame(block, bg="#2a3140", height=1).pack(fill="x",
                                                         pady=(0, int(6 * scale)))
            line = tk.Frame(block, bg=BG_TIP)
            line.pack(anchor="w")
            # Meme ton que les libelles de stats : c'en est un de plus.
            tk.Label(line, text="Capacité  ", bg=BG_TIP, fg=FG_REGION,
                     font=font(8)).pack(side="left")
            tk.Label(line, text=self.widget._ability(alpha["ability"]), bg=BG_TIP,
                     fg=KIND_COLOR["alpha"], font=font(9, "bold")).pack(side="left")

        self.reposition()

    def _alpha_details(self, english: str) -> dict | None:
        """Capacite et attaques, uniquement si l'evenement affiche est un alpha.

        Ces champs n'existent que pour les alphas chez Alphapedia : 310 entrees
        alpha sur 310 les portent, 0 sur 797 entrees d'essaims.
        """
        entry = self.origin
        if not entry or entry.get("kind") != "alpha":
            return None
        key = "|".join((normalize(english), normalize(entry.get("region", "")),
                        normalize(entry.get("location", ""))))
        found = self.widget.alpha_data.get(key)
        if found:
            return found
        # Le lieu annonce peut differer de celui du catalogue. On ne se rabat
        # sur l'espece seule que si elle n'a QU'UNE apparition connue : deux
        # spawns d'une meme espece ont des attaques differentes, et afficher
        # celles du mauvais serait pire que de ne rien montrer.
        prefix = normalize(english) + "|"
        matches = [value for candidate, value in self.widget.alpha_data.items()
                   if candidate.startswith(prefix)]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _stat_color(value: int) -> str:
        if value >= 120:
            return "#3ddc84"
        if value >= 90:
            return "#8bd450"
        if value >= 60:
            return "#e0c341"
        if value >= 40:
            return "#e08f41"
        return "#d1594f"

    def reposition(self) -> None:
        """Accole le panneau au widget, du cote ou il y a le plus de place.

        Appele aussi pendant le deplacement du widget, pour que le panneau le
        suive au lieu de rester en arriere.
        """
        panel = self.window
        if panel is None:
            return
        root = self.widget.root
        root.update_idletasks()
        panel.update_idletasks()

        main_x, main_y = root.winfo_rootx(), root.winfo_rooty()
        main_w, main_h = root.winfo_width(), root.winfo_height()
        panel_w = panel.winfo_reqwidth()

        # Bornes de l'ECRAN OU SE TROUVE LE WIDGET, et non de l'ecran principal :
        # sur un second moniteur, un calcul base sur winfo_screenwidth() place le
        # panneau hors champ.
        left, top, right, bottom = monitor_work_area(self.widget.hwnd or root.winfo_id())

        room_right = right - (main_x + main_w)
        room_left = main_x - left
        if room_right >= panel_w + self.GAP or room_right >= room_left:
            x = main_x + main_w + self.GAP
        else:
            x = main_x - panel_w - self.GAP
        x = max(left, min(x, right - panel_w))
        y = max(top, min(main_y, bottom - main_h))
        # Meme hauteur que le widget principal, alignee sur son sommet.
        panel.geometry(f"{panel_w}x{main_h}+{x}+{y}")


class SwarmWidget:
    def __init__(self, root: tk.Tk, feed_queue: queue.Queue, pin: str, opacity: float,
                 lang: str, scale: float, sprite_scale: float = 1.0,
                 rarity: str = "tier", idle_opacity: float = 0.72):
        self.root = root
        self.queue = feed_queue
        self.pin = pin
        self.opacity = opacity
        self.lang = lang
        self.scale = scale
        self.sprite_scale = sprite_scale
        self.rarity = rarity
        self.idle_opacity = min(opacity, idle_opacity)
        self.current_alpha = opacity
        self.blink_on = False
        self.connection = "connecting"
        self.feed_status: dict[str, str] = {}
        self.bboxes = load_bboxes()
        self.bboxes_big = load_bboxes(BBOX_BIG_FILE)
        self.bboxes_alpha = load_bboxes(BBOX_ALPHA_FILE)
        self.art = {}   # grandes images du panneau, gardees en reference
        self.glow_step = 0
        self.glow_last = (None, None)
        self.panel = DetailPanel(self)
        self._dragged = False
        # Ligne actuellement survolee : _render() doit preserver son
        # accentuation, sinon la mise a jour du decompte l'efface chaque seconde.
        self.hovered = None
        self.hovered_place = None
        tables = load_data()
        self.table = tables["pokemon"]
        self.places = tables["location"]
        self.regions = tables["region"]
        self.moves = tables["move"]
        self.abilities = tables["ability"]
        self.alpha_data = load_alpha_data()
        self.maps = load_maps()
        self.regions_map = load_regions()
        self.map_window = None
        self.tiers, self.tier_points = load_tiers()
        self.state: dict[tuple[str, str], dict] = {}
        self.rows: dict[str, list[dict]] = {}
        self.sprites: dict[int, tk.PhotoImage] = {}  # references gardees : sinon vidage
        self.visible = True
        self.hwnd = None
        self._last_render = ""
        # Avant de calculer quoi que ce soit qui depende de l'echelle : l'etat
        # sauvegarde peut la redefinir.
        self._load_state()
        # Cellule d'un sprite : taille de reference * echelle globale * echelle
        # propre aux sprites. Fixe, pour que la colonne ne tremble pas d'une
        # ligne a l'autre selon la corpulence du Pokemon.
        self.cell = (max(8, int(round(SPRITE_CELL[0] * self.scale * sprite_scale))),
                     max(8, int(round(SPRITE_CELL[1] * self.scale * sprite_scale))))
        self._build()

    # -- ressources ---------------------------------------------------------

    def _label(self, english: str) -> str:
        info = self.table.get(english)
        if self.lang == "fr" and info and info.get("fr"):
            return info["fr"]
        return english

    def artwork(self, english: str, box: tuple[int, int],
                alpha: bool = False) -> tk.PhotoImage | None:
        """Grande image du Pokemon pour le panneau de details.

        Utilise les sprites de face 96x96 et non les icones 68x56 : agrandies,
        ces dernieres seraient illisibles. Rognees puis mises a l'echelle pour
        tenir dans le cadre voulu, sans deformation.

        Pour un alpha, on prend la variante cerclee de rouge generee par
        fetch_assets.py : PokeMMO entoure ses alphas d'une aura, mais c'est un
        effet de rendu du jeu, aucun sprite alpha n'etant distribue.
        """
        info = self.table.get(english)
        if not info:
            return None
        dex = info["id"]
        key = (dex, box, alpha)
        if key in self.art:
            return self.art[key]
        directory = SPRITE_ALPHA_DIR if alpha else SPRITE_BIG_DIR
        boxes = self.bboxes_alpha if alpha else self.bboxes_big
        path = directory / f"{dex}.png"
        if not path.exists():
            directory, boxes = SPRITE_BIG_DIR, self.bboxes_big
            path = directory / f"{dex}.png"
        if not path.exists():
            return None
        try:
            image = tk.PhotoImage(file=str(path))
            # Nom distinct de `box` : le reutiliser ecraserait le cadre cible,
            # et l'echelle se calculerait alors sur les coordonnees du rognage.
            crop = boxes.get(str(dex))
            if crop:
                x1, y1, x2, y2 = crop
                cropped = tk.PhotoImage(width=x2 - x1, height=y2 - y1)
                cropped.tk.call(cropped, "copy", image, "-from", x1, y1, x2, y2,
                                "-to", 0, 0)
                image = cropped
            factor = min(box[0] / max(1, image.width()),
                         box[1] / max(1, image.height()))
            ratio = Fraction(0, 1)
            for denominator in range(1, 7):
                numerator = int(factor * denominator)
                if numerator >= 1:
                    candidate = Fraction(numerator, denominator)
                    if candidate <= factor and candidate > ratio:
                        ratio = candidate
            if ratio == 0:
                ratio = Fraction(1, 6)
            if ratio.numerator > 1:
                image = image.zoom(ratio.numerator, ratio.numerator)
            if ratio.denominator > 1:
                image = image.subsample(ratio.denominator, ratio.denominator)
        except (tk.TclError, ValueError, ZeroDivisionError):
            return None
        self.art[key] = image
        return image

    def _move(self, english: str) -> str:
        if self.lang == "fr":
            return self.moves.get(english) or english
        return english

    def _ability(self, english: str) -> str:
        if self.lang == "fr":
            return self.abilities.get(english) or english
        return english

    def map_for(self, region: str, location: str) -> dict | None:
        """Carte annotee du lieu, si la communaute en a fourni une.

        Elles ne couvrent que 55 lieux sur plusieurs centaines — surtout les
        grottes et interieurs, la ou s'orienter est le plus penible.
        """
        return self.maps.get("|".join((normalize(region), normalize(location))))

    @staticmethod
    def _find_place(places: dict, key: str):
        """Retrouve un lieu malgre les ecarts de nommage entre PokeMMO et les
        decompilations : « Route 205 » y est decoupee en route205north et
        route205south, « Mt. Coronet » s'y appelle mountcoronet, et
        « Lake Verity » veritylakefront.
        """
        if not key:
            return None
        if key in places:
            return places[key]
        variantes = [key]
        if key.startswith("mt"):
            variantes.append("mount" + key[2:])
        if key.startswith("mount"):
            variantes.append("mt" + key[5:])
        if key.startswith("lake"):
            variantes.append(key[4:] + "lakefront")
        for variante in variantes:
            if variante in places:
                return places[variante]
            # Prefixe : une zone decoupee en plusieurs troncons.
            proches = sorted(k for k in places if k.startswith(variante))
            if proches:
                return places[proches[0]]
        return None

    def show_region(self, region: str, location: str) -> None:
        """Affiche la carte de la region, ou la couche qui contient le lieu.

        Certaines regions ont des cartes annexes (iles Sevii pour Kanto) : si le
        lieu s'y trouve, on montre cette couche seule plutot que la principale.
        """
        info = self.regions_map.get(normalize(region))
        if not info:
            return
        key = normalize(location)
        chosen, label = info, self._region_label(region, region)
        spot = self._find_place(info.get("places") or {}, key)
        if spot is None:
            for layer in info.get("layers") or []:
                found = self._find_place(layer.get("places") or {}, key)
                if found is not None:
                    chosen, label, spot = layer, layer.get("name", label), found
                    break
        path = REGIONS_DIR / chosen["file"]
        if not path.exists():
            return
        self._open_map_panel(path, label, self._place_name(location), spot,
                             detail=self.map_for(region, location),
                             back=None, region=region, location=location)

    def _show_detail_map(self, card: dict, title: str, back) -> None:
        """Carte annotee du lieu, ouverte depuis le repere de la carte de
        region. Le bouton retour ramene a la carte officielle."""
        filename = card.get("file")
        if not filename or not (MAPS_DIR / filename).exists():
            webbrowser.open(card.get("url", ""))
            return
        self._open_map_panel(MAPS_DIR / filename, title, "carte détaillée",
                             None, back=back)

    def show_map(self, card: dict, title: str) -> None:
        """Ouvre la carte dans sa propre fenetre, ou dans le navigateur.

        Tk ne sait lire que le PNG et le GIF : les quelques cartes au format
        JPEG sont donc ouvertes dans le navigateur plutot que rendues ici.
        """
        filename = card.get("file")
        if not filename or not (MAPS_DIR / filename).exists():
            webbrowser.open(card.get("url", ""))
            return

        if self.map_window is not None:
            self.map_window.destroy()
            self.map_window = None

        try:
            image = tk.PhotoImage(file=str(MAPS_DIR / filename))
        except tk.TclError:
            webbrowser.open(card.get("url", ""))
            return

        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.attributes("-topmost", self.pin == "top")
        window.attributes("-alpha", self.opacity)
        window.configure(bg="#2a3140")          # fine bordure, comme le panneau
        self.map_window = window

        # La carte est cadree sur la LARGEUR du widget : le bandeau se colle
        # au-dessus ou en dessous, dans son alignement exact.
        self.root.update_idletasks()
        target_w = max(120, self.root.winfo_width() - 2)
        shrink = 1
        while image.width() // shrink > target_w and shrink < 8:
            shrink += 1
        if shrink > 1:
            image = image.subsample(shrink, shrink)

        # Largeur imposee, image centree : PhotoImage ne reduit que par des
        # entiers, l'image tombe donc rarement pile a la largeur du widget.
        body = tk.Frame(window, bg=BG_TIP, width=max(target_w, image.width()))
        body.pack(fill="both", expand=True, padx=1, pady=1)
        body.pack_propagate(False)
        head = tk.Frame(body, bg=BG_TIP)
        head.pack(fill="x", padx=int(8 * self.scale), pady=(int(4 * self.scale), 0))
        tk.Label(head, text=self._place_name(title), bg=BG_TIP, fg=FG_VALUE,
                 font=self._font(9, "bold")).pack(side="left")
        close = tk.Label(head, text="✕", bg=BG_TIP, fg=FG_EMPTY,
                         font=self._font(10, "bold"), cursor="hand2")
        close.pack(side="right")
        holder = tk.Label(body, image=image, bg=BG_TIP)
        holder.image = image           # reference gardee : sinon vidage
        holder.pack(padx=1, pady=(1, int(4 * self.scale)))
        # Hauteur = entete + image, puisque pack_propagate est desactive.
        body.configure(height=image.height() + int(30 * self.scale))

        def dismiss(_event=None):
            if self.map_window is not None:
                self.map_window.destroy()
                self.map_window = None
        # Seule la croix referme : cliquer l'image ne fait rien, comme sur la
        # carte de region.
        close.bind("<Button-1>", dismiss)
        close.bind("<Enter>", lambda _e: close.configure(fg=FG_VALUE))
        close.bind("<Leave>", lambda _e: close.configure(fg=FG_EMPTY))
        window.bind("<Escape>", dismiss)
        self.place_map()

    def _open_map_panel(self, path, region_label, place_label, spot,
                        enlarged: bool = False, detail=None, back=None,
                        region: str = "", location: str = "") -> None:
        """Bandeau de carte accole au widget, avec repere optionnel.

        L'agrandissement n'est pas memorise : a chaque reouverture on repart de
        la taille normale, calee sur la largeur du widget.
        """
        self._map_state = (path, region_label, place_label, spot)
        self._map_context = {"detail": detail, "back": back,
                             "region": region, "location": location}
        try:
            image = tk.PhotoImage(file=str(path))
        except tk.TclError:
            return
        if self.map_window is not None:
            self.map_window.destroy()
            self.map_window = None

        self.root.update_idletasks()
        area = monitor_work_area(self.hwnd or self.root.winfo_id())
        base_w = max(160, self.root.winfo_width() - 2)
        target_w = min(int((area[2] - area[0]) * 0.9), int(base_w * 2)) if enlarged else base_w
        shrink = 1
        grow = 1
        while image.width() // shrink > target_w and shrink < 10:
            shrink += 1
        if shrink > 1:
            image = image.subsample(shrink, shrink)
        elif image.width() * 2 <= target_w:
            # Certaines cartes sont plus petites que le widget : sans
            # grossissement, le bouton d'agrandissement n'aurait aucun effet.
            grow = min(4, target_w // max(1, image.width()))
            if grow > 1:
                image = image.zoom(grow, grow)

        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.attributes("-topmost", self.pin == "top")
        window.attributes("-alpha", self.opacity)
        window.configure(bg="#2a3140")
        self.map_window = window

        body = tk.Frame(window, bg=BG_TIP, width=max(target_w, image.width()))
        body.pack(fill="both", expand=True, padx=1, pady=1)
        body.pack_propagate(False)
        head = tk.Frame(body, bg=BG_TIP)
        head.pack(fill="x", padx=int(8 * self.scale), pady=(int(4 * self.scale), 0))
        tk.Label(head, text=region_label, bg=BG_TIP, fg=FG_VALUE,
                 font=self._font(9, "bold")).pack(side="left")
        tk.Label(head, text=f"  {place_label}", bg=BG_TIP, fg=FG_LOCATION,
                 font=self._font(8)).pack(side="left")
        close = tk.Label(head, text="✕", bg=BG_TIP, fg=FG_EMPTY,
                         font=self._font(10, "bold"), cursor="hand2")
        close.pack(side="right")
        zoom = tk.Label(head, text="⤡" if enlarged else "⤢", bg=BG_TIP, fg=FG_LINK,
                        font=self._font(10, "bold"), cursor="hand2")
        zoom.pack(side="right", padx=(0, int(8 * self.scale)))
        if back:
            retour = tk.Label(head, text="←", bg=BG_TIP, fg=FG_LINK,
                              font=self._font(11, "bold"), cursor="hand2")
            retour.pack(side="right", padx=(0, int(8 * self.scale)))
            retour.bind("<Button-1>", lambda _e: back())
            retour.bind("<Enter>", lambda _e: retour.configure(fg=FG_HOVER))
            retour.bind("<Leave>", lambda _e: retour.configure(fg=FG_LINK))
        ctx = self._map_context

        def basculer_taille(_event=None):
            """Agrandit, ou revient a la taille normale selon l'etat courant."""
            self._open_map_panel(path, region_label, place_label, spot, not enlarged,
                                 detail=ctx["detail"], back=ctx["back"],
                                 region=ctx["region"], location=ctx["location"])
            return "break"

        zoom.bind("<Button-1>", basculer_taille)
        zoom.bind("<Enter>", lambda _e: zoom.configure(fg=FG_HOVER))
        zoom.bind("<Leave>", lambda _e: zoom.configure(fg=FG_LINK))

        canvas = tk.Canvas(body, width=image.width(), height=image.height(),
                           bg=BG_TIP, highlightthickness=0)
        canvas.pack(pady=(int(3 * self.scale), int(4 * self.scale)))
        canvas.create_image(0, 0, anchor="nw", image=image)
        canvas.image = image           # reference gardee : sinon vidage
        body.configure(height=image.height() + int(30 * self.scale))
        # Double-clic n'importe ou sur la carte : meme effet que le bouton
        # d'agrandissement. Le simple clic, lui, ne fait rien — la carte ne se
        # referme que par sa croix, pour ne pas disparaitre au moindre geste.
        canvas.bind("<Double-Button-1>", basculer_taille)

        marker_ids = []
        if spot:
            # Le repere suit la meme mise a l'echelle que l'image.
            factor = (grow if shrink == 1 else 1) / shrink
            x, y, w, h = (v * factor for v in spot)
            pad = 2
            marker_ids.append(canvas.create_rectangle(
                x - pad, y - pad, x + w + pad, y + h + pad, outline="#ff3b30", width=2))
            marker_ids.append(canvas.create_rectangle(
                x - pad - 2, y - pad - 2, x + w + pad + 2, y + h + pad + 2,
                outline="#ffd166", width=1))
            if detail:
                # Cliquer le repere ouvre la carte annotee du lieu, avec retour.
                zone = canvas.create_rectangle(x - 8, y - 8, x + w + 8, y + h + 8,
                                               outline="", fill="")
                def vers_detail(_event=None):
                    retour = lambda: self.show_region(region, location)
                    self._show_detail_map(detail, place_label, retour)
                    return "break"
                for item in marker_ids + [zone]:
                    canvas.tag_bind(item, "<Button-1>", vers_detail)
                    # Sur le repere, le double-clic n'agrandit pas : son premier
                    # clic a deja ouvert la carte annotee.
                    canvas.tag_bind(item, "<Double-Button-1>", lambda _e: "break")
                    canvas.tag_bind(item, "<Enter>",
                                    lambda _e: canvas.configure(cursor="hand2"))
                    canvas.tag_bind(item, "<Leave>",
                                    lambda _e: canvas.configure(cursor=""))

        def dismiss(_event=None):
            if self.map_window is not None:
                self.map_window.destroy()
                self.map_window = None
        close.bind("<Button-1>", dismiss)
        close.bind("<Enter>", lambda _e: close.configure(fg=FG_VALUE))
        close.bind("<Leave>", lambda _e: close.configure(fg=FG_EMPTY))
        window.bind("<Escape>", dismiss)
        self.place_map()

    def place_map(self) -> None:
        """Colle la carte au-dessus ou en dessous du widget, meme largeur.

        Le cote est choisi selon la place disponible sur l'ecran courant : au
        ras du bas de l'ecran, le bandeau passe au-dessus.
        """
        window = self.map_window
        if window is None:
            return
        self.root.update_idletasks()
        window.update_idletasks()

        left, top, right, bottom = monitor_work_area(self.hwnd or self.root.winfo_id())
        main_x, main_y = self.root.winfo_rootx(), self.root.winfo_rooty()
        main_h = self.root.winfo_height()
        height = window.winfo_reqheight()
        gap = 8

        below = main_y + main_h + gap
        if below + height <= bottom:
            y = below
        else:
            y = max(top, main_y - height - gap)
        window.geometry(f"+{max(left, min(main_x, right - window.winfo_reqwidth()))}+{y}")

    def _place_name(self, english: str) -> str:
        """Nom localise du lieu. Les routes numerotees sont identiques dans les
        deux langues ; les lieux nommes ne le sont pas du tout
        (Jagged Pass -> Sentier Sinuroc).

        A ne pas confondre avec _place(), qui positionne la fenetre."""
        if self.lang == "fr":
            return self.places.get(english) or english
        return english

    def _region_label(self, english: str, fallback: str) -> str:
        if self.lang == "fr":
            return self.regions.get(english) or fallback
        return english

    def _tier_of(self, english: str, entry: dict) -> int | None:
        """Tier annonce par le payload s'il y en a un, sinon table locale."""
        declared = entry.get("tier")
        if isinstance(declared, int):
            return declared
        tier = self.tiers.get(normalize(english))
        return tier if isinstance(tier, int) else None

    def _sprite(self, english: str, hover: bool = False) -> tk.PhotoImage | None:
        """Sprite rogne de sa transparence puis mis a l'echelle de la cellule.

        Les icones natives font 68x56 mais le Pokemon n'y occupe que 7 a 13 %
        (mediane 24x22 px). Sans rognage il parait minuscule et impose des
        lignes deux fois trop hautes. On recadre, puis on met chaque sprite a
        l'echelle individuellement pour qu'ils aient tous la meme taille utile.
        """
        info = self.table.get(english)
        if not info:
            return None
        dex = info["id"]
        if (dex, hover) in self.sprites:
            return self.sprites[(dex, hover)]
        path = SPRITE_DIR / f"{dex}.png"
        if not path.exists():
            return None
        # Au repos le sprite n'occupe que 85 % de sa cellule : la marge permet
        # de le grossir au survol sans deborder ni bousculer la mise en page.
        budget = (self.cell[0] * (1.0 if hover else 0.85),
                  self.cell[1] * (1.0 if hover else 0.85))

        try:
            image = tk.PhotoImage(file=str(path))
            box = self.bboxes.get(str(dex))
            if box:
                x1, y1, x2, y2 = box
                cropped = tk.PhotoImage(width=x2 - x1, height=y2 - y1)
                cropped.tk.call(cropped, "copy", image, "-from", x1, y1, x2, y2,
                                "-to", 0, 0)
                image = cropped

            # Facteur qui fait tenir le sprite dans la cellule sans le deformer.
            # PhotoImage ne sait qu'agrandir/reduire par des entiers : on
            # approche le facteur par une fraction, zoom(n) puis subsample(d).
            width, height = image.width(), image.height()
            factor = min(budget[0] / width, budget[1] / height)
            # limit_denominator() peut arrondir au-dessus et faire deborder le
            # sprite de sa cellule (qui le rognerait). On cherche donc la
            # meilleure fraction restant inferieure ou egale au facteur voulu.
            # Partir de 0 et non de 1 : sinon, pour un facteur inferieur a 1
            # (gros Pokemon a reduire), aucun candidat ne l'emporterait.
            ratio = Fraction(0, 1)
            for denominator in range(1, 7):
                numerator = int(factor * denominator)
                if numerator >= 1:
                    candidate = Fraction(numerator, denominator)
                    if candidate <= factor and candidate > ratio:
                        ratio = candidate
            if ratio == 0:  # sprite bien plus grand que la cellule
                ratio = Fraction(1, 6)
            if ratio.numerator > 1:
                image = image.zoom(ratio.numerator, ratio.numerator)
            if ratio.denominator > 1:
                image = image.subsample(ratio.denominator, ratio.denominator)
        except (tk.TclError, ValueError, ZeroDivisionError):
            return None

        self.sprites[(dex, hover)] = image
        return image

    # -- construction -------------------------------------------------------

    def _font(self, size: int, weight: str = "normal") -> tuple:
        return ("Segoe UI", max(7, int(round(size * self.scale))), weight)

    def _build(self) -> None:
        root = self.root
        root.overrideredirect(True)        # pas de barre de titre
        root.configure(bg=BG)
        # Assez opaque pour rester lisible sur un fond charge : en dessous de
        # ~0.95 le bureau transperce le texte.
        root.attributes("-alpha", self.opacity)

        # Gabarit transparent aux dimensions de la cellule (voir plus bas).
        self.blank = tk.PhotoImage(width=self.cell[0], height=self.cell[1])

        # Deux cadres imbriques servent de halo : leur epaisseur simule une
        # lueur, leur couleur pulse quand un alpha est en cours.
        thickness = max(2, int(round(4 * self.scale)))
        self.glow_outer = tk.Frame(root, bg=BG, padx=thickness, pady=thickness)
        self.glow_outer.pack(fill="both", expand=True)
        self.glow_inner = tk.Frame(self.glow_outer, bg=BG,
                                   padx=max(1, thickness // 2),
                                   pady=max(1, thickness // 2))
        self.glow_inner.pack(fill="both", expand=True)

        pad = int(round(22 * self.scale))
        frame = tk.Frame(self.glow_inner, bg=BG, padx=pad, pady=pad)
        frame.pack(fill="both", expand=True)
        self.frame = frame

        header = tk.Frame(frame, bg=BG)
        header.grid(row=0, column=0, columnspan=4, sticky="ew",
                    pady=(0, int(16 * self.scale)))
        tk.Label(header, text="ESSAIMS", bg=BG, fg=FG_TITLE,
                 font=self._font(9, "bold")).pack(side="left")
        self.status = tk.Label(header, text="●", bg=BG, fg=FG_EMPTY, font=self._font(9))
        self.status.pack(side="right")

        row_index = 1
        for region_number, (key, label) in enumerate(REGIONS):
            # Respiration entre deux regions, sauf au-dessus de la premiere qui
            # suit deja l'entete.
            gap_top = 0 if region_number == 0 else int(round(9 * self.scale))
            # Deux emplacements par region : un essaim et un alpha peuvent etre
            # actifs au meme endroit. Le second reste masque tant qu'il ne sert
            # pas (grid_remove conserve sa configuration).
            slots = []
            for slot in range(2):
                # Le 2e emplacement se colle au 1er : ils appartiennent a la
                # meme region, l'espace ne se met qu'entre les regions.
                pad_y = (gap_top if slot == 0 else int(round(4 * self.scale)),
                         int(round(2 * self.scale)))
                shown = self._region_label(key, label) if slot == 0 else ""
                region = tk.Label(frame, text=shown, bg=BG,
                                  fg=FG_REGION, anchor="w", font=self._font(11))
                # "w" et non "nw" : centre verticalement, comme le nom en face.
                region.grid(row=row_index, column=0, sticky="w",
                            padx=(0, int(16 * self.scale)), pady=pad_y)
                # Le label porte toujours une image : le gabarit transparent
                # quand il n'y a rien. C'est la seule facon de figer la taille
                # de la colonne — width/height d'un Label comptent en
                # caracteres sans image, et en pixels avec. Fixer les deux
                # centre le sprite dans sa cellule quelle que soit sa taille.
                icon = tk.Label(frame, bg=BG, image=self.blank,
                                width=self.cell[0], height=self.cell[1])
                icon.grid(row=row_index, column=1, sticky="w",
                          padx=(0, int(12 * self.scale)), pady=pad_y)
                # Badge empile au-dessus du nom plutot qu'a cote : le type tient
                # dans la largeur deja occupee par le nom.
                stack = tk.Frame(frame, bg=BG)
                stack.grid(row=row_index, column=2, sticky="w", pady=pad_y)
                # Ligne des etiquettes : type d'evenement puis rarete.
                badges = tk.Frame(stack, bg=BG)
                badges.pack(anchor="w", pady=(0, int(round(3 * self.scale))))
                badge = tk.Label(badges, text="", bg=BG, fg=FG_EMPTY, anchor="w",
                                 font=self._font(7, "bold"))
                badge.pack(side="left")
                tier = tk.Label(badges, text="", bg=BG, fg=FG_EMPTY, anchor="w",
                                font=self._font(7, "bold"))
                tier.pack(side="left", padx=(int(round(8 * self.scale)), 0))
                # Nom et lieu separes : cliquer le nom ouvre la fiche du
                # Pokemon, cliquer le lieu ouvrira sa carte. Un seul libelle
                # rendait impossible de viser l'un ou l'autre.
                line = tk.Frame(stack, bg=BG)
                line.pack(anchor="w")
                name = tk.Label(line, text="---", bg=BG, fg=FG_EMPTY, anchor="w",
                                font=self._font(11, "bold"))
                name.pack(side="left")
                where = tk.Label(line, text="", bg=BG, fg=FG_EMPTY, anchor="w",
                                 font=self._font(11, "bold"))
                where.pack(side="left")
                timer = tk.Label(frame, text="", bg=BG, fg=FG_TIMER, anchor="e",
                                 font=self._font(9))
                timer.grid(row=row_index, column=3, sticky="e",
                           padx=(int(22 * self.scale), 0), pady=pad_y)

                # Survol : accentuation seule. Clic : ouverture de la fiche.
                for target in (icon, name):
                    target.bind("<Enter>", lambda _e, k=key, i=slot: self._hover(k, i, True))
                    target.bind("<Leave>", lambda _e, k=key, i=slot: self._hover(k, i, False))
                    target.bind("<ButtonRelease-1>",
                                lambda e, k=key, i=slot: self._click(e, k, i))
                    target.configure(cursor="hand2")
                where.bind("<Enter>", lambda _e, k=key, i=slot: self._hover_place(k, i, True))
                where.bind("<Leave>", lambda _e, k=key, i=slot: self._hover_place(k, i, False))
                where.bind("<ButtonRelease-1>",
                           lambda e, k=key, i=slot: self._click_place(e, k, i))
                where.configure(cursor="hand2")

                widgets = {"region": region, "badge": badge, "tier": tier,
                           "icon": icon, "name": name, "where": where,
                           "timer": timer,
                           # Seuls ces widgets sont geres par grid : badge et
                           # name sont empiles dans stack via pack().
                           "_gridded": (region, icon, stack, timer)}
                if slot == 1:
                    for w in widgets["_gridded"]:
                        w.grid_remove()
                slots.append(widgets)
                row_index += 1
            self.rows[key] = slots

        frame.grid_columnconfigure(2, weight=1)

        # Deplacement a la souris, puisqu'il n'y a plus de barre de titre.
        for widget in (root, self.glow_outer, self.glow_inner, frame, header):
            widget.bind("<Button-1>", self._grab)
            widget.bind("<B1-Motion>", self._drag)

        self.root.geometry("+%d+%d" % self.position)

    # -- etat persistant ----------------------------------------------------

    def _load_state(self) -> None:
        """Restaure position, mode d'ancrage et echelle de la session precedente."""
        self.position = (60, 60)
        try:
            saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        try:
            x, y = int(saved["x"]), int(saved["y"])
            # Une position hors de tout ecran rendrait le widget invisible :
            # cela arrive si l'on debranche un ecran ou change la resolution.
            # On borne sur le BUREAU VIRTUEL, sinon une position parfaitement
            # valide sur un second ecran serait rejetee.
            vx = user32.GetSystemMetrics(76)
            vy = user32.GetSystemMetrics(77)
            vw = user32.GetSystemMetrics(78) or self.root.winfo_screenwidth()
            vh = user32.GetSystemMetrics(79) or self.root.winfo_screenheight()
            if vx - 200 < x < vx + vw and vy - 200 < y < vy + vh:
                self.position = (x, y)
        except (KeyError, ValueError, TypeError):
            pass
        self.pin = saved.get("pin", self.pin)
        try:
            self.scale = min(3.0, max(0.5, float(saved["scale"])))
        except (KeyError, ValueError, TypeError):
            pass
        for key, low in (("opacity", 0.3), ("idle_opacity", 0.15)):
            try:
                setattr(self, key, min(1.0, max(low, float(saved[key]))))
            except (KeyError, ValueError, TypeError):
                pass

    def _save_state(self) -> None:
        try:
            STATE_FILE.write_text(json.dumps(
                {"x": self.position[0], "y": self.position[1],
                 "pin": self.pin, "scale": self.scale,
                 "opacity": self.opacity, "idle_opacity": self.idle_opacity}),
                encoding="utf-8")
        except OSError:
            pass

    # -- deplacement --------------------------------------------------------

    def _grab(self, event) -> None:
        self._origin = (event.x_root - self.root.winfo_x(),
                        event.y_root - self.root.winfo_y())
        self._dragged = False

    def _drag(self, event) -> None:
        if not hasattr(self, "_origin"):
            return
        self._dragged = True
        self.position = (event.x_root - self._origin[0], event.y_root - self._origin[1])
        self._place()
        self._save_state()
        # Panneau et carte restent accoles au widget pendant le deplacement.
        self.panel.reposition()
        self.place_map()

    def _place(self) -> None:
        """Positionne la fenetre. Une fois ancree au bureau, Tk ne controle plus
        sa position : geometry() est ignore, il faut passer par Win32."""
        if self.pin == "desktop" and self.hwnd:
            SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x1, 0x4, 0x10
            user32.SetWindowPos(self.hwnd, None, self.position[0], self.position[1],
                                0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        else:
            self.root.geometry("+%d+%d" % self.position)

    # -- ancrage ------------------------------------------------------------

    def apply_pin(self, mode: str | None = None) -> None:
        """Bascule premier plan / bureau. Appelable depuis le thread de l'icone."""
        if mode and mode != self.pin:
            self.pin = mode
            self._save_state()
        self.root.after(0, self._apply_pin_now)

    def _apply_pin_now(self) -> None:
        self.root.update_idletasks()
        # wm_frame() et non winfo_id() : Tk cree une fenetre interne (TkChild)
        # dans sa fenetre de premier niveau (TkTopLevel), et winfo_id() rend
        # l'interne. La reparenter la detacherait en fenetre autonome, laissant
        # deux widgets a l'ecran. wm_frame() rend le HWND de premier niveau.
        try:
            hwnd = int(self.root.wm_frame(), 16)
        except (tk.TclError, ValueError):
            hwnd = self.root.winfo_id()
        self.hwnd = hwnd

        if self.pin == "top":
            user32.SetParent(hwnd, None)   # detache du bureau s'il y etait
            self.root.attributes("-topmost", True)
        else:
            self.root.attributes("-topmost", False)
            pin_to_desktop(hwnd)
        # Tk rejoue sa propre geometrie juste apres un reparentage : on
        # repositionne en differe, sinon la fenetre retombe en 0,0.
        self.root.after(250, self._place)

    # -- rafraichissement ---------------------------------------------------

    def toggle(self) -> None:
        self.visible = not self.visible
        self.root.after(0, self.root.deiconify if self.visible else self.root.withdraw)

    def pump(self) -> None:
        """Vide la file d'evenements et redessine si necessaire."""
        try:
            while True:
                item = self.queue.get_nowait()
                if "status" in item:
                    self._set_status(item["status"], item.get("feed", ""))
                    continue
                region = item.get("region", "")
                if region not in self.rows:
                    continue  # region inconnue : on ignore plutot que d'inventer
                # Cle (region, type) : un essaim et un alpha peuvent etre actifs
                # dans la meme region sans que l'un chasse l'autre.
                key = (region, item.get("kind", "swarm"))
                previous = self.state.get(key)
                # Un evenement plus ancien ne doit pas ecraser un plus recent
                # (l'amorcage rejoue le cache dans l'ordre d'arrivee).
                if previous and item["received"] < previous["received"]:
                    continue
                # Le meme evenement arrive par les deux flux : celui d'Alphapedia
                # (texte) sans date d'expiration, le webhook (JSON) avec. On
                # conserve la date connue plutot que de la perdre.
                if (previous and not item.get("despawn") and previous.get("despawn")
                        and previous["pokemon"] == item["pokemon"]
                        and previous["location"] == item["location"]):
                    item["despawn"] = previous["despawn"]
                self.state[key] = item
        except queue.Empty:
            pass

        self._expire()
        self._render()
        # 500 ms : assez rapide pour que le compte a rebours ne saute aucune
        # seconde, sans cout notable (on ne redessine que si l'affichage change).
        self.root.after(500, self.pump)

    def _expire(self) -> None:
        now = time.time()
        for key, entry in list(self.state.items()):
            if now >= self._end(entry):
                del self.state[key]

    @staticmethod
    def _end(entry: dict) -> float:
        fallback = FALLBACK_DURATION.get(entry.get("kind", "swarm"), 25 * 60)
        return entry.get("despawn") or (entry["received"] + fallback)

    def _set_status(self, status: str, feed: str = "") -> None:
        """Etat par flux. La pastille montre le meilleur des deux : avec
        plusieurs flux, une coupure de l'un ne doit pas signaler une panne
        generale alors que l'autre alimente toujours le widget."""
        self.feed_status[feed] = status
        states = set(self.feed_status.values())
        self.connection = ("online" if "online" in states
                           else "connecting" if "connecting" in states
                           else "offline")

    def blink(self) -> None:
        """Pastille d'etat : vert clignotant des qu'un essaim est en cours.

        Le clignotement sert aussi de temoin de vie : s'il s'arrete, c'est que
        la boucle du widget est bloquee.
        """
        status = getattr(self, "connection", "connecting")
        if status == "offline":
            color = "#b04f4f"
        elif status == "connecting":
            color = "#b08b3f"
        elif self.state:
            self.blink_on = not self.blink_on
            color = ACTIVE if self.blink_on else ACTIVE_DIM
        else:
            color = ACCENT
        self.status.configure(fg=color)
        self.root.after(600, self.blink)

    def track_pointer(self) -> None:
        """Rend le widget plus transparent quand la souris n'est pas dessus.

        On sonde la position du pointeur plutot que d'utiliser <Enter>/<Leave> :
        ces evenements se declenchent aussi en passant d'un widget enfant a un
        autre, ce qui ferait clignoter l'opacite en permanence.
        """
        pointer_x, pointer_y = self.root.winfo_pointerxy()
        left, top = self.root.winfo_rootx(), self.root.winfo_rooty()
        over = (left <= pointer_x < left + self.root.winfo_width()
                and top <= pointer_y < top + self.root.winfo_height())

        target = self.opacity if over else self.idle_opacity
        if abs(target - self.current_alpha) > 0.005:
            # Fondu par paliers : un basculement sec accrocherait l'oeil.
            step = 0.06 if target > self.current_alpha else -0.06
            self.current_alpha = (min(target, self.current_alpha + step)
                                  if step > 0 else max(target, self.current_alpha + step))
            self.root.attributes("-alpha", round(self.current_alpha, 3))
        self.root.after(60, self.track_pointer)

    def pulse(self) -> None:
        """Halo rouge lent autour du widget quand un alpha est en cours.

        Les alphas sont rares (environ un par jour de jeu) : l'alerte doit
        sauter aux yeux sans clignoter agressivement, d'ou le degrade lent.
        """
        steps = GLOW_ALPHA if self.has_alpha() else (GLOW_SWARM if self.state else None)
        if steps:
            self.glow_step = (self.glow_step + 1) % len(steps)
            outer = steps[self.glow_step]
            # Le cadre interieur suit avec un decalage : cela adoucit la
            # transition et donne l'impression d'une lueur diffuse.
            inner = steps[(self.glow_step + 2) % len(steps)]
        else:
            outer = inner = BG   # rien en cours : aucun contour
            self.glow_step = 0

        if (outer, inner) != self.glow_last:
            self.glow_last = (outer, inner)
            self.glow_outer.configure(bg=outer)
            self.glow_inner.configure(bg=inner)
        self.root.after(180, self.pulse)

    # -- echelle ------------------------------------------------------------

    def change_opacity(self, delta: float | None = None, absolute: float | None = None):
        """Regle la transparence au repos. Appelable depuis le thread de l'icone.

        Seule l'opacite au repos est pilotee : celle au survol suit
        automatiquement si on demande plus opaque que le survol actuel, pour
        eviter qu'approcher la souris rende le widget PLUS transparent.
        """
        target = absolute if absolute is not None else self.idle_opacity + (delta or 0)
        target = min(1.0, max(0.15, round(target, 2)))
        if abs(target - self.idle_opacity) < 1e-6:
            return
        self.idle_opacity = target
        self.opacity = max(self.opacity, target)
        self._save_state()

    def change_scale(self, factor: float | None = None, absolute: float | None = None):
        """Change l'echelle a chaud. Appelable depuis le thread de l'icone."""
        target = absolute if absolute is not None else self.scale * (factor or 1.0)
        target = min(3.0, max(0.5, round(target, 3)))
        if abs(target - self.scale) < 1e-3:
            return
        self.root.after(0, lambda: self._rebuild(target))

    def _rebuild(self, scale: float) -> None:
        """Reconstruit l'interface a la nouvelle echelle.

        Polices, marges et cellules des sprites en dependent toutes : il est
        plus sur de tout reconstruire que de reconfigurer chaque widget.
        """
        self.scale = scale
        self.cell = (max(8, int(round(SPRITE_CELL[0] * scale * self.sprite_scale))),
                     max(8, int(round(SPRITE_CELL[1] * scale * self.sprite_scale))))
        self.panel.close()
        if self.map_window is not None:
            self.map_window.destroy()
            self.map_window = None
        self.hovered = None
        self.sprites.clear()      # les sprites sont mis a l'echelle de la cellule
        self.rows.clear()
        self.glow_last = (None, None)
        self._last_render = ""
        self.glow_outer.destroy()
        self._build()
        self._save_state()
        self._render()
        self._apply_pin_now()

    def _hover(self, region: str, index: int, entering: bool) -> None:
        """Accentue la ligne survolee (nom en bleu clair, sprite agrandi)."""
        slots = self.rows.get(region) or []
        if index >= len(slots):
            return
        widgets = slots[index]
        if not widgets.get("species"):
            return
        self.hovered = (region, index) if entering else None
        self._paint_row(widgets, entering)

    def _paint_row(self, widgets: dict, hovered: bool) -> None:
        english = widgets.get("species")
        if not english:
            return
        widgets["name"].configure(
            fg=FG_HOVER if hovered else widgets.get("base_fg", FG_VALUE))
        sprite = self._sprite(english, hover=hovered)
        if sprite:
            widgets["icon"].configure(image=sprite)

    def _click(self, event, region: str, index: int) -> None:
        """Ouvre la fiche. Ignore le clic s'il s'agissait d'un deplacement."""
        origin = getattr(self, "_origin", None)
        if origin and self._dragged:
            return
        slots = self.rows.get(region) or []
        if index >= len(slots):
            return
        widgets = slots[index]
        english = widgets.get("species")
        if english:
            self.panel.toggle(english, widgets.get("entry"))

    def _hover_place(self, region: str, index: int, entering: bool) -> None:
        """Accentue le lieu survole, independamment du nom."""
        slots = self.rows.get(region) or []
        if index >= len(slots) or not slots[index].get("species"):
            return
        widgets = slots[index]
        self.hovered_place = (region, index) if entering else None
        widgets["where"].configure(
            fg=FG_HOVER if entering else widgets.get("base_fg", FG_VALUE))

    def _click_place(self, event, region: str, index: int) -> None:
        """Clic sur le lieu : ouvre sa carte, sans toucher a la fiche Pokemon.

        Un second clic sur le meme lieu la referme, comme la fiche Pokedex : la
        carte n'ayant plus de fermeture au clic, c'est le geste naturel pour
        revenir en arriere sans viser la croix.
        """
        if self._dragged:
            return
        slots = self.rows.get(region) or []
        if index >= len(slots):
            return
        entry = slots[index].get("entry")
        if not entry:
            return
        wanted = (entry.get("region", ""), entry.get("location", ""))
        context = getattr(self, "_map_context", None) or {}
        showing = (context.get("region", ""), context.get("location", ""))
        if self.map_window is not None and showing == wanted:
            self.map_window.destroy()
            self.map_window = None
            return
        self.show_region(*wanted)

    def _remaining(self, entry: dict, now: float) -> int:
        return max(0, int(self._end(entry) - now))

    def _entries_for(self, region: str) -> list[dict]:
        """Evenements actifs d'une region, alphas en tete (plus rares)."""
        found = [self.state[(region, kind)]
                 for kind in ("alpha", "swarm") if (region, kind) in self.state]
        return found[:2]

    def has_alpha(self) -> bool:
        return any(kind == "alpha" for _, kind in self.state)

    def _render(self) -> None:
        now = time.time()
        # Empreinte de l'affichage : on ne touche aux widgets que s'il change.
        # Elle inclut les secondes, puisque le compte a rebours les affiche.
        signature = []
        for region, _ in REGIONS:
            entries = self._entries_for(region)
            if not entries:
                signature.append(f"{region}:-")
            for entry in entries:
                signature.append(f"{region}:{entry['kind']}:{entry['pokemon']}:"
                                 f"{self._remaining(entry, now)}")
        stamp = "|".join(signature)
        if stamp == self._last_render:
            return
        self._last_render = stamp

        for region, _ in REGIONS:
            entries = self._entries_for(region)
            for slot, widgets in enumerate(self.rows[region]):
                if slot >= len(entries):
                    if slot == 0:  # premiere ligne : toujours visible
                        widgets["species"] = None
                        widgets["entry"] = None
                        widgets["badge"].configure(text="")
                        widgets["tier"].configure(text="")
                        widgets["icon"].configure(image=self.blank)
                        widgets["name"].configure(text="---", fg=FG_EMPTY)
                        widgets["where"].configure(text="")
                        widgets["timer"].configure(text="")
                    else:
                        for w in widgets["_gridded"]:
                            w.grid_remove()
                    continue

                entry = entries[slot]
                kind = entry.get("kind", "swarm")
                if slot == 1:
                    for w in widgets["_gridded"]:
                        w.grid()

                widgets["badge"].configure(text=KIND_LABEL.get(kind, "Essaim"),
                                           fg=KIND_COLOR.get(kind, FG_TIMER))

                tier = self._tier_of(entry["pokemon"], entry)
                if tier is None or self.rarity == "none":
                    widgets["tier"].configure(text="")
                else:
                    # Les points sont le bareme de scoring des Shiny Wars, rebase
                    # a chaque edition (T0 valait 30 points en 2025, 50 en 2026).
                    # Le rang, lui, reste comparable : on ne l'affiche seul que
                    # par defaut, les points restant disponibles a la demande.
                    points = self.tier_points.get(tier)
                    label = f"T{tier}"
                    if self.rarity == "points" and points:
                        label += f" · {points} pts"
                    widgets["tier"].configure(text=label,
                                              fg=TIER_COLORS.get(tier, FG_TIMER))

                # Une ligne survolee garde son accentuation : le decompte
                # redessine chaque seconde, il ne doit pas l'effacer.
                is_hovered = self.hovered == (region, slot)
                sprite = self._sprite(entry["pokemon"], hover=is_hovered)
                widgets["icon"].configure(image=sprite if sprite else self.blank)
                base_fg = KIND_COLOR["alpha"] if kind == "alpha" else FG_VALUE
                widgets["species"] = entry["pokemon"]
                widgets["entry"] = entry
                widgets["base_fg"] = base_fg
                widgets["name"].configure(
                    text=f"{self._label(entry['pokemon'])}  |  ",
                    fg=FG_HOVER if is_hovered else base_fg)
                place_hovered = self.hovered_place == (region, slot)
                widgets["where"].configure(
                    text=self._place_name(entry["location"]),
                    fg=FG_HOVER if place_hovered else base_fg)

                left = self._remaining(entry, now)
                widgets["timer"].configure(
                    text=f"{left // 3600:02d}:{left // 60 % 60:02d}:{left % 60:02d}")


# --- Point d'entree -------------------------------------------------------


# Scene de demonstration : sert a produire la capture du README et a ouvrir
# l'interface sans attendre qu'un essaim tombe — les vrais evenements sont rares
# (un toutes les ~45 min, toutes regions confondues).
#
# Les deux alphas correspondent a de vraies entrees d'alpha_data.json
# (espece + region + lieu) : sans cela le bloc « capacite » resterait vide,
# et la capture ne montrerait pas ce qui distingue justement un alpha.
DEMO_SCENE = [
    # region, espece (anglais), lieu (anglais), type, minutes restantes
    ("Kanto",  "Growlithe", "Route 7",      "swarm", 18),
    ("Johto",  "Dragonite", "Dragon's Den", "alpha", 61),
    ("Hoenn",  "Altaria",   "Route 114",    "alpha", 47),
    ("Sinnoh", "Buizel",    "Route 205",    "swarm",  9),
    ("Unova",  "Munna",     "Dreamyard",    "swarm", 23),
]


def seed_demo(events: queue.Queue) -> None:
    """Remplit la file avec la scene de demonstration, sans toucher au reseau."""
    now = time.time()
    for region, pokemon, location, kind, minutes in DEMO_SCENE:
        events.put({"pokemon": pokemon, "region": region, "location": location,
                    "kind": kind, "tier": None, "received": now,
                    "despawn": now + minutes * 60})
    events.put({"status": "online", "feed": "demo"})


def main() -> int:
    parser = argparse.ArgumentParser(description="Widget de bureau des essaims PokeMMO.")
    parser.add_argument("--feed", action="append", default=[], metavar="URL",
                        help="flux ntfy a suivre, sous la forme "
                             "https://serveur/topic1,topic2 . Repetable. "
                             f"Par defaut : {OFFICIAL_FEED}")
    parser.add_argument("--topic", help="raccourci : topic ntfy personnel "
                                        "(ajoute un flux sur --server)")
    parser.add_argument("--server", default=NTFY_SERVER,
                        help=f"serveur associe a --topic (defaut {NTFY_SERVER})")
    parser.add_argument("--seed", default="12h",
                        help="profondeur du cache ntfy rejoue au demarrage "
                             "(12h max sur ntfy.sh, 'none' pour partir vide)")
    parser.add_argument("--pin", choices=["desktop", "top"], default="top",
                        help="top = premier plan (defaut) ; desktop = colle au bureau. "
                             "Basculable ensuite depuis l'icone systeme.")
    parser.add_argument("--lang", choices=["fr", "en"], default="fr",
                        help="langue des noms de Pokemon (defaut fr)")
    parser.add_argument("--scale", type=float, default=DEFAULT_SCALE,
                        help=f"echelle globale : texte, marges ET sprites. "
                             f"ex 1.3 pour agrandir l'ensemble (defaut "
                             f"{DEFAULT_SCALE}). Reglable ensuite depuis "
                             f"l'icone systeme ; la derniere valeur est retenue.")
    parser.add_argument("--sprite-scale", type=float, default=1.0,
                        help="multiplicateur supplementaire sur les seuls "
                             "sprites, par-dessus --scale (defaut 1.0)")
    parser.add_argument("--rarity", choices=["tier", "points", "none"],
                        default="tier",
                        help="rang de rarete affiche : tier = rang seul (defaut) ; "
                             "points = rang + bareme Shiny Wars ; none = rien")
    parser.add_argument("--opacity", type=float, default=0.97,
                        help="opacite quand la souris est sur le widget "
                             "(0.3 a 1.0, defaut 0.97)")
    parser.add_argument("--idle-opacity", type=float, default=0.72,
                        help="opacite quand la souris est ailleurs : laisse "
                             "voir ce qu'il y a derriere (defaut 0.72)")
    parser.add_argument("--demo", action="store_true",
                        help="scene fixe (2 alphas, 3 essaims) sans reseau, "
                             "fiche et carte ouvertes : sert a la capture du "
                             "README et a tester l'affichage")
    args = parser.parse_args()
    args.opacity = min(1.0, max(0.3, args.opacity))
    args.scale = min(3.0, max(0.5, args.scale))
    args.sprite_scale = min(3.0, max(0.25, args.sprite_scale))
    args.idle_opacity = min(1.0, max(0.15, args.idle_opacity))

    if not DATA_FILE.exists():
        print("[!] pokemon_data.json absent : lance d'abord `python fetch_assets.py` "
              "(noms francais + sprites).")

    urls = list(args.feed)
    if args.topic:
        urls.append(f"{args.server.rstrip('/')}/{args.topic}")
    if not urls:
        urls = [OFFICIAL_FEED]

    events: queue.Queue = queue.Queue()
    seed = None if args.seed == "none" else args.seed
    feeds = []
    if not args.demo:
        for url in urls:
            server, _, topic = url.rstrip("/").rpartition("/")
            if not server or not topic:
                parser.error(f"flux invalide : {url} (attendu https://serveur/topic)")
            feeds.append(NtfyFeed(server, topic, events, seed))

    root = tk.Tk()
    widget = SwarmWidget(root, events, args.pin, args.opacity, args.lang,
                         args.scale, args.sprite_scale, args.rarity,
                         args.idle_opacity)

    def quit_all() -> None:
        for f in feeds:
            f.stop.set()
        tray.remove()
        root.after(0, root.destroy)

    tip = ("Essaims PokeMMO — demonstration" if args.demo
           else "Essaims PokeMMO — " + ", ".join(f.topic for f in feeds))
    tray = TrayIcon(tip, widget.toggle, quit_all,
                    widget.apply_pin, lambda: widget.pin,
                    widget.change_scale, lambda: widget.scale,
                    widget.change_opacity, lambda: widget.idle_opacity)
    tray.start()
    for f in feeds:
        f.start()

    if args.demo:
        seed_demo(events)
        # On laisse le premier rendu se faire avant d'ouvrir les panneaux :
        # toggle() a besoin que la ligne existe pour se placer a cote d'elle.
        root.after(900, lambda: widget.panel.toggle(
            "Altaria", widget.state.get(("Hoenn", "alpha"))))
        root.after(1300, lambda: widget.show_region("Hoenn", "Route 114"))

    root.after(120, widget.apply_pin)
    root.after(400, widget.pump)
    root.after(500, widget.blink)
    root.after(600, widget.pulse)
    root.after(700, widget.track_pointer)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        quit_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
