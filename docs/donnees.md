# Les flux de données

## Les deux flux

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

## Configurer son propre topic ntfy

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

## Essaims et alphas

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

## Durée d'un essaim

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

## Format réel d'Alphapedia — vérifié

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

## Fiabilité — vérifiée

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

---

[← Retour au README](../README.md)
