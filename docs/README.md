# Documentation

Le [README](../README.md) suffit pour installer et se servir du widget. Ces
pages sont pour aller plus loin : comment l'interface se comporte, d'où viennent
les données, et comment les ressources sont fabriquées.

| Page | Contenu |
|---|---|
| [L'interface en détail](interface.md) | pastille d'état, fiche Pokédex, cartes de région et cartes annotées, ce qui change pour un alpha, halo et transparence, menu de l'icône système |
| [Les flux de données](donnees.md) | les deux flux ntfy, configurer son propre topic, essaims contre alphas, durée d'un essaim, format réel d'Alphapedia, fiabilité et latence mesurées |
| [Sous le capot](sous-le-capot.md) | noms, sprites, raretés et cartes : d'où ils viennent et comment ils sont construits ; rognage des sprites, halo des alphas, reconstitution des cartes de région, et pourquoi pas l'interception réseau |

Pour contribuer, voir [CONTRIBUTING.md](../CONTRIBUTING.md).

`screenshot.png` est la capture affichée en tête du README ; elle se régénère
avec `pythonw swarm_widget.py --demo`.
