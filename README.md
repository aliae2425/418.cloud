# 418.cloud

Le catalogue des fournisseurs et des modèles que **418.extension** sait
employer. Un fichier JSON, servi par trente lignes de Python, dans un
conteneur.

## Pourquoi pas models.dev directement

models.dev décrit ce qui **existe** chez les fournisseurs d'API. Deux choses
lui manquent, et ce sont exactement celles qui nous intéressent :

- **l'abonnement ChatGPT.** Son backend Codex n'expose aucun catalogue — ni
  route, ni config, ni cache — et models.dev ne le décrit pas non plus : il
  décrit l'API facturée au jeton. Sans cette liste tenue à la main, `/model`
  sur l'abonnement n'a rien à proposer.
- **ce qu'on gère.** Un fournisseur présent chez eux et absent ici ne doit
  pas apparaître dans `/connect` : on n'a rien écrit pour le brancher.

D'où un catalogue à nous, qui **hérite** de models.dev pour ce qu'il sait et
le **complète** pour le reste. Le résultat est sous notre contrôle : on y met
ce qu'on gère, on en retire ce qu'on ne gère pas.

---

## Ce qu'il y a

| | |
|---|---|
| `generer.py` | fabrique `api.json` — miroir filtré de models.dev + `maison.json` |
| `maison.json` | ce que models.dev ignore. Tenu à la main, et assumé |
| `api.json` | le résultat. **Généré — ne pas l'éditer**, il serait écrasé |
| `service.py` | le sert, avec CORS, ETag et `/sante` |
| `Dockerfile` · `compose.yaml` | l'emballage |

Aucune dépendance nulle part : `urllib`, `json`, `http.server`. Rien à
installer, rien à auditer, rien qui se périme.

## Mettre à jour le catalogue

```bash
python generer.py --verifier   # dit ce qui changerait, n'écrit rien
python generer.py              # écrit api.json
git diff api.json              # relire AVANT de pousser
```

Ajouter un fournisseur : une entrée dans `SERVIS` (`generer.py`) s'il est
chez models.dev, dans `maison.json` sinon. En retirer un : l'enlever. Il
disparaît de `/connect` au prochain chargement.

**Rien ne signale qu'un modèle a disparu chez le fournisseur.** Un nom refusé
revient en clair dans l'erreur de l'API, et c'est le seul signal qu'on aura.
Relancer `generer.py` de temps en temps est la seule hygiène.

## Déployer

Derrière **Traefik**, qui termine le TLS et route sur le nom.

```bash
cp .env.exemple .env      # remplir DOMAINE, RESEAU, CERTRESOLVER
docker compose config     # relire ce que l'interpolation a donné
docker compose up -d --build
curl -s https://$DOMAINE/api.json | head
```

**Aucun port n'est publié sur l'hôte.** Traefik joint le conteneur par le
réseau partagé ; publier un port ouvrirait une seconde porte, en clair, qui
contournerait le TLS et les middlewares.

Le réseau est déclaré `external` : s'il manque, `up` échoue tout de suite
plutôt que de monter un conteneur que rien ne joindra. `docker network ls`
dira son nom — `traefik` chez beaucoup, `proxy` chez d'autres.

Un seul middleware, et il se mesure : **7 184 octets → 1 054 en gzip, 85 %
en moins**. Chaque Revit qui démarre tire ce fichier.

| variable | défaut | où |
|---|---|---|
| `DOMAINE` | — | `.env`, le nom routé par Traefik |
| `RESEAU` | `traefik` | `.env`, le réseau que Traefik écoute |
| `CERTRESOLVER` | `letsencrypt` | `.env`, le résolveur déclaré chez Traefik |
| `PORT` | `8418` | image — dans le conteneur, pas sur l'hôte |
| `CATALOGUE` | `/app/api.json` | image — chemin du fichier servi |
| `ORIGINE` | `*` | compose — `Access-Control-Allow-Origin` |
| `DUREE` | `900` | compose — `max-age`, en secondes |

`api.json` est **monté**, pas cuit dans l'image : le remplacer et recharger
ne demande ni build ni redémarrage. L'image en garde une copie, qui sert de
repli si le montage manque.

Pour l'essayer sans Traefik, en local :

```bash
python service.py          # écoute sur :8418
curl -s localhost:8418/api.json | head
```

## Les routes

```
GET /api.json   le catalogue      200 · 304 si l'ETag n'a pas bougé · 503 s'il est cassé
GET /sante      pour le healthcheck
```

`503` sur un catalogue illisible est délibéré : un service qui répond `200`
avec une liste vide est pire qu'un service qui dit franchement qu'il n'a
rien. Le `healthcheck` relit le fichier, donc un JSON cassé fait tomber le
conteneur au lieu de servir du vide en silence.

L'`ETag` est **exposé** par CORS (`Access-Control-Expose-Headers`). Sans ça
le navigateur le cache au script, et le `304` ne sert plus à rien.

---

## Le format

```jsonc
{
  "version": 1,
  "genere": "2026-10-09T13:06:26Z",
  "source": "https://models.dev/api.json",
  "fournisseurs": {
    "openai": {
      "nom": "OpenAI",
      "connexion": "cle",            // 'cle' | 'abonnement'
      "env": ["OPENAI_API_KEY"],
      "doc": "https://platform.openai.com/docs",
      "modeles": {
        "gpt-5.6": {
          "nom": "GPT-5.6",
          "outils": true,            // sans ça, inutile dans ce volet
          "pieces": true,            // images ou PDF en entrée
          "raisonnement": true,
          "limite": { "contexte": 1050000, "sortie": 128000 },
          "cout": { "entree": 4, "sortie": 20, "cache": 0.4 },
          "sorti": "2026-02-11",
          "defaut": true             // facultatif : le choisi par défaut
        }
      }
    }
  }
}
```

Les coûts sont en **dollars par million de jetons**, comme chez models.dev.
Sur l'abonnement ils valent zéro : le forfait est payé, afficher un prix au
jeton serait faux.

`version` existe pour que le client refuse un format qu'il ne sait pas lire
plutôt que d'en tirer n'importe quoi.

## Ce que ce service ne fait PAS

Il **sert**, il n'administre pas. Pas d'écriture, pas de compte, pas de base.
Le catalogue se change par un commit et un `docker compose restart`.

Le jour où il faudra éditer sans passer par git — des réglages par agence,
une interface — ce sera un autre sujet, avec du stockage et de
l'authentification. Pas avant que quelqu'un en ait besoin.
