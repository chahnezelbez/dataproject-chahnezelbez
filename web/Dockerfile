# CONTEXTE ÉTUDIANT : S3 | contexte de build ./web
# À PRÉPARER / ADAPTER : Ajouter vos nouveaux assets à COPY si vous en créez.
# CONTRÔLE ATTENDU : Vérifier les fichiers servis par l’image, pas seulement ceux présents sur le poste.
#
# Image Nginx prévue pour un processus non root ; le serveur écoute sur 8080.
# Le tag fourni est un point de départ : relever le digest pour la traçabilité.
FROM nginxinc/nginx-unprivileged:stable-alpine
# Configuration Compose/Kubernetes : api est un nom DNS interne.
COPY default.conf /etc/nginx/conf.d/default.conf
# Les fichiers sont embarqués, contrairement au bind mount du développement.
# TODO S2-S3 : compléter cette liste si vous ajoutez des fichiers au frontend.
COPY index.html app.js styles.css /usr/share/nginx/html/
# Port interne ; la publication est définie dans Compose ou via le Service.
EXPOSE 8080
