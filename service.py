# -*- coding: utf-8 -*-
"""Le service : sert le catalogue, et rien d'autre pour l'instant.

Une trentaine de lignes de bibliothèque standard plutôt qu'un cadre web. Ce
qu'il fait tient en trois phrases — lire un fichier, poser les bons en-têtes,
répondre. Y mettre FastAPI ou Flask ajouterait des dépendances, une image
plus lourde et une surface à tenir à jour, pour la même sortie.

Le jour où il faudra écrire ET lire — une interface d'administration, des
réglages par poste — ce sera le moment d'en discuter, pas avant.

    GET /api.json    le catalogue
    GET /sante       pour le `healthcheck` de Docker

Le catalogue est relu à CHAQUE requête : il fait sept kilo-octets, le
système de fichiers le garde en cache, et ça permet de le remplacer sans
redémarrer le conteneur.
"""
from __future__ import unicode_literals
import hashlib
import io
import json
import os
import sys

try:
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn
except ImportError:                        # Python 2
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
    from SocketServer import ThreadingMixIn

ICI = os.path.dirname(os.path.abspath(__file__))
CATALOGUE = os.environ.get('CATALOGUE') or os.path.join(ICI, 'api.json')
PORT = int(os.environ.get('PORT') or 8418)

# Le volet tourne sur une origine locale servie par WebView2 ; sans ce
# `Access-Control-Allow-Origin`, le navigateur refuse de lire la réponse.
# `*` parce que le catalogue est public : il ne dit rien qu'on cache.
ORIGINE = os.environ.get('ORIGINE') or '*'

# Un quart d'heure. Assez pour que dix Revit qui démarrent ensemble ne
# tapent qu'une fois, assez court pour qu'une correction se propage dans la
# demi-heure. Le client a de toute façon son propre cache et son repli.
DUREE = int(os.environ.get('DUREE') or 900)


def lire():
    """``(octets, empreinte)``. Lève si le fichier manque — c'est voulu :
    un service qui répond 200 avec un catalogue vide est pire qu'un service
    qui dit franchement qu'il n'a rien."""
    with io.open(CATALOGUE, 'rb') as ouvert:
        brut = ouvert.read()
    json.loads(brut.decode('utf-8'))       # refuse de servir du JSON cassé
    return brut, '"{0}"'.format(hashlib.sha256(brut).hexdigest()[:16])


class Service(BaseHTTPRequestHandler):

    server_version = '418.cloud'

    def do_GET(self):                                        # noqa: N802
        chemin = self.path.split('?')[0].rstrip('/') or '/'
        if chemin in ('/sante', '/health'):
            return self._rendre(b'{"ok":true}', '"sante"')
        if chemin in ('/', '/api.json'):
            try:
                brut, empreinte = lire()
            except Exception as e:
                return self._erreur(503, 'catalogue illisible : {0}'.format(e))
            # Le client renvoie l'empreinte qu'il a ; si elle n'a pas bougé,
            # 304 et zéro octet sur le fil.
            if self.headers.get('If-None-Match') == empreinte:
                return self._rendre(b'', empreinte, statut=304)
            return self._rendre(brut, empreinte)
        return self._erreur(404, 'inconnu')

    # Un moniteur ou un proxy sonde volontiers en HEAD. `_rendre` sait déjà
    # ne pas écrire le corps dans ce cas.
    do_HEAD = do_GET

    def do_OPTIONS(self):                                    # noqa: N802
        # Le préflight d'un navigateur. Sans lui, une page qui pose le
        # moindre en-tête se fait refuser avant d'avoir rien demandé.
        self.send_response(204)
        self._cors()
        self.send_header('Access-Control-Allow-Headers', 'if-none-match')
        self.send_header('Access-Control-Max-Age', '86400')
        self.end_headers()

    def _rendre(self, corps, empreinte, statut=200):
        self.send_response(statut)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('ETag', empreinte)
        self.send_header('Cache-Control', 'public, max-age={0}'.format(DUREE))
        self.send_header('Content-Length', str(len(corps)))
        self.end_headers()
        if corps and self.command != 'HEAD':
            self.wfile.write(corps)

    def _erreur(self, statut, message):
        corps = json.dumps({'erreur': message}).encode('utf-8')
        self.send_response(statut)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', ORIGINE)
        # L'empreinte doit être LISIBLE par la page, sinon le 304 ne sert à
        # rien : sans cette ligne, le navigateur la cache au script.
        self.send_header('Access-Control-Expose-Headers', 'etag')

    def log_message(self, forme, *args):
        # Une ligne par requête sur la sortie standard : c'est ce que Docker
        # ramasse, et c'est tout ce dont on a besoin.
        sys.stdout.write('%s %s\n' % (self.address_string(), forme % args))
        sys.stdout.flush()


class Fils(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    try:
        brut, _ = lire()
    except Exception as e:
        sys.stderr.write('catalogue introuvable ou cassé : {0}\n'.format(e))
        return 1
    sys.stdout.write('418.cloud sur :{0} — catalogue {1} ({2} octets)\n'.format(
        PORT, CATALOGUE, len(brut)))
    sys.stdout.flush()
    Fils(('0.0.0.0', PORT), Service).serve_forever()
    return 0


if __name__ == '__main__':
    sys.exit(main())
