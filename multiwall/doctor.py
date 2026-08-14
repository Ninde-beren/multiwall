# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Diagnostic de l'environnement.

MultiWall dépend moins de la distribution que de l'environnement de bureau :
il pilote `org.gnome.desktop.background` en mode « étalé », ce que tous les
bureaux ne savent pas faire. Ce module répond à la question « est-ce que ça
marchera ici ? » sans rien modifier.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from . import core

#: Bureaux qui lisent org.gnome.desktop.background et honorent « spanned ».
BUREAUX_SUPPORTES = ("gnome", "budgie", "cinnamon", "mate", "unity", "pantheon")

#: Bureaux qui gèrent leur fond d'écran autrement : MultiWall n'aura pas de prise.
BUREAUX_INCOMPATIBLES = ("kde", "plasma", "xfce", "lxqt", "lxde", "sway", "i3", "hyprland")

PYTHON_MINIMAL = (3, 7)
GTK_MINIMAL = (3, 20)      # Gtk.ShortcutsWindow
PILLOW_RECOMMANDE = (6, 0)  # ImageOps.exif_transpose

OK, ATTENTION, ECHEC = "ok", "attention", "échec"


@dataclass
class Point:
    """Un élément vérifié, avec son verdict."""

    categorie: str
    libelle: str
    valeur: str
    etat: str = OK
    detail: str = ""


@dataclass
class Rapport:
    points: list = field(default_factory=list)

    def ajouter(self, *args, **kwargs) -> None:
        self.points.append(Point(*args, **kwargs))

    @property
    def echecs(self) -> list:
        return [p for p in self.points if p.etat == ECHEC]

    @property
    def avertissements(self) -> list:
        return [p for p in self.points if p.etat == ATTENTION]

    @property
    def utilisable(self) -> bool:
        return not self.echecs


def _version_gtk() -> tuple[str, tuple]:
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        return f"{Gtk.MAJOR_VERSION}.{Gtk.MINOR_VERSION}", (Gtk.MAJOR_VERSION, Gtk.MINOR_VERSION)
    except Exception as exc:
        return f"absent ({type(exc).__name__})", ()


def _version_pillow() -> tuple[str, tuple]:
    try:
        import PIL

        return PIL.__version__, tuple(int(n) for n in PIL.__version__.split(".")[:2])
    except Exception:
        return "absent", ()


