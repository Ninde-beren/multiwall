#!/usr/bin/env bash
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
#
# Construit le paquet Debian de MultiWall.
#
# Paquet « natif » assemblé avec dpkg-deb : l'application est du Python pur, il
# n'y a rien à compiler, et debhelper n'apporterait ici qu'une couche de plus.
# Le résultat s'installe avec `apt install ./multiwall_<version>_all.deb`.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

VERSION="$(python3 -c 'import sys; sys.path.insert(0, "."); import multiwall; print(multiwall.__version__)')"
PAQUET="multiwall_${VERSION}_all"
BUILD="$HERE/build/$PAQUET"

rm -rf "$HERE/build"
mkdir -p "$BUILD"/{DEBIAN,usr/bin}
mkdir -p "$BUILD/usr/lib/python3/dist-packages/multiwall/data"
mkdir -p "$BUILD/usr/share/applications"
mkdir -p "$BUILD/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$BUILD/usr/share/doc/multiwall"

# --- Code ------------------------------------------------------------------
install -m 644 multiwall/*.py       "$BUILD/usr/lib/python3/dist-packages/multiwall/"
install -m 644 multiwall/data/*.svg "$BUILD/usr/lib/python3/dist-packages/multiwall/data/"

# Lanceur : le paquet est dans dist-packages, donc importable tel quel.
cat > "$BUILD/usr/bin/multiwall" <<'LANCEUR'
#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Lanceur de MultiWall."""
import sys

from multiwall.cli import main

sys.exit(main())
LANCEUR
chmod 755 "$BUILD/usr/bin/multiwall"

# --- Intégration au bureau -------------------------------------------------
install -m 644 multiwall.desktop \
    "$BUILD/usr/share/applications/org.sigilbo.MultiWall.desktop"
install -m 644 multiwall/data/logo.svg \
    "$BUILD/usr/share/icons/hicolor/scalable/apps/org.sigilbo.MultiWall.svg"
install -m 644 README.md "$BUILD/usr/share/doc/multiwall/"

# Le format `copyright` de Debian, avec la licence complète.
{
    echo "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/"
    echo "Upstream-Name: MultiWall"
    echo "Source: https://github.com/Ninde-beren/multiwall"
    echo
    echo "Files: *"
    echo "Copyright: 2026 Sigilbo"
    echo "License: PolyForm-Noncommercial-1.0.0"
    sed 's/^$/./; s/^/ /' LICENSE
} > "$BUILD/usr/share/doc/multiwall/copyright"
chmod 644 "$BUILD/usr/share/doc/multiwall/copyright"

# --- Changelog et page de manuel ------------------------------------------
mkdir -p "$BUILD/usr/share/man/man1"
: "${DATE_DEB:=$(date -R)}"
cat > "$HERE/build/changelog" <<CHANGELOG
multiwall ($VERSION) stable; urgency=low

  * Première version publiée.
  * Un fond d'écran par moniteur, ou une image panoramique étalée.
  * Bibliothèque : fonds générés, photos Wikimedia Commons, historique.
  * Détection à chaud des écrans, diagnostic d'environnement.

 -- Sigilbo <Ninde-beren@users.noreply.github.com>  $DATE_DEB
CHANGELOG
gzip -9n -c "$HERE/build/changelog" > "$BUILD/usr/share/doc/multiwall/changelog.gz"
chmod 644 "$BUILD/usr/share/doc/multiwall/changelog.gz"

cat > "$HERE/build/multiwall.1" <<'MANPAGE'
.TH MULTIWALL 1 "2026" "MultiWall" "Manuel de l'utilisateur"
.SH NOM
multiwall \- un fond d'écran différent par moniteur
.SH SYNOPSIS
.B multiwall
[\fICOMMANDE\fR] [\fIOPTIONS\fR]
.SH DESCRIPTION
Pose un fond d'écran distinct sur chaque moniteur, ou étale une image
panoramique unique sur l'ensemble des écrans.
.PP
Sans argument, ouvre l'interface graphique.
.SH COMMANDES
.TP
.B list
Affiche les écrans détectés et les dimensions du bureau.
.TP
.B set \fIIMAGE\fR...
Assigne une image par écran, de gauche à droite. Accepte aussi la forme
\fBNOM=chemin\fR pour cibler une sortie précise.
.TP
.B span \fIIMAGE\fR
Étale une seule image sur tous les écrans.
.TP
.B library \fR[\fIFOND\fR]
Liste les fonds générés, ou applique celui dont l'identifiant est donné.
.TP
.B photos \fR[\fIRECHERCHE\fR] [\fB--use\fR \fIN\fR]
Cherche des photos panoramiques sur Wikimedia Commons et applique la N-ième.
.TP
.B random \fIDOSSIER\fR
Tire une image au sort dans un dossier.
.TP
.B apply
Réapplique la dernière configuration enregistrée.
.TP
.B export \fIFICHIER\fR
Enregistre l'image composée sans l'appliquer.
.TP
.B doctor \fR[\fB--gui\fR] [\fB--mire\fR]
Vérifie que l'environnement de bureau est supporté. Renvoie 0 si oui.
\fB--gui\fR affiche le résultat dans une fenêtre ; \fB--mire\fR applique une mire
de contrôle puis restaure le fond précédent.
.SH OPTIONS
.TP
.BI --fit " MODE"
cover, contain, blur, stretch, center ou tile.
.TP
.BI --background " COULEUR"
Couleur des zones vides, par exemple \fB#101010\fR.
.TP
.B --span
Avec \fBrandom\fR, tire une seule image étalée sur tous les écrans.
.TP
.BI --nombre " N"
Avec \fBphotos\fR, nombre de résultats à lister (12 par défaut).
.SH FICHIERS
.TP
.I ~/.config/multiwall/config.json
Configuration et historique des images.
.TP
.I ~/.local/share/multiwall/
Images composées et photos en cache.
.SH NOTES
Nécessite un bureau lisant \fBorg.gnome.desktop.background\fR : GNOME, Budgie,
Cinnamon, MATE, Unity ou Pantheon. Ne fonctionne pas sous KDE Plasma, XFCE ni
LXQt.
.SH AUTEUR
Sigilbo \- https://github.com/Ninde-beren/multiwall
MANPAGE
gzip -9n -c "$HERE/build/multiwall.1" > "$BUILD/usr/share/man/man1/multiwall.1.gz"
chmod 644 "$BUILD/usr/share/man/man1/multiwall.1.gz"

# --- Métadonnées -----------------------------------------------------------
TAILLE="$(du -ks "$BUILD" | cut -f1)"
cat > "$BUILD/DEBIAN/control" <<CONTROL
Package: multiwall
Version: $VERSION
Section: x11
Priority: optional
Architecture: all
Depends: python3 (>= 3.7), python3-gi, gir1.2-gtk-3.0 (>= 3.20), python3-pil (>= 6.0), libglib2.0-bin, gsettings-desktop-schemas
Recommends: x11-xserver-utils
Installed-Size: $TAILLE
Maintainer: Sigilbo <Ninde-beren@users.noreply.github.com>
Homepage: https://github.com/Ninde-beren/multiwall
Description: Un fond d'écran différent par moniteur
 MultiWall pose un fond d'écran distinct sur chaque moniteur, ou étale une
 image panoramique unique sur l'ensemble des écrans — ce que GNOME et ses
 dérivés ne savent pas faire nativement.
 .
 L'application compose une image unique aux dimensions du bureau virtuel puis
 l'installe en mode « étalé », ce qui la répartit pixel pour pixel sur tous les
 moniteurs, d'après la géométrie réelle des écrans.
 .
 Fonctionne sur GNOME, Budgie, Cinnamon, MATE, Unity et Pantheon. Ne fonctionne
 pas sur KDE Plasma, XFCE ni LXQt, qui gèrent leur fond d'écran autrement ;
 la commande « multiwall doctor » diagnostique l'environnement.
CONTROL

# Rafraîchit les caches du bureau après installation et suppression.
cat > "$BUILD/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    if command -v update-desktop-database >/dev/null; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null; then
        gtk-update-icon-cache -qf /usr/share/icons/hicolor || true
    fi
fi
exit 0
POSTINST

cat > "$BUILD/DEBIAN/postrm" <<'POSTRM'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v update-desktop-database >/dev/null; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null; then
        gtk-update-icon-cache -qf /usr/share/icons/hicolor || true
    fi
fi
exit 0
POSTRM
chmod 755 "$BUILD/DEBIAN/postinst" "$BUILD/DEBIAN/postrm"

# --- Construction ----------------------------------------------------------
find "$BUILD" -type d -exec chmod 755 {} +   # le umask de l'atelier donnerait 775
fakeroot dpkg-deb --build --root-owner-group "$BUILD" >/dev/null
DEB="$HERE/build/$PAQUET.deb"

echo "✓ Paquet : $DEB"
echo "  taille : $(du -h "$DEB" | cut -f1)"
echo
echo "Installer :   sudo apt install $DEB"
echo "Désinstaller : sudo apt remove multiwall"
