# Sous le capot

Tout est écrit avec la bibliothèque standard. `fetch_assets.py` construit les
ressources une fois pour toutes ; `swarm_widget.py` ne fait que lire et afficher.

## Noms et sprites

Le client PokeMMO ne contient **ni les noms ni les sprites** des Pokémon : il les
lit dans les ROMs fournies par le joueur, absentes de l'installation. Vérifié :
`data.pak` est du gzip de données binaires sans chaînes, `models.pak` ne contient
que des modèles 3D, `particles.pak` des effets, `atlas/` l'interface. Les
`strings_*.xml` n'ont aucun nom de Pokémon.

| Ressource | Source | Poids |
|---|---|---|
| `pokemon_data.json` — noms FR des Pokémon, lieux et régions, + n° du Pokédex | tables de traduction d'[Alphapedia](https://alpha.pokemmotools.org/) + [fanzeyi/pokemon.json](https://github.com/fanzeyi/pokemon.json) | 160 Ko |
| `pokemon_tiers.json` — tier de rareté et barème | page *Shiny Tiers* d'Alphapedia | 9 Ko |
| `alpha_data.json` — capacité figée de chaque alpha | Alphapedia | 46 Ko |
| `sprites/` — icônes gen VIII | [PokeAPI/sprites](https://github.com/PokeAPI/sprites) | 1,2 Mo |
| `sprites_big/` — images 96×96 | PokeAPI | 1,8 Mo |
| `sprites_alpha/` — variantes à halo rouge | générées localement | 2,7 Mo |
| `sprite_bbox*.json` — cadrage utile de chaque sprite | calculé localement | 39 Ko |
| `regions.json` — emprise des 486 lieux | décompilations `pret` + pokebip | 31 Ko |

## Les contres

La table d'efficacité des types est **locale**, comme les couleurs et les
traductions de types. Seuls les rapports différents de 1 sont écrits.

**Elle est en cinquième génération, pas en sixième** — PokeMMO s'arrête à
Noir/Blanc. Deux écarts avec la table moderne, et ils comptent :

| | Moderne | PokeMMO (5ᵉ gén.) |
|---|---|---|
| Type Fée | existe | **n'existe pas** — une demande d'ajout a été refusée sur le forum du jeu |
| Acier contre Spectre et Ténèbres | neutre | **résiste** (×0.5) |

Les 22 espèces que la sixième génération a retypées reviennent donc à leurs
types d'époque : Mélofée redevient Normal, Marill Eau, Mysdibule Acier. Le
pokédex public utilisé pour les noms donne les types modernes ; `fetch_assets.py`
lit `past_types` de PokeAPI en `generation-v` pour les corriger — une vingtaine
d'appels plutôt que 649. La table, elle, a été vérifiée contre
`past_damage_relations` de PokeAPI pour la même génération.

Le classement des contres retient trois critères, dans cet ordre :

1. **Ce que le candidat inflige** — le meilleur rapport de ses propres types
   contre la combinaison défensive de la cible. En dessous de ×2, il est écarté.
2. **Ce qu'il encaisse en retour** — le pire rapport des types de la cible
   contre les siens.
3. **Sa meilleure statistique offensive**, avec un appoint de vitesse.

> **Ce que ce classement ignore, et c'est beaucoup.** Faute de données
> d'attaques, il suppose que chaque espèce porte une attaque de son propre type
> — hypothèse courante mais pas toujours vraie, et qui passe à côté de toute
> couverture hors type. Il ne connaît ni les talents, ni les objets, ni les
> niveaux, ni le moindre contexte de combat. C'est un point de départ de
> réflexion, pas un verdict compétitif.

**Deux espèces n'ont aucun contre**, et c'est correct : Spiritomb et Ténéfix
sont Spectre/Ténèbres, une combinaison qu'**aucun type ne frappe en
super-efficace** en cinquième génération. Ils sont même immunisés au Normal, au
Combat et au Psy. C'est précisément le type Fée qui leur a donné une faiblesse
en sixième — et il n'existe pas dans PokeMMO. Le panneau l'explique plutôt que
d'afficher une liste vide.

## Les cris

649 cris, environ 8 Ko chacun, **5,0 Mo** au total — téléchargés depuis Pokémon
Showdown, rangés sous le numéro de Pokédex.

Le MP3 n'est pas un choix esthétique mais le seul format lisible sans
dépendance. `winsound` ne lit que du WAV ; MCI (`winmm.dll`) ouvre le MP3
nativement mais **refuse l'OGG** — vérifié, l'ouverture échoue en automatique,
en `type mpegvideo` et en `type waveaudio`.

L'écart de poids est de toute façon négligeable, contrairement à ce que laissait
croire un premier sondage :

| Source | Moyenne | Total 649 |
|---|---|---|
| OGG d'époque (PokeAPI `legacy`) | 7,6 Ko | 4,8 Mo |
| **MP3 (Showdown)** | **7,8 Ko** | **5,0 Mo** |
| OGG « latest » (PokeAPI) | 13,5 Ko | 8,5 Mo |

Le format lourd est l'OGG *latest*, pas le MP3 : 200 Ko séparent le MP3 de
l'OGG d'époque sur l'ensemble, soit 4 %.

> Les deux Nidoran ont demandé une exception : leur symbole de genre disparaît à
> la normalisation et les confond tous deux en `nidoran`. Showdown les distingue
> par un suffixe (`nidoranf`, `nidoranm`) — table `CRIES_ALIASES`.

## Les noms de lieux

Alphapedia publie **ses propres tables de traduction**, celles que son site
utilise pour s'afficher :

```
/static/translations/<lang>/locationPokeapi-<lang>.json   946 lieux
/static/translations/<lang>/pokemon-species-<lang>.json   682 Pokémon
/static/translations/<lang>/region-<lang>.json              5 régions
```

C'est la meilleure source possible : les noms correspondent exactement à ce que
tu vois sur leur site, et aux conventions de PokeMMO.

```
Jagged Pass      -> Sentier Sinuroc
Viridian Forest  -> Forêt de Jade
Shoal Cave       -> Grotte Tréfonds
Sprout Tower     -> Tour CHETIFLOR
Route 103        -> Route 103          (identique, normal)
```

Langues disponibles : `en`, `de`, `es`, `fr`, `it`, `pt`, `zh`.
`python fetch_assets.py --lang es --force` bascule tout l'ensemble.

> Alphapedia n'envoie **que l'anglais** dans son payload (`"pokemon": "Zangoose"`),
> quelle que soit la langue réglée sur le profil. La traduction est donc faite
> localement : `Zangoose` → **Mangriff**.

**Quand le lieu ne correspond pas au jeu.** Il arrive que le jeu annonce un
endroit plus précis qu'Alphapedia : un essaim donné pour `Seven Island` peut être
annoncé en jeu « près de la Tour des Dresseurs », qui se trouve sur cette île. Ce
n'est pas un défaut de traduction — vérifié, le payload ne contient rien de plus
fin. C'est la granularité choisie par le contributeur. Le champ `HMs` donne
souvent l'indice manquant : pour un Staross il valait `["Surf"]`, l'essaim était
donc dans l'eau autour de l'île.

## La rareté — et ses limites

Le rang affiché (`T0` à `T7`) vient du classement **Shiny Tiers** d'Alphapedia,
établi pour les [Shiny Wars](https://pokemmo.shoutwiki.com/wiki/Shiny_Wars). Les
tiers y regroupent les espèces « par rareté, taux de rencontre et temps de chasse
moyen », et **toute une lignée évolutive vaut le même score**. Plus le tier est
**bas**, plus l'espèce est rare : T0 est le sommet.

| Tier | Couleur | Points 2026 |
|---|---|---|
| T0 | or | 50 |
| T1 | ambre | 40 |
| T2 | orange | 30 |
| T3 | bleu clair | 20 |
| T4 – T7 | bleu-gris dégradé | 15 → 3 |

> ⚠️ **Ce classement est recalibré à chaque édition.** Mesuré entre les jeux de
> données 2025 et 2026 : seuls **118 Pokémon sur 282 (42 %)** ont conservé leur
> tier, 126 ont bougé d'un rang, 32 de deux à sept rangs. Le barème a été
> entièrement rebasé (T0 valait 30 points en 2025, 50 en 2026) et un huitième
> tier a été ajouté.
>
> C'est donc un **indicateur de valeur de chasse à un instant donné**, pas une
> mesure permanente de rareté. Pour cette raison le widget n'affiche que le
> **rang** par défaut — `--rarity points` pour les deux, `--rarity none` pour
> masquer.

**Propagation le long de la lignée** : Alphapedia ne classe qu'un membre par
lignée évolutive (Racaillou T7, mais rien pour Gravalanch ni Grolem). Comme une
lignée entière vaut le même score, `fetch_assets.py` reconstitue les chaînes via
PokeAPI et partage le tier : **597 Pokémon couverts** sur 649. Les 52 restants —
des légendaires, hors événement — n'affichent aucun tier plutôt qu'une valeur
inventée.

> Le partage se fait **dans les deux sens**, et pas seulement vers les
> évolutions. Le membre classé n'est pas toujours le plus bas de la chaîne : les
> quinze bébés (Pichu, Mime Jr., Goinfrex…) n'ont aucun ancêtre, et c'est leur
> évolution qu'Alphapedia classe. Remonter la chaîne les laissait sans tier.
>
> En cas de désaccord entre membres classés, on s'abstient. La lignée Ninjask
> porte Nincada et Ninjask en T2 mais **Munja en T0** — bien plus rare — et
> deviner y serait faux.

## Le rognage des sprites

Les icônes gen VIII sont des cadres de 68×56 où le Pokémon n'occupe que **7 à
13 %** de la surface, calé en bas (médiane du contenu utile : **24×22 px**).
Affichées telles quelles, elles paraissent minuscules et imposent des lignes deux
fois trop hautes pour du vide.

`fetch_assets.py` calcule donc le cadre utile de chaque sprite avec un décodeur
PNG minimal (zlib + défiltrage, ~1,7 s pour les 649, sans Pillow). Le widget
recadre, puis met **chaque sprite à l'échelle individuellement** pour qu'ils
occupent tous la même cellule, quelle que soit la corpulence du Pokémon.

`PhotoImage` ne sachant redimensionner que par des entiers, le facteur voulu est
approché par une fraction (`zoom(n)` puis `subsample(d)`), toujours choisie
**inférieure ou égale** à la cible pour qu'aucun sprite ne déborde de sa cellule —
vérifié sur les 649.

La grande image utilise un **second jeu de sprites** (96×96) : agrandir les
icônes 68×56 les rendrait illisibles. Elle est contrainte par les **deux**
dimensions d'un cadre de 128×120, sans déformation — un Pokémon large et plat
comme Racaillou serait sinon sorti du panneau.

## Le halo des alphas

Aucun jeu de sprites alpha n'est distribué publiquement : l'aura est un effet de
rendu du jeu, et Alphapedia affiche elle-même les sprites ordinaires.

`fetch_assets.py` décode chaque sprite, calcule par **propagation en largeur** la
distance de chaque pixel vide à la silhouette, puis peint un halo dont l'opacité
décroît de façon quadratique avec cette distance — avant de ré-encoder le PNG.
649 variantes, ~20 s, 2,7 Mo, aucune dépendance graphique.

Mesuré sur le résultat : **5 niveaux d'opacité** de 74 % à 2 %, soit un dégradé
et non un bord net, et un halo qui reste translucide.

## Les cartes de région

Trois régions sont **reconstituées** depuis les décompilations
[pret](https://github.com/pret) : le tileset et le tilemap de la carte du monde
sont téléchargés, assemblés, puis les emprises des lieux sont lues dans les
données de landmarks. Hoenn a demandé trois hypothèses fausses avant de trouver
que son tilemap est **planaire** et non des `u16` empaquetés.

> Une entrée de tilemap GBA porte l'index de tuile sur **10 bits**, puis les
> miroirs et la palette. Le masquer sur 8 bits repliait toute tuile ≥ 256 sur
> une autre — et le tileset en compte 320. La carte principale de Kanto n'en
> utilise que 6 au-delà (1 %), donc elle restait crédible ; Sevii 6-7 en utilise
> 30 (5 %) et devenait méconnaissable. Les bits de palette, eux, sont ignorés à
> dessein : le PNG de `pret` stocke des index absolus sur ses 80 couleurs, donc
> chaque tuile y porte déjà la sienne.

> Kanto ne passe pas par des landmarks mais par son **layout MAPSEC**, une
> grille où chaque tuile porte le nom de la zone qui l'occupe : les emprises y
> sont exactes par construction, sans calage. Encore faut-il lire la grille
> correctement — les couches y sont mises bout à bout et `[LAYER_COUNT]`, simple
> marqueur de taille, compte comme une découpe sans porter de ligne. Retrouver
> la hauteur en divisant le total par le nombre de découpes donnait 10 au lieu
> de 15 et repliait les cinq dernières lignes sur les premières.

Sinnoh et Unys sont **fournies à la main** (`regions/`) : la grille de Sinnoh est
projetée sur l'image par une transformation affine calée par recherche
exhaustive, et Unys n'a aucune décompilation.

> Le critère de calage compte la **part** de chaque repère qui tombe sur un
> tracé, et non le simple fait qu'il en touche un. La nuance n'est pas
> cosmétique : un repère posé de travers effleure presque toujours la route
> voisine, si bien qu'un premier calage obtenait 97 % au critère binaire tout en
> ne recouvrant réellement que **44 %** — Route 230 tombait à côté de sa voie
> maritime. Le calage retenu recouvre **94 %** et ne laisse aucun repère hors
> cadre.

**Unys, via pokebip.** Chaque page de lieu du guide publie la carte de la région
avec l'emprise du lieu **tracée en rouge sur un fond commun**. Plutôt que de
stocker 84 images, `unova_places()` isole les pixels rouges et en déduit la
boîte : une seule carte suffit. Les deux guides sont lus, Noir/Blanc 2 en
dernier — c'est sa carte que PokeMMO utilise, sud-ouest compris. Recalage vérifié
sur la carte fournie : **93 % de contours communs à décalage nul**, contre 49 %
au décalage suivant.

> Le décodeur PNG maison gère les types de couleur 0, 2, 3 et 6, les profondeurs
> 1/2/4/8 et l'**entrelacement Adam7** — sans quoi une carte entrelacée se décode
> en bruit, silencieusement.

---

---

## Pourquoi pas l'interception réseau

C'était la piste initiale, techniquement faisable mais inadaptée :

- protocole **chiffré et compressé**, TLS maison comparant la clé publique signée
  du serveur à un **certificat codé en dur** → un proxy MITM impose de **patcher
  le binaire** ;
- les ToS indiquent que le client **scanne la RAM** et remonte au serveur le nom
  du compte et les détails du programme détecté. Le *client tampering* et
  l'injection JVM sont des motifs de ban documentés ;
- client obfusqué (`f.ej2`, `f.k12`…) : tout hook casse à chaque mise à jour.

---

[← Retour au README](../README.md)
