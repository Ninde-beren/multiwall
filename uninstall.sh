#!/usr/bin/env bash
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
#
# Retire l'installation faite par install.sh, pour l'utilisateur courant.
# Ne concerne pas le paquet Debian : celui-ci se retire par
#   sudo apt remove multiwall
set -euo pipefail

BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
AUTOSTART_DIR="$HOME/.config/autostart"
ICON_THEME="$HOME/.local/share/icons/hicolor"
ICON_DIR="$ICON_THEME/scalable/apps"

CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/multiwall"
DONNEES="${XDG_DATA_HOME:-$HOME/.local/share}/multiwall"

for f in "$BIN_DIR/multiwall" \
         "$APP_DIR/org.sigilbo.MultiWall.desktop" \
         "$APP_DIR/multiwall.desktop" \
         "$AUTOSTART_DIR/multiwall-apply.desktop" \
         "$ICON_DIR/org.sigilbo.MultiWall.svg"; do
    if [ -e "$f" ] || [ -L "$f" ]; then
        rm -f "$f"
        echo "✓ Retiré : $f"
    fi
done

command -v update-desktop-database >/dev/null \
    && update-desktop-database -q "$APP_DIR" 2>/dev/null || true

# L'option -t est indispensable : sans elle, gtk-update-icon-cache refuse de
# travailler faute d'index.theme et échoue SILENCIEUSEMENT, laissant dans le
# cache une entrée qui pointe vers l'icône supprimée. Le thème utilisateur
# primant sur /usr/share, plus aucune icône de l'application ne s'affiche
# ensuite — pas même celle du paquet Debian.
if [ -d "$ICON_THEME" ] && command -v gtk-update-icon-cache >/dev/null; then
    gtk-update-icon-cache -q -f -t "$ICON_THEME" 2>/dev/null || true
    echo "✓ Cache d'icônes rafraîchi"
fi

echo
echo "Conservés : votre configuration et vos fonds."
echo "  $CONFIG"
echo "  $DONNEES"
echo
echo "Pour tout effacer :  rm -rf '$CONFIG' '$DONNEES'"
echo "Votre fond d'écran actuel reste en place ; changez-en depuis les"
echo "paramètres du bureau si vous ne voulez pas le garder."
