# Contribuer à PokeMMO Swarm Widget

Les contributions sont les bienvenues — corrections, régions mieux couvertes,
traductions, ou simplement un retour d'usage. Le projet est petit et sans
dépendance : on peut y entrer en une soirée.

*Contributions welcome. The codebase and its comments are in French, but issues
and pull requests in English are perfectly fine.*

## Avant de coder

Ouvre une **issue** d'abord si le changement est structurant (nouvelle source de
données, refonte de l'affichage, dépendance ajoutée). Pour une correction ou un
petit ajout, va directement au pull request.

## Mettre en place

```powershell
git clone https://github.com/<toi>/pokemmo-swarm-widget.git
cd pokemmo-swarm-widget
python fetch_assets.py      # sprites et cartes : ~6 Mo, quelques minutes
pythonw swarm_widget.py
```

Aucun environnement virtuel n'est nécessaire, il n'y a rien à installer.

## Les règles du projet

Trois contraintes ont façonné le code et ne sont pas négociables :

1. **Aucune dépendance tierce.** Le décodage PNG, le halo des alphas et la mise
   à l'échelle sont écrits à la main plutôt que de tirer Pillow. Une PR qui
   ajoute une dépendance doit expliquer pourquoi la bibliothèque standard ne
   suffit pas.
2. **Aucune automatisation de jeu.** Pas d'anti-AFK, pas d'envoi de touches,
   pas de lecture mémoire, pas d'interception réseau, pas de modification du
   client. Voir *Ce que ce widget ne fait jamais* dans le README — c'est ce qui
   sépare cet outil d'un bot.
3. **Rien n'est journalisé.** L'état vit en mémoire. Seuls la position, l'échelle
   et la transparence sont écrits sur disque.

## Style

- **Commentaires en français**, comme le reste du code.
- Un commentaire explique **pourquoi**, pas quoi. Les commentaires existants
  documentent surtout des pièges (`PhotoImage` ne redimensionne que par des
  entiers, `winfo_id()` renvoie l'enfant et non la fenêtre…) : c'est le genre
  d'information qui mérite d'être écrite.
- Lignes à 88 colonnes environ, `snake_case`, pas de type hints imposés mais
  ils sont appréciés sur les signatures publiques.
- Pas de reformatage massif dans une PR fonctionnelle : ça noie le vrai
  changement.

## Tester

Il n'y a pas de suite de tests automatisés — l'essentiel du projet est de
l'affichage et du réseau. À vérifier à la main avant de proposer une PR :

```powershell
python -c "import ast;ast.parse(open('swarm_widget.py',encoding='utf-8').read())"
pythonw swarm_widget.py --demo             # scene fixe : 2 alphas, 3 essaims
pythonw swarm_widget.py                    # demarre, icone systeme presente
```

`--demo` évite d'attendre qu'un essaim tombe (un toutes les ~45 min) : il
remplit les cinq régions, ouvre la fiche Pokédex et la carte de région. C'est
aussi ce qui produit `docs/screenshot.png`.

Puis, selon ce que tu as touché :

| Zone modifiée | À vérifier |
|---|---|
| Flux ntfy | le widget se remplit au démarrage (cache rejoué), pastille bleue ou verte |
| Affichage | survol, clic sur le sprite, clic sur le lieu, agrandissement de carte |
| Cartes | le repère tombe au bon endroit dans les cinq régions |
| `fetch_assets.py` | `python fetch_assets.py --force` va au bout sans erreur |

Si tu touches aux ressources, précise dans la PR combien de sprites ou de lieux
sont couverts avant et après : c'est la mesure qui compte.

## Ce qui aiderait le plus

- **Compléter les cartes de région.** Sinnoh et Unys sont fournies à la main et
  ne se régénèrent pas ; trois repères de Sinnoh débordent de 3 px en bas.
- **Élargir les cartes annotées** : 49 lieux couverts sur plusieurs centaines.
- **Autres langues.** Les tables d'Alphapedia existent en `en`, `de`, `es`,
  `fr`, `it`, `pt`, `zh` ; seuls les libellés de l'interface sont encore
  uniquement en français.
- **Support Linux/macOS.** L'icône système et l'ancrage au bureau passent par
  l'API Win32 ; le reste est portable.

## Signaler un bug

Indique la version de Python, la version de Windows, la commande lancée, et ce
que tu attendais. Si le widget ne démarre pas, relance-le avec `python` au lieu
de `pythonw` : la console affichera l'erreur.
