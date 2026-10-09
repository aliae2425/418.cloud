# -*- coding: utf-8 -*-
"""Fabrique `api.json` : un miroir filtré de models.dev, plus ce qu'il ignore.

Deux sources, et la seconde est la raison d'être du service :

1. **models.dev** (MIT) décrit ce qui *existe* chez les fournisseurs d'API.
   On en garde les modèles qu'on sert, avec les champs qu'on emploie.
2. **`maison.json`** décrit ce que models.dev ne connaît pas — au premier
   chef le backend Codex de l'abonnement ChatGPT, qui n'expose aucun
   catalogue et qu'aucun tiers ne documente.

Le résultat est à NOUS : on y met ce qu'on gère, on en retire ce qu'on ne
gère pas, et on ne dépend de personne pour ça.

    python generer.py            # écrit api.json
    python generer.py --verifier # dit ce qui changerait, n'écrit rien

Aucune dépendance : urllib et json, c'est tout.
"""
from __future__ import unicode_literals
import io
import json
import os
import sys
import time

try:
    from urllib.request import Request, urlopen
except ImportError:                        # Python 2
    from urllib2 import Request, urlopen

SOURCE = 'https://models.dev/api.json'

# models.dev rend 403 sur l'User-Agent par défaut d'urllib. On se nomme —
# c'est ce que fait opencode aussi, et c'est la moindre des politesses quand
# on tire chez quelqu'un.
AGENT = '418.cloud (+https://github.com/aliae2425)'
ICI = os.path.dirname(os.path.abspath(__file__))
MAISON = os.path.join(ICI, 'maison.json')
SORTIE = os.path.join(ICI, 'api.json')

VERSION = 1

# Les fournisseurs qu'on sert, et sous quelle forme on s'y connecte.
# Y figurer suffit à apparaître dans `/connect` ; en sortir suffit à
# disparaître. C'est tout le pouvoir qu'on voulait reprendre.
SERVIS = {
    'openai': {'nom': 'OpenAI', 'connexion': 'cle', 'limite': 12},
}

# Ce qui n'est pas un modèle de conversation. Le filtre est volontairement
# grossier : mieux vaut en laisser passer un de trop qu'en cacher un bon.
ECARTE = ('audio', 'realtime', 'transcribe', 'tts', 'image', 'embedding',
          'moderation', 'search', 'codex')


def tirer(url=SOURCE):
    requete = Request(url, headers={'User-Agent': AGENT})
    return json.loads(urlopen(requete, timeout=30).read().decode('utf-8'))


def convertir(brut):
    """Une entrée models.dev → la nôtre. Seulement ce qu'on emploie."""
    cout = brut.get('cost') or {}
    limite = brut.get('limit') or {}
    entrees = (brut.get('modalities') or {}).get('input') or []
    return {
        'nom': brut.get('name') or brut['id'],
        # `outils` décide si le modèle peut appeler `lib/rvt`. Un modèle sans
        # outils, dans ce volet, ne sert à rien : on ne le propose pas.
        'outils': bool(brut.get('tool_call')),
        'pieces': 'pdf' in entrees or 'image' in entrees,
        'raisonnement': bool(brut.get('reasoning')),
        'limite': {'contexte': limite.get('context'),
                   'sortie': limite.get('output')},
        'cout': {'entree': cout.get('input'), 'sortie': cout.get('output'),
                 'cache': cout.get('cache_read')},
        'sorti': brut.get('release_date') or '',
    }


def depuis_models_dev(amont):
    fournisseurs = {}
    for identifiant, reglage in SERVIS.items():
        source = amont.get(identifiant)
        if source is None:
            print('  ! {0} absent de models.dev, ignoré'.format(identifiant))
            continue
        lus = [m for cle, m in (source.get('models') or {}).items()
               if m.get('tool_call') and m.get('status') != 'deprecated'
               and not any(x in cle for x in ECARTE)]
        lus.sort(key=lambda m: m.get('release_date') or '', reverse=True)
        fournisseurs[identifiant] = {
            'nom': reglage['nom'],
            'connexion': reglage['connexion'],
            'env': list(source.get('env') or []),
            'doc': source.get('doc') or '',
            'modeles': dict((m['id'], convertir(m))
                            for m in lus[:reglage['limite']]),
        }
    return fournisseurs


def maison():
    """Ce que models.dev ne décrit pas. Tenu à la main, et assumé."""
    if not os.path.exists(MAISON):
        return {}
    with io.open(MAISON, encoding='utf-8') as ouvert:
        return json.loads(ouvert.read())


def fabriquer():
    print('tirage de', SOURCE)
    fournisseurs = depuis_models_dev(tirer())
    ajouts = maison()
    for identifiant, entree in ajouts.items():
        if identifiant in fournisseurs:
            # Un fournisseur décrit des deux côtés : la main l'emporte. C'est
            # la porte de sortie quand l'amont se trompe ou tarde.
            fournisseurs[identifiant]['modeles'].update(entree.get('modeles') or {})
            print('  + {0} : {1} modèles ajoutés à la main'.format(
                identifiant, len(entree.get('modeles') or {})))
        else:
            fournisseurs[identifiant] = entree
            print('  + {0} : fournisseur entièrement à la main'.format(identifiant))
    return {
        'version': VERSION,
        # Daté pour que le client sache ce qu'il a, et qu'un instantané
        # oublié se repère d'un coup d'œil.
        'genere': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'source': SOURCE,
        'fournisseurs': fournisseurs,
    }


def ecrire(charge, chemin=SORTIE):
    # ensure_ascii=False : les noms de modèles portent des accents, et un
    # JSON échappé est illisible en revue.
    brut = json.dumps(charge, ensure_ascii=False, indent=2, sort_keys=True)
    with io.open(chemin, 'w', encoding='utf-8') as ouvert:
        ouvert.write(brut + '\n')
    return len(brut.encode('utf-8'))


def main():
    charge = fabriquer()
    compte = sum(len(f['modeles']) for f in charge['fournisseurs'].values())
    if '--verifier' in sys.argv:
        print('{0} fournisseurs, {1} modèles — rien écrit'.format(
            len(charge['fournisseurs']), compte))
        return 0
    taille = ecrire(charge)
    print('api.json : {0} fournisseurs, {1} modèles, {2:.1f} ko'.format(
        len(charge['fournisseurs']), compte, taille / 1024.0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
