# PokeMMO Swarm Widget

<img src="docs/screenshot.png" alt="Le widget, la fiche Pokédex d'Altaria et la carte de Hoenn" width="660">

*Deux alphas en cours — Dracolosse à Johto, Altaria à Hoenn — en rouge, d'où le
halo qui entoure le widget ; les trois autres régions sont de simples essaims.
À droite, la fiche d'Altaria avec son sprite auréolé, ses deux types et sa
capacité figée. Au-dessus, la carte de Hoenn, Route 114 encadrée.*

[![Licence MIT](https://img.shields.io/badge/licence-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/plateforme-Windows%2010%2F11-0078d4.svg)](#installation)
[![Sans dépendance](https://img.shields.io/badge/d%C3%A9pendances-aucune-lightgrey.svg)](requirements.txt)

**Un panneau posé sur le bureau qui montre les essaims et les alphas PokeMMO des
cinq régions, en temps réel — sans lancer le jeu.**

Un essaim dure environ 25 minutes, un alpha 75. Les repérer suppose d'ouvrir la
carte du jeu régulièrement, donc de jouer, donc de rester connecté. Ce widget
retire cette contrainte : il écoute les annonces de la communauté et les affiche
dans un petit panneau toujours visible, que le jeu tourne ou non.

Survol d'un sprite : il grossit. Clic : une fiche Pokédex s'ouvre à côté —
rareté, types, statistiques, capacité de l'alpha. Clic sur le lieu : la carte de
la région s'affiche, l'endroit encadré.

---

## Sommaire

- [Ce que ça fait](#ce-que-ça-fait)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Le widget en détail](#le-widget-en-détail)
- [Les flux de données](#les-flux-de-données)
- [Sous le capot](#sous-le-capot)
- [Ce que ce widget ne fait jamais](#ce-que-ce-widget-ne-fait-jamais)
- [Limites connues](#limites-connues)
- [Contribuer](#contribuer)
- [Licence](#licence)
- [Crédits et mentions légales](#crédits-et-mentions-légales)

---

## Ce que ça fait

| | |
|---|---|
| **Cinq régions à la fois** | Kanto, Johto, Hoenn, Sinnoh, Unys — une ligne chacune, deux emplacements par région (un essaim *et* un alpha peuvent coexister) |
| **Sans lancer le jeu** | les données viennent du flux public d'Alphapedia, pas du client |
| **Compte à rebours à la seconde** | `hh:mm:ss`, qui sert aussi de témoin de vie |
| **Noms français** | Pokémon *et* lieux, depuis les tables d'Alphapedia |
| **Fiche Pokédex** | rareté, types colorés, six jauges de statistiques, capacité figée des alphas |
| **Cartes de région** | 467 lieux repérés sur les cartes officielles, plus 49 cartes annotées par la communauté |
| **Alphas signalés** | badge rouge, sprite cerclé de rouge, halo pulsant autour du widget |
| **Discret** | translucide au repos, opaque au survol, ancrable au bureau ou au premier plan |
| **Rien sur le disque** | l'état vit en mémoire ; seuls position, échelle et transparence sont retenus |
| **Aucune dépendance** | bibliothèque standard uniquement, Pillow compris |

---

## Installation

**Prérequis** : Windows 10 ou 11, Python 3.10+ avec tkinter (inclus dans
l'installeur officiel de [python.org](https://www.python.org/)).

```powershell
git clone https://github.com/<toi>/pokemmo-swarm-widget.git
cd pokemmo-swarm-widget
python fetch_assets.py      # une seule fois : sprites et cartes
pythonw swarm_widget.py
```

Ou double-clic sur `start_widget.cmd`.

`fetch_assets.py` télécharge ce que le dépôt ne peut pas contenir : 649 icônes,
649 grandes images, 649 variantes à halo rouge, et les cartes annotées de la
communauté — environ 6 Mo, plus 42 Mo si tu gardes les cartes annotées. Les
données dérivées (noms, raretés, coordonnées des lieux) sont, elles, versionnées :
inutile de les reconstruire.

> Rien à installer avec `pip`. `requirements.txt` est vide de dépendances et
> documente simplement les prérequis.

---

## Utilisation

```powershell
pythonw swarm_widget.py
```

`pythonw` plutôt que `python` : aucune fenêtre de console. **Sans aucun
argument**, le widget suit le serveur ntfy public d'Alphapedia — alphas et
essaims des cinq régions, aucun compte à créer. Il se ferme depuis l'icône de la
zone de notification.

### Options

```powershell
pythonw swarm_widget.py ^
    --feed https://serveur/topic1,topic2   # repetable
    --topic <ton-topic>                    # raccourci sur --server
    --server https://ntfy.sh               # serveur associe a --topic
    --pin top^|desktop                     # premier plan (defaut) ou colle au bureau
    --lang fr^|en                          # langue des noms (defaut fr)
    --scale 0.85                           # echelle GLOBALE : texte, marges, sprites
    --sprite-scale 1.0                     # multiplicateur sur les seuls sprites
    --opacity 0.97                         # opacite au survol
    --idle-opacity 0.72                    # opacite au repos ; 1.0 pour desactiver
    --rarity tier^|points^|none            # rang seul (defaut), + bareme, ou rien
    --seed 12h^|none                       # historique rejoue au demarrage
    --demo                                 # scene fixe, sans reseau
```

`--demo` remplit le widget avec deux alphas et trois essaims, puis ouvre la
fiche et la carte — c'est ce qui a produit la capture ci-dessus. Utile pour voir
l'interface sans attendre : un essaim ne tombe que toutes les ~45 min.

`--scale` agit sur **tout l'ensemble** : c'est le réglage pour agrandir ou
réduire le widget d'un bloc.

| `--scale` | Cellule sprite | Widget |
|---|---|---|
| `0.6` | 28×25 | très compact |
| `0.85` *(défaut)* | 39×36 | ~342×249 |
| `1.3` | 60×55 | grand |

`--sprite-scale` vient **par-dessus**, pour grossir les seuls sprites sans
toucher au texte (ex. `--scale 0.7 --sprite-scale 1.4`).

### Au démarrage de Windows

```powershell
powershell -ExecutionPolicy Bypass -File install_startup.ps1
```

Crée un raccourci dans `shell:startup`. Aucune écriture dans le registre, aucun
droit administrateur. Pour désactiver : `install_startup.ps1 -Remove`.

Le widget rouvre à sa **dernière position**, dans son dernier mode, à sa dernière
échelle et transparence. Une position devenue hors écran (écran débranché,
changement de résolution) est rejetée au profit du coin par défaut.

---

## Le widget en détail

### La pastille d'état

| Pastille | Sens |
|---|---|
| 🟢 vert **clignotant** | au moins un essaim en cours |
| 🔵 bleu fixe | connecté, aucun essaim |
| 🟠 orange | connexion en cours |
| 🔴 rouge | déconnecté (reconnexion automatique) |

Elle agrège les flux : elle ne passe au rouge que si **tous** sont tombés.

### La fiche Pokédex

**Survol** du sprite ou du nom : le nom passe en bleu clair et le sprite grossit
d'environ 20 %. La marge est prévue dès le départ — au repos le sprite n'occupe
que 85 % de sa cellule — pour qu'il grossisse **sans bousculer la mise en page**.

**Clic** : un panneau s'ouvre **accolé au widget**, du côté où il y a le plus de
place, à la même hauteur et aligné sur son sommet. Il suit le widget quand on le
déplace. Un nouveau clic sur le même Pokémon le referme, tout comme la croix.

| Élément | Détail |
|---|---|
| Nom et n° | nom localisé + numéro, suivi de **↗** qui ouvre la fiche en ligne |
| **Grande image** | sprite de face 96×96, rogné et mis à l'échelle |
| **Rareté** | rang et barème, sur fond coloré selon le tier |
| **Types** | étiquettes traduites, sur fond de la couleur du type |
| **Stats de base** | six jauges (PV, Att, Déf, Att.Spé, Déf.Spé, Vit) + total |
| **Capacité** *(alphas seulement)* | la capacité figée de cet alpha, en rouge |

Le lien est une simple icône **↗** posée à côté du numéro : en bas de panneau, un
libellé texte se faisait couper quand le widget était court.

Les jauges se remplissent par rapport à **180** et non au maximum absolu (255) :
au-delà de 180 une stat est déjà exceptionnelle, et calibrer sur 255 écraserait
visuellement tout le reste.

> Les 18 types sont traduits et colorés localement : Alphapedia ne publie pas de
> table de traduction pour eux (404 sur `type-fr.json`), et ces valeurs ne
> changent jamais.

### La carte de la région

Un clic sur le **nom du lieu** ouvre la carte officielle de la région, dans un
panneau de la largeur du widget, avec l'emprise du lieu encadrée. Le bouton
d'agrandissement double la taille ; il revient au normal à la fermeture. Les
régions à couches (îles Sevii pour Kanto) n'affichent que la couche contenant
le lieu.

Un clic sur le **repère** lui-même bascule sur la carte annotée de la communauté
quand il y en a une, avec un bouton **←** pour revenir.

| Région | Lieux repérés | Source des coordonnées |
|---|---|---|
| Sinnoh | 123 | `pokeplatinum` + calage affine |
| Johto | 95 | `pokecrystal` |
| Kanto | 83 | `pokefirered`, 3 couches Sevii |
| Unys | 84 | guides pokebip Noir/Blanc et Noir/Blanc 2 |
| Hoenn | 82 | `pokeemerald` |

### La carte annotée du lieu

Quand une carte annotée existe pour le lieu, une icône **🗺** apparaît à côté de
son nom dans la fiche. Un clic l'ouvre en grand — c'est la carte du jeu, avec le
spot marqué et les annotations de la communauté (*Mach Bike*, *Flash*,
itinéraires…). Clic, `Échap` ou la croix pour fermer.

> **La couverture est partielle** : 49 lieux sur plusieurs centaines. Alphapedia
> expose un champ `Map Link` qui n'est rempli que pour 72 spawns sur 1107 —
> essentiellement des grottes et intérieurs, là où s'orienter est le plus
> pénible. Les routes en extérieur en ont rarement.
>
> Réparties ainsi : Hoenn 14, Johto 12, Sinnoh 10, Unys 10, Kanto 9.
>
> Elles sont téléchargées en local (**42 Mo**). Six sont au format JPEG, que Tk
> ne sait pas lire : elles s'ouvrent dans le navigateur. Supprime le dossier
> `maps/` si le poids te gêne — l'icône basculera sur le lien distant.

Les fichiers `.pm3d` du client n'ont pas été utilisés : PokeMMO ne conserve que
3 cartes en cache local, et les décoder reviendrait à rétro-concevoir le
client — ce que ce projet s'interdit.

### Ce qui change pour un alpha

1. **Son image est cerclée de rouge**, comme l'aura que PokeMMO leur donne.
2. Un bloc affiche sa **capacité**, en rouge.
3. Le widget entier s'entoure d'un **halo rouge pulsant** tant qu'il est actif.

La capacité n'existe que pour les alphas — vérifié sur les données
d'Alphapedia : **310 entrées alpha sur 310** la portent, contre **0 sur 797**
entrées d'essaims. C'est ce qui fait leur intérêt, leur capacité étant figée et
parfois inaccessible autrement.

> Si le lieu annoncé ne correspond à aucune entrée du catalogue, le repli sur
> l'espèce seule ne s'applique **que si elle n'a qu'une apparition connue** :
> deux spawns d'une même espèce ont des capacités différentes, et afficher celle
> du mauvais serait pire que de ne rien montrer.

> Le **sprite d'un alpha est celui de son espèce** : dans PokeMMO un alpha est un
> individu particulier, pas une forme distincte, et Alphapedia n'envoie aucune
> image spécifique. La distinction se fait par le badge, la couleur et le halo.

### Halo et transparence

Le contour du widget pulse lentement selon ce qui est en cours :

| État | Contour |
|---|---|
| Au moins un **alpha** | 🔴 rouge pulsant (le plus visible) |
| Uniquement des **essaims** | 🟢 vert pulsant, plus sourd |
| Rien en cours | aucun contour |

Le widget est **légèrement transparent au repos** (`0.72`) et redevient opaque
(`0.97`) au passage de la souris, avec un fondu progressif. On voit donc ce qu'il
y a derrière sans avoir à le déplacer.

> La position du pointeur est **sondée** plutôt que suivie via `<Enter>`/`<Leave>` :
> ces événements se déclenchent aussi au passage d'un widget enfant à un autre,
> ce qui ferait clignoter l'opacité en continu.

### Le menu de l'icône système

Clic gauche : afficher/masquer. Clic droit :

| Entrée | Effet |
|---|---|
| Premier plan / Arrière-plan | bascule l'ancrage (coche sur le mode actif) |
| Agrandir (+10 %) | agrandit tout le widget, à chaud |
| Réduire (−10 %) | réduit tout le widget, à chaud |
| Taille par défaut | revient à `0.85`, affiche l'échelle courante |
| Plus opaque (+5 %) | rend le widget moins transparent au repos |
| Plus transparent (−5 %) | le rend plus discret |
| Transparence par défaut | revient à `72 %`, affiche la valeur courante |
| Afficher / masquer | |
| Quitter | ferme le widget |

Taille **et** transparence sont retenues pour les lancements suivants
(`.widget_state.json`).

Le menu règle l'opacité **au repos** ; celle au survol suit automatiquement si on
demande plus opaque qu'elle, pour qu'approcher la souris ne rende jamais le
widget *plus* transparent. Bornes : 15 % à 100 %.

---

## Les flux de données

### Les deux flux

Alphapedia **héberge son propre serveur ntfy**, documenté dans sa page d'aide :
`https://ntfy.pokemmotools.org`, topics publics `alphapings` et `swarmpings`.
Aucun compte ni configuration. Mais ses messages sont en **texte simple** :

```
title   = "Golem"
message = "Hoenn\nJagged Pass"
```

Pas de `despawnTimestamp` : sur ce flux seul, le compte à rebours repose sur les
durées par défaut (25 min / 75 min). Un webhook personnel, lui, envoie du JSON
complet avec la date d'expiration exacte. D'où la combinaison possible :

| Flux | Couvre | Expiration |
|---|---|---|
| `https://ntfy.pokemmotools.org/alphapings,swarmpings` *(défaut)* | alphas **et** essaims | estimée |
| ton webhook (scope `Both`) sur `ntfy.sh` | selon la config de ton profil | **exacte** |

Quand le même événement arrive par les deux, le widget **conserve la date exacte**
plutôt que de la perdre au profit de l'estimation.

Au démarrage, le cache ntfy des 12 dernières heures est rejoué pour afficher
l'état courant immédiatement. Chaque message rejoué garde **son horodatage
d'origine** (champ `time` de ntfy), donc les événements déjà expirés ne
réapparaissent pas et les décomptes restent justes.

> Le serveur d'Alphapedia est derrière Cloudflare et répond **403** à l'agent par
> défaut de Python, en souscription comme en interrogation ponctuelle. Le widget
> envoie donc un `User-Agent` de navigateur.

### Configurer son propre topic ntfy

Utile uniquement pour obtenir les **dates d'expiration exactes**. Le principe :
un webhook classique exige que *tu* exposes une URL publique. ntfy inverse le
sens — ton PC ouvre une connexion **sortante** et la garde ouverte, les messages
descendent dedans. Pas d'IP fixe, pas de port ouvert, ça marche derrière
n'importe quel routeur ou 4G.

```
Alphapedia  --POST-->  ntfy.sh/<topic>  <--GET (connexion ouverte)--  ton PC
                       (l'URL publique                                (aucune URL
                        que tu n'as pas                                a exposer)
                        a heberger)
```

Sur ton profil Alphapedia : soit l'intégration ntfy native, soit le champ
« webhook URL » dans lequel tu colles `https://ntfy.sh/<ton-topic>`. Puis :

```powershell
pythonw swarm_widget.py --topic <ton-topic>
```

> ⚠️ Les noms de topics ntfy sont **publics** : qui connaît le nom lit le flux, et
> n'importe qui peut y publier. Prends un nom long et non devinable, et ne le
> partage pas — surtout pas dans un dépôt public. Pour un vrai contrôle d'accès,
> ntfy supporte les comptes, les topics protégés et l'auto-hébergement.

Pour vérifier un topic à la main :

```powershell
curl https://ntfy.sh/<ton-topic>/json          # ecoute (Ctrl+C pour sortir)
curl -d "test" https://ntfy.sh/<ton-topic>     # publie, depuis une autre fenetre
```

Un topic vide n'est concluant **que si un essaim a été publié depuis** la
configuration du webhook — ils ne tombent que toutes les ~45 min.

### Essaims et alphas

Alphapedia publie sur deux canaux, que le widget distingue par le champ `topic`
du payload (`swarmpings` / `alphapings`, variantes `-test` incluses), avec
`originalJson.sourcePage` comme second indice :

| Type | Badge | Durée de repli | Rendu |
|---|---|---|---|
| Essaim | `Essaim` gris | 25 min | texte clair |
| Alpha | `ALPHA` rouge | 75 min | texte rouge + halo rouge pulsant |

Un essaim **et** un alpha peuvent être actifs dans la même région : chaque région
dispose de deux emplacements, le second n'apparaissant qu'en cas de besoin.
L'alpha est toujours affiché en premier.

> Pour recevoir les alphas sur ton propre topic, il faut activer **les deux**
> intégrations sur ton profil Alphapedia (`alphapings` en plus de `swarmpings`),
> en pointant sur le même topic.

### Durée d'un essaim

Le payload d'Alphapedia porte **la durée réelle**, ce qui évite toute
approximation :

```json
"swarmDurationMinutes": 25,
"despawnTimestamp": 1786616190
```

Vérifié : `despawnTimestamp` vaut exactement l'heure d'annonce + 25 min. Le
widget se cale dessus et retire la ligne à l'expiration — cohérent avec le wiki,
qui situe les essaims autour de 20-30 min
([Mass Outbreak](https://pokemmo.shoutwiki.com/wiki/Mass_Outbreak)).
La durée de repli (25 min) ne sert que si un payload n'a pas ce champ.

### Format réel d'Alphapedia — vérifié

Capté en direct le 2026-08-13 à 12:51:52. Alphapedia poste un **JSON à plat** :

```json
{
  "id": 2972,
  "pokemon": "Zangoose",
  "region": "Kanto",
  "location": "Route 14",
  "timestamp": "2026-08-13 09:51:30.902993",
  "published_by": "andreah2o",
  "topic": "swarmpings",
  "originalJson": { "data": { "HMs": ["Cut"], "…": "métadonnées Pokédex" } }
}
```

- `pokemon`, `region`, `location` sont au **premier niveau**.
- `timestamp` est en **UTC**, séparé par une espace et avec microsecondes (pas un
  `T` ISO) — converti en heure locale.
- `originalJson.data` contient des **métadonnées Pokédex** (HMs, notes de lieu),
  pas la localisation de l'essaim. Le parseur donne donc la priorité aux champs
  de premier niveau : un objet imbriqué ne peut pas écraser la région ni le lieu.
- `published_by` : les données sont **remontées par des contributeurs humains**.
  La couverture et la réactivité dépendent d'eux, ce n'est pas automatisé.

Autres formes acceptées : JSON encapsulé (`{"data":{…}}`, déballé sans écraser le
premier niveau), texte reprenant l'annonce du jeu (motifs FR/EN), et tout autre
texte **relayé tel quel** plutôt qu'ignoré. Alias reconnus : `name`/`species`
(Pokémon), `area`/`route` (lieu), `timestampIso`/`time` (horodatage).

### Fiabilité — vérifiée

Contrôle effectué le 2026-08-13. Un essaim observé en jeu à **11:19 heure locale**
(`Un essaim de Munna a été repérée près de Route 4 !`) a été retrouvé dans
l'historique Alphapedia :

```
2026-08-13 08:20 UTC   Munna   Kanto   Route 4      =  11:20 heure locale
```

Bon Pokémon, bon lieu, bonne région, bonne minute.

Volume constaté sur la journée : **32 essaims**, répartis Unys 8, Johto 7,
Hoenn 6, Kanto 6, Sinnoh 5 — soit un toutes les ~45 min toutes régions
confondues, et un toutes les ~4 h pour une région donnée.

Latence mesurée : essaim horodaté à 12:51:30, message reçu via ntfy à
12:51:52 — **~21 s**. C'est du push, pas du sondage.

---

## Sous le capot

Tout est écrit avec la bibliothèque standard. `fetch_assets.py` construit les
ressources une fois pour toutes ; `swarm_widget.py` ne fait que lire et afficher.

### Noms et sprites

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
| `regions.json` — emprise des 467 lieux | décompilations `pret` + pokebip | 31 Ko |

### Les noms de lieux

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

### La rareté — et ses limites

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

**Propagation aux évolutions** : Alphapedia ne classe que les formes de base
(Racaillou T7, mais rien pour Gravalanch ni Grolem). Comme une lignée vaut le
même score, `fetch_assets.py` remonte les chaînes évolutives via PokeAPI et
propage le tier : 282 formes de base + 300 évolutions = **582 Pokémon couverts**
sur 649. Les 67 restants — surtout des légendaires, hors événement — n'affichent
aucun tier plutôt qu'une valeur inventée.

### Le rognage des sprites

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

### Le halo des alphas

Aucun jeu de sprites alpha n'est distribué publiquement : l'aura est un effet de
rendu du jeu, et Alphapedia affiche elle-même les sprites ordinaires.

`fetch_assets.py` décode chaque sprite, calcule par **propagation en largeur** la
distance de chaque pixel vide à la silhouette, puis peint un halo dont l'opacité
décroît de façon quadratique avec cette distance — avant de ré-encoder le PNG.
649 variantes, ~20 s, 2,7 Mo, aucune dépendance graphique.

Mesuré sur le résultat : **5 niveaux d'opacité** de 74 % à 2 %, soit un dégradé
et non un bord net, et un halo qui reste translucide.

### Les cartes de région

Trois régions sont **reconstituées** depuis les décompilations
[pret](https://github.com/pret) : le tileset et le tilemap de la carte du monde
sont téléchargés, assemblés, puis les emprises des lieux sont lues dans les
données de landmarks. Hoenn a demandé trois hypothèses fausses avant de trouver
que son tilemap est **planaire** et non des `u16` empaquetés.

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

## Ce que ce widget ne fait jamais

- toucher au process du jeu ou à sa mémoire,
- toucher au trafic réseau du jeu,
- envoyer des entrées clavier ou souris — **aucune automatisation de gameplay**.

**Pas d'anti-AFK, volontairement.** Bouger le curseur ou envoyer des touches
automatiquement tombe sous la clause des ToS visant « scripts, macros, bots,
autoclickers », et le client scanne la RAM à la recherche de programmes tiers.
Le flux Alphapedia supprime le besoin : le jeu n'a plus à tourner.

**Pourquoi pas l'interception réseau.** C'était la piste initiale, techniquement
faisable mais inadaptée :

- protocole **chiffré et compressé**, TLS maison comparant la clé publique signée
  du serveur à un **certificat codé en dur** → un proxy MITM impose de **patcher
  le binaire** ;
- les ToS indiquent que le client **scanne la RAM** et remonte au serveur le nom
  du compte et les détails du programme détecté. Le *client tampering* et
  l'injection JVM sont des motifs de ban documentés ;
- client obfusqué (`f.ej2`, `f.k12`…) : tout hook casse à chaque mise à jour.

---

## Limites connues

- **Windows uniquement.** L'icône système et l'ancrage au bureau passent par
  l'API Win32 via `ctypes`. Le reste est portable.
- **Dépendance à des contributeurs humains.** Alphapedia est alimentée par des
  joueurs : un essaim non signalé n'apparaîtra pas.
- **Durées estimées sur le flux public.** Sans topic personnel, les décomptes
  reposent sur 25 min / 75 min plutôt que sur la date d'expiration réelle.
- **Cartes annotées partielles** : 49 lieux, dont 6 en JPEG que Tk ne lit pas.
- **Sinnoh reste le repérage le moins précis** : faute de carte extractible, ses
  emprises passent par une transformation affine (94 % de recouvrement), là où
  les autres régions viennent directement des données de jeu.
- **PWT, Pokéwood et la Réserve Naturelle** n'ont pas de repère sur Unys : ce
  sont des installations sans spawn sauvage.

---

## Contribuer

Les contributions sont les bienvenues — voir [CONTRIBUTING.md](CONTRIBUTING.md)
pour la mise en place, le style et ce qui aiderait le plus.

En deux lignes : aucune dépendance tierce, aucune automatisation de jeu, rien
n'est journalisé. Le reste est ouvert à la discussion.

*Contributions welcome. The code and its comments are in French, but issues and
pull requests in English are perfectly fine.*

---

## Licence

[MIT](LICENSE) pour le code source.

La licence ne couvre **pas** les ressources de jeu que le projet télécharge à
l'exécution (sprites, cartes) ni les données lues chez des tiers.

---

## Crédits et mentions légales

| | |
|---|---|
| [Alphapedia](https://alpha.pokemmotools.org/) | source des essaims, alphas, raretés et traductions — par FlaProGmr & Lorddusk |
| [ntfy](https://ntfy.sh/) | transport push, et son [API de souscription](https://docs.ntfy.sh/subscribe/api/) |
| [PokeAPI](https://pokeapi.co/) / [PokeAPI/sprites](https://github.com/PokeAPI/sprites) | sprites et chaînes évolutives |
| [pret](https://github.com/pret) | décompilations `pokeemerald`, `pokefirered`, `pokecrystal`, `pokeplatinum` |
| [pokebip](https://www.pokebip.com/) | guide des lieux Noir/Blanc et Noir/Blanc 2 |
| [fanzeyi/pokemon.json](https://github.com/fanzeyi/pokemon.json) | numéros du Pokédex |
| [PokeMMO ShoutWiki](https://pokemmo.shoutwiki.com/) | durées des essaims, Shiny Wars |

Les scripts respectent les sites qu'ils interrogent : cache disque systématique,
pause entre les requêtes, et aucune ressource re-téléchargée sans `--force`.

> **PokeMMO Swarm Widget est un projet de fan non officiel**, sans aucun lien avec
> Nintendo, Creatures Inc., GAME FREAK Inc. ni l'équipe PokeMMO. Pokémon et les
> noms, sprites et cartes associés restent la propriété de leurs détenteurs
> respectifs. Aucune ressource de jeu n'est redistribuée par ce dépôt : elles
> sont téléchargées à l'exécution depuis leurs sources d'origine.
>
> Cet outil lit des annonces publiques et n'interagit jamais avec le client
> PokeMMO. Il reste de ta responsabilité de vérifier qu'il est compatible avec
> les conditions d'utilisation en vigueur.
