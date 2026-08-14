#!/usr/bin/env bash
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
# Installe MultiWall pour l'utilisateur courant : commande `multiwall` dans le
# PATH, entrée dans le menu d'applications, et (optionnel) réapplication au login.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
AUTOSTART_DIR="$HOME/.config/autostart"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

mkdir -p "$BIN_DIR" "$APP_DIR" "$ICON_DIR"

# Icône nommée d'après l'app-id : le dock et le menu la retrouvent seuls.
install -m 644 "$HERE/multiwall/data/logo.svg" "$ICON_DIR/org.sigilbo.MultiWall.svg"
command -v gtk-update-icon-cache >/dev/null \
    && gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
echo "✓ Icône : $ICON_DIR/org.sigilbo.MultiWall.svg"

ln -sf "$HERE/bin/multiwall" "$BIN_DIR/multiwall"
echo "✓ Commande : $BIN_DIR/multiwall"

# Le fichier est nommé d'après l'app-id GTK : le shell associe alors la
# fenêtre à son lanceur sans passer par l'heuristique WM_CLASS.
DESKTOP="$APP_DIR/org.sigilbo.MultiWall.desktop"
# awk plutôt que sed : un chemin contenant « | » ou « & » casserait le s|…|…|
awk -v ligne="Exec=$HERE/bin/multiwall gui" \
    '/^Exec=/ { print ligne; next } { print }' \
    "$HERE/multiwall.desktop" > "$DESKTOP"
rm -f "$APP_DIR/multiwall.desktop"   # ancien nom : évite un doublon dans le menu
echo "✓ Menu d'applications : $DESKTOP"

if [[ "${1:-}" == "--autostart" ]]; then
    mkdir -p "$AUTOSTART_DIR"
    cat > "$AUTOSTART_DIR/multiwall-apply.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=MultiWall (réapplication)
Comment=Réapplique le fond d'écran multi-moniteurs à l'ouverture de session
Exec=$HERE/bin/multiwall apply
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
EOF
    echo "✓ Autostart : $AUTOSTART_DIR/multiwall-apply.desktop"
fi

command -v update-desktop-database >/dev/null && update-desktop-database "$APP_DIR" || true

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "⚠ $BIN_DIR n'est pas dans le PATH — ajoutez-le à votre ~/.bashrc" ;;
esac

echo "Terminé. Lancez : multiwall"
echo "Pour désinstaller : $HERE/uninstall.sh"
