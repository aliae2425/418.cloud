# Image sans dépendance : `service.py` n'emploie que la bibliothèque
# standard, donc rien à installer, rien à mettre à jour, rien à auditer.
FROM python:3.13-slim

# Pas de root. Si quelqu'un trouve un trou dans trente lignes de http.server,
# autant qu'il ne tombe pas sur un conteneur privilégié.
RUN useradd --system --no-create-home --uid 10418 cloud

WORKDIR /app
COPY service.py api.json ./
RUN chown -R cloud:cloud /app
USER cloud

ENV PORT=8418 \
    CATALOGUE=/app/api.json \
    ORIGINE=* \
    DUREE=900 \
    PYTHONUNBUFFERED=1

EXPOSE 8418

# `/sante` relit le catalogue : un fichier remplacé par du JSON cassé fait
# tomber le conteneur au lieu de servir une liste vide en silence.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/sante',timeout=2)"

CMD ["python", "service.py"]
