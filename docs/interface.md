# L'interface en détail

## La pastille d'état

| Pastille | Sens |
|---|---|
| 🟢 vert **clignotant** | au moins un essaim en cours |
| 🔵 bleu fixe | connecté, aucun essaim |
| 🟠 orange | connexion en cours |
| 🔴 rouge | déconnecté (reconnexion automatique) |

Elle agrège les flux : elle ne passe au rouge que si **tous** sont tombés.

## Le cri du Pokémon

Un haut-parleur suit le titre **ESSAIMS** : 🔇 quand le son est coupé, 🔊 sinon.
Un clic bascule, tout comme l'entrée correspondante du menu de l'icône système.

- **Muet au lancement**, toujours. Un widget qui se met à crier tout seul au
  démarrage de la session serait une mauvaise surprise, et le cache rejoué au
  démarrage produirait une douzaine de cris d'affilée.
- **Un cri par événement**, et un seul : le même essaim arrive souvent par les
  deux flux. La signature retenue — région, type, espèce, lieu — ignore
  volontairement l'horodatage, qui diffère d'un flux à l'autre pour un événement
  identique. Elle est oubliée à l'expiration, si bien qu'un essaim qui
  réapparaît plus tard sonne de nouveau.
- **Une file d'attente**, pas de superposition. Deux essaims coup sur coup se
  suivent : la lecture est bloquante dans son propre fil, le suivant part quand
  le précédent est fini. La file est bornée à six — en cas d'avalanche, mieux
  vaut abandonner les surnuméraires que sonner une minute après l'événement.
- **Le volume est retenu**, pas le silence : le widget redémarre muet mais
  retrouve le niveau choisi quand on le rétablit.

## La fiche Pokédex

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

## La carte de la région

Un clic sur le **nom du lieu** ouvre la carte officielle de la région, dans un
panneau de la largeur du widget, avec l'emprise du lieu encadrée. Les régions à
couches (îles Sevii pour Kanto) n'affichent que la couche contenant le lieu.

| Geste | Effet |
|---|---|
| Clic sur le **nom du lieu** | ouvre la carte ; **un second clic la referme** |
| Clic sur le **repère** | bascule sur la carte annotée de la communauté, avec **←** pour revenir |
| **Double-clic** sur la carte | agrandit, ou revient à la taille normale selon l'état courant |
| Clic ailleurs sur la carte | **rien** |
| **✕** ou `Échap` | ferme |

> Cliquer la carte la refermait, ce qui la faisait disparaître au moindre geste —
> y compris en visant le repère. Seule la croix ferme désormais, et le
> double-clic reprend le rôle du bouton d'agrandissement pour qu'on puisse
> zoomer sans viser l'en-tête. L'agrandissement n'est pas mémorisé : chaque
> réouverture repart de la taille normale.

| Région | Lieux repérés | Source des coordonnées |
|---|---|---|
| Sinnoh | 126 | `pokeplatinum` + calage affine |
| Johto | 107 | `pokecrystal` |
| Unys | 86 | guides pokebip Noir/Blanc et Noir/Blanc 2 |
| Kanto | 85 | `pokefirered`, 3 couches Sevii |
| Hoenn | 82 | `pokeemerald` |

**Les repères empruntés.** PokeMMO annonce parfois un lieu plus fin que la carte
du monde n'en décrit : le Jardin Trophée est le jardin du Manoir, l'Espace Guide
une salle au bout du Tunnel Bardane, le QG de la Team Rocket un sous-sol de
Acajou. D'autres n'existent pas sur la carte d'origine — Grotte Falaise et les
routes 47-48 viennent de HeartGold, que Cristal ignore. D'autres encore ne
diffèrent que par le nom : FireRed écrit `KANTO_SAFARI_ZONE`, Platine a rebaptisé
le Tunnel Runiement.

Faute de repère propre, ces lieux empruntent celui de leur parent : montrer le
bon quartier vaut mieux que ne rien montrer, et l'en-tête du panneau porte de
toute façon le nom exact annoncé. Table `PLACE_FALLBACKS` dans
`fetch_assets.py`.

**Le contrôle de couverture.** `fetch_assets.py` confronte les repères au
catalogue des spawns d'Alphapedia (`swarm-spawn-data` et `alpha-spawn-data`),
qui énumère exactement les **266 couples région/lieu** pouvant être annoncés, et
nomme ce qui manque. Couverture actuelle : **266/266**.

> Ce contrôle a d'abord été mesuré sur les seuls spots d'alphas — 196 lieux — ce
> qui affichait 100 % alors que cinq lieux d'essaims restaient sans repère. Un
> taux de couverture ne vaut que par son dénominateur. La résolution utilisée
> par le contrôle est par ailleurs confrontée à celle du widget sur les 266
> lieux : sans cela, il validerait une recherche que l'affichage ne fait pas.

## La carte annotée du lieu

Quand une carte annotée existe pour le lieu, une icône **🗺** apparaît à côté de
son nom dans la fiche. Un clic l'ouvre en grand — c'est la carte du jeu, avec le
spot marqué et les annotations de la communauté (*Mach Bike*, *Flash*,
itinéraires…). `Échap` ou la croix pour fermer — là aussi, cliquer l'image ne
fait rien.

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

## Ce qui change pour un alpha

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

## Halo et transparence

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

## Le menu de l'icône système

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
| Cri du Pokémon à chaque essaim | coupe ou rétablit le son (coche quand il est actif) |
| Son plus fort (+10 %) | monte le volume des cris |
| Son moins fort (−10 %) | le baisse |
| Volume par défaut | revient à `60 %`, affiche la valeur courante |
| Afficher / masquer | |
| Quitter | ferme le widget |

Taille, transparence **et volume** sont retenus pour les lancements suivants
(`.widget_state.json`).

Le menu règle l'opacité **au repos** ; celle au survol suit automatiquement si on
demande plus opaque qu'elle, pour qu'approcher la souris ne rende jamais le
widget *plus* transparent. Bornes : 15 % à 100 %.

---

---

[← Retour au README](../README.md)