def _schema_present(schema: str) -> bool:
    if not shutil.which("gsettings"):
        return False
    try:
        sortie = subprocess.run(["gsettings", "list-schemas"], capture_output=True,
                                text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return schema in sortie.split()


def analyser() -> Rapport:
    """Inspecte l'environnement et renvoie un rapport, sans rien modifier."""
    rapport = Rapport()

    # --- Bureau et session ------------------------------------------------
    bureau = os.environ.get("XDG_CURRENT_DESKTOP", "") or os.environ.get("DESKTOP_SESSION", "")
    bureau_bas = bureau.lower()
    if any(n in bureau_bas for n in BUREAUX_INCOMPATIBLES):
        rapport.ajouter("Environnement", "Bureau", bureau or "inconnu", ECHEC,
                        "Ce bureau gère son fond d'écran autrement que par "
                        "org.gnome.desktop.background.")
    elif any(n in bureau_bas for n in BUREAUX_SUPPORTES):
        rapport.ajouter("Environnement", "Bureau", bureau)
    else:
        rapport.ajouter("Environnement", "Bureau", bureau or "inconnu", ATTENTION,
                        "Bureau non reconnu : le mode « étalé » n'est pas garanti.")

    session = os.environ.get("XDG_SESSION_TYPE", "inconnu")
    if session == "x11":
        rapport.ajouter("Environnement", "Session", session)
    elif session == "wayland":
        rapport.ajouter("Environnement", "Session", session, ATTENTION,
                        "Sous Wayland, la détection passe par GDK et le mode "
                        "« étalé » dépend du compositeur. Non vérifié.")
    else:
        rapport.ajouter("Environnement", "Session", session, ATTENTION)

    # --- Versions ---------------------------------------------------------
    version_py = ".".join(str(n) for n in sys.version_info[:3])
    rapport.ajouter("Versions", "Python", version_py,
                    OK if sys.version_info[:2] >= PYTHON_MINIMAL else ECHEC,
                    "" if sys.version_info[:2] >= PYTHON_MINIMAL
                    else f"Python {'.'.join(map(str, PYTHON_MINIMAL))} minimum.")

    texte, tuple_gtk = _version_gtk()
    if not tuple_gtk:
        rapport.ajouter("Versions", "GTK 3", texte, ECHEC,
                        "Installez python3-gi et gir1.2-gtk-3.0.")
    else:
        suffisant = tuple_gtk >= GTK_MINIMAL
        rapport.ajouter("Versions", "GTK 3", texte, OK if suffisant else ECHEC,
                        "" if suffisant else "GTK 3.20 minimum.")

    texte, tuple_pil = _version_pillow()
    if not tuple_pil:
        rapport.ajouter("Versions", "Pillow", texte, ECHEC, "Installez python3-pil.")
    elif tuple_pil < PILLOW_RECOMMANDE:
        rapport.ajouter("Versions", "Pillow", texte, ATTENTION,
                        "Pillow 6.0 recommandé : sans lui, l'orientation EXIF des "
                        "photos est ignorée.")
    else:
        rapport.ajouter("Versions", "Pillow", texte)

    # --- Outils système ---------------------------------------------------
    chemin_gsettings = shutil.which("gsettings")
    rapport.ajouter("Outils", "gsettings", chemin_gsettings or "absent",
                    OK if chemin_gsettings else ECHEC,
                    "" if chemin_gsettings else "Installez libglib2.0-bin.")

    if _schema_present(core.SCHEMA):
        rapport.ajouter("Outils", "Schéma du bureau", core.SCHEMA)
        try:
            cles = subprocess.run(["gsettings", "list-keys", core.SCHEMA],
                                  capture_output=True, text=True, timeout=10).stdout.split()
        except (OSError, subprocess.SubprocessError):
            cles = []
        if "picture-uri-dark" in cles:
            rapport.ajouter("Outils", "Variante sombre", "picture-uri-dark")
        else:
            rapport.ajouter("Outils", "Variante sombre", "absente", ATTENTION,
                            "GNOME antérieur à 42 : seul le fond clair sera défini.")
    else:
        rapport.ajouter("Outils", "Schéma du bureau", "absent", ECHEC,
                        f"{core.SCHEMA} introuvable. Installez gsettings-desktop-schemas.")

    chemin_xrandr = shutil.which("xrandr")
    if chemin_xrandr:
        rapport.ajouter("Outils", "xrandr", chemin_xrandr)
    else:
        rapport.ajouter("Outils", "xrandr", "absent", ATTENTION,
                        "Détection des écrans par GDK (normal sous Wayland).")

    # --- Écrans -----------------------------------------------------------
    try:
        ecrans = core.detect_monitors()
    except Exception as exc:  # pragma: no cover - dépend du système
        ecrans = []
        rapport.ajouter("Écrans", "Détection", f"échec ({type(exc).__name__})", ECHEC)

    if ecrans:
        largeur, hauteur = core.desktop_size(ecrans)
        rapport.ajouter("Écrans", "Détectés", f"{len(ecrans)} · bureau {largeur}×{hauteur}")
        for ecran in ecrans:
            rapport.ajouter("Écrans", f"  {ecran.name}",
                            f"{ecran.width}×{ecran.height} à +{ecran.x}+{ecran.y}"
                            + (" (principal)" if ecran.primary else ""))
    elif not rapport.echecs:
        rapport.ajouter("Écrans", "Détectés", "aucun", ECHEC,
                        "Aucun écran détecté : MultiWall n'a rien à habiller.")

    return rapport


SYMBOLES = {OK: "✓", ATTENTION: "!", ECHEC: "✗"}


def formater(rapport: Rapport) -> str:
    """Rend le rapport lisible dans un terminal."""
    lignes = ["MultiWall — diagnostic de l'environnement", ""]
    categorie = None
    for point in rapport.points:
        if point.categorie != categorie:
            categorie = point.categorie
            lignes.append(categorie)
        lignes.append(f"  {SYMBOLES[point.etat]} {point.libelle:<22} {point.valeur}")
        if point.detail:
            lignes.append(f"      {point.detail}")
    lignes.append("")

    if rapport.echecs:
        lignes.append("Verdict : environnement NON supporté.")
        for point in rapport.echecs:
            lignes.append(f"  ✗ {point.libelle} — {point.detail or point.valeur}")
    elif rapport.avertissements:
        lignes.append("Verdict : devrait fonctionner, avec des réserves.")
        for point in rapport.avertissements:
            lignes.append(f"  ! {point.libelle} — {point.detail or point.valeur}")
        lignes.append("")
        lignes.append("Pour lever le doute : multiwall doctor --mire")
    else:
        lignes.append("Verdict : environnement pleinement supporté.")
    return "\n".join(lignes)


# --------------------------------------------------------------------------- #
# Mire de contrôle
# --------------------------------------------------------------------------- #

def _lire_fond_actuel() -> dict:
    """Sauvegarde l'état du fond d'écran, pour pouvoir le remettre."""
    etat = {}
    for cle in ("picture-uri", "picture-uri-dark", "picture-options", "primary-color"):
        try:
            sortie = subprocess.run(["gsettings", "get", core.SCHEMA, cle],
                                    capture_output=True, text=True, timeout=10)
            if sortie.returncode == 0:
                etat[cle] = sortie.stdout.strip().strip("'")
        except (OSError, subprocess.SubprocessError):
            continue
    return etat


def _restaurer_fond(etat: dict) -> None:
    for cle, valeur in etat.items():
        try:
            subprocess.run(["gsettings", "set", core.SCHEMA, cle, valeur],
                           capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            continue


def mire(monitors: list) -> "core.Image.Image":
    """Image de contrôle : une couleur et un cadre par écran.

    Si chaque moniteur affiche sa propre couleur avec un cadre qui épouse ses
    bords, alors le mode « étalé » fonctionne.
    """
    from PIL import Image, ImageDraw

    couleurs = [(200, 40, 40), (40, 160, 80), (50, 90, 220),
                (220, 160, 40), (150, 60, 180), (40, 170, 190)]
    image = Image.new("RGB", core.desktop_size(monitors), (0, 0, 0))
    dessin = ImageDraw.Draw(image)
    for rang, ecran in enumerate(monitors):
        couleur = couleurs[rang % len(couleurs)]
        dessin.rectangle(
            [ecran.x, ecran.y, ecran.x + ecran.width - 1, ecran.y + ecran.height - 1],
            fill=couleur,
        )
        marge = max(min(ecran.width, ecran.height) // 40, 4)
        dessin.rectangle(
            [ecran.x + marge, ecran.y + marge,
             ecran.x + ecran.width - 1 - marge, ecran.y + ecran.height - 1 - marge],
            outline=(255, 255, 255), width=max(marge // 3, 2),
        )
    return image


def poser_mire(monitors: list) -> dict:
    """Applique la mire et renvoie l'état précédent, à restaurer ensuite."""
    etat = _lire_fond_actuel()
    core.apply_wallpaper(mire(monitors))
    return etat


def restaurer(etat: dict) -> None:
    _restaurer_fond(etat)
