@echo off
REM PokeMMO Swarm Widget — widget de bureau des essaims et alphas PokeMMO.
REM
REM Sans argument, le widget suit le serveur ntfy public d'Alphapedia : alphas et
REM essaims des cinq regions, aucun compte a creer. La duree y est estimee, faute
REM de date d'expiration dans ce flux.
REM
REM Pour des decomptes exacts, ajoute ton propre topic ntfy :
REM     start_widget.cmd --topic mon-topic-prive
REM
REM pythonw = pas de fenetre console. Ferme-le depuis l'icone de la zone de
REM notification.
cd /d "%~dp0"
start "" pythonw swarm_widget.py %*
