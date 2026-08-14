# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Bibliothèque de fonds d'écran panoramiques générés à la volée.

Rien n'est stocké sur disque : une entrée est une *recette* (style, palette,
graine). L'image est calculée à la résolution exacte du bureau au moment où on
en a besoin — elle s'adapte donc à n'importe quelle configuration d'écrans, et
la bibliothèque ne pèse rien.

Les générateurs reçoivent des « ancres » : les abscisses des centres d'écran.
Les éléments focaux (un astre, un sommet principal) s'y posent, pour ne jamais
tomber sur la bordure physique entre deux moniteurs.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PIL import Image, ImageDraw

PALETTES: dict[str, list[tuple[int, int, int]]] = {
    "crepuscule": [(20, 24, 62), (72, 40, 110), (176, 66, 118), (247, 148, 92), (252, 211, 141)],
    "abysse":     [(6, 20, 38), (12, 52, 84), (22, 108, 138), (86, 186, 172), (198, 235, 214)],
    "foret":      [(14, 32, 28), (26, 66, 52), (58, 110, 68), (140, 168, 88), (226, 214, 150)],
    "nocturne":   [(10, 12, 30), (32, 30, 74), (70, 54, 128), (128, 88, 176), (206, 168, 224)],
    "braise":     [(24, 12, 20), (80, 22, 44), (152, 48, 52), (216, 104, 54), (246, 186, 104)],
}


# --------------------------------------------------------------------------- #
# Outils communs
# --------------------------------------------------------------------------- #

def _degrade_vertical(taille: tuple[int, int], couleurs: list) -> Image.Image:
    """Dégradé lisse : une colonne de quelques pixels agrandie en bicubique.

    Bien plus rapide que de calculer chaque ligne, et sans banding visible.
    """
    petite = Image.new("RGB", (1, len(couleurs)))
    for i, couleur in enumerate(couleurs):
        petite.putpixel((0, i), couleur)
    return petite.resize(taille, Image.BICUBIC)


def _melange(a, b, t: float):
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _crete(largeur: int, rng: random.Random, amplitude: float, base: float,
           octaves: int = 3) -> list:
    """Ligne de relief : somme de sinusoïdes déphasées."""
    ondes = [
        (rng.uniform(1.0, 2.5) * (2 ** o), rng.uniform(0, math.tau), amplitude / (1.6 ** o))
        for o in range(octaves)
    ]
    pas = max(largeur // 400, 1)
    points = []
    for x in range(0, largeur + pas, pas):
        u = x / largeur
        points.append((x, base + sum(a * math.sin(f * math.tau * u + p) for f, p, a in ondes)))
    return points


def _ancre(rng: random.Random, ancres: list[float] | None, largeur: int) -> float:
    """Choisit une abscisse focale, au centre d'un écran si on les connaît."""
    if ancres:
        return rng.choice(ancres)
    return largeur * rng.uniform(0.25, 0.75)


# --------------------------------------------------------------------------- #
# Styles
# --------------------------------------------------------------------------- #

def _mesh(taille, rng, palette, ancres):
    """Dégradé maillé : matrice de couleurs agrandie."""
    cols, rows = 6, 4
    petite = Image.new("RGB", (cols, rows))
    for y in range(rows):
        haut = palette[min(y, len(palette) - 1)]
        bas = palette[min(y + 1, len(palette) - 1)]
        for x in range(cols):
            petite.putpixel((x, y), _melange(haut, bas, rng.uniform(0, 0.85)))
    return petite.resize(taille, Image.BICUBIC)


def _montagnes(taille, rng, palette, ancres):
    """Reliefs en couches, avec astre posé au centre d'un écran."""
    largeur, hauteur = taille
    img = _degrade_vertical(taille, palette[:3])
    dessin = ImageDraw.Draw(img)

    rayon = hauteur * rng.uniform(0.12, 0.2)
    cx = _ancre(rng, ancres, largeur)
    cy = hauteur * rng.uniform(0.3, 0.48)
    dessin.ellipse([cx - rayon, cy - rayon, cx + rayon, cy + rayon], fill=palette[4])

    couches = 4
    for i in range(couches):
        base = hauteur * (0.5 + 0.16 * i)
        points = _crete(largeur, rng, hauteur * 0.18 / (i + 1), base)
        dessin.polygon(
            [(0, hauteur)] + points + [(largeur, hauteur)],
            fill=_melange(palette[1], palette[0], (i + 1) / couches),
        )
    return img


def _vagues(taille, rng, palette, ancres):
    """Bandes fluides empilées."""
    largeur, hauteur = taille
    img = _degrade_vertical(taille, [palette[0], palette[1]])
    dessin = ImageDraw.Draw(img)
    bandes = 7
    for i in range(bandes):
        base = hauteur * (0.25 + 0.11 * i)
        points = _crete(largeur, rng, hauteur * 0.09, base, octaves=2)
        dessin.polygon(
            [(0, hauteur)] + points + [(largeur, hauteur)],
            fill=_melange(palette[3], palette[1], i / (bandes - 1)),
        )
    return img


def _lowpoly(taille, rng, palette, ancres):
    """Triangulation régulière perturbée."""
    largeur, hauteur = taille
    cols, rows = 26, 6
    fond = _degrade_vertical((cols + 1, rows + 1), palette).load()

    grille = []
    for j in range(rows + 1):
        ligne = []
        for i in range(cols + 1):
            # Les points de bord restent alignés : pas de dent de scie sur les côtés.
            dx = 0 if i in (0, cols) else rng.uniform(-0.42, 0.42)
            dy = 0 if j in (0, rows) else rng.uniform(-0.42, 0.42)
            ligne.append(((i + dx) * largeur / cols, (j + dy) * hauteur / rows))
        grille.append(ligne)

    img = Image.new("RGB", taille)
    dessin = ImageDraw.Draw(img)
    for j in range(rows):
        for i in range(cols):
            a, b = grille[j][i], grille[j][i + 1]
            c, e = grille[j + 1][i + 1], grille[j + 1][i]
            base = fond[i, j]
            for triangle in ((a, b, c), (a, c, e)):
                variation = rng.uniform(-0.12, 0.12)
                dessin.polygon(
                    triangle,
                    fill=tuple(max(0, min(255, round(v * (1 + variation)))) for v in base),
                )
    return img


STYLES = {
    "mesh": _mesh,
    "montagnes": _montagnes,
    "vagues": _vagues,
    "lowpoly": _lowpoly,
}


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Fond:
    """Une entrée de la bibliothèque : de quoi recalculer l'image à l'identique."""

    id: str
    nom: str
    style: str
    palette: str
    graine: int

    def rendu(self, taille: tuple[int, int], ancres: list[float] | None = None) -> Image.Image:
        largeur, hauteur = max(taille[0], 1), max(taille[1], 1)
        return STYLES[self.style](
            (largeur, hauteur), random.Random(self.graine), PALETTES[self.palette], ancres
        )


CATALOGUE: tuple[Fond, ...] = (
    Fond("crepuscule",  "Crépuscule",     "mesh",      "crepuscule", 7301),
    Fond("aube-froide", "Aube froide",    "mesh",      "abysse",     4127),
    Fond("braise",      "Braise",         "mesh",      "braise",     9042),
    Fond("nuit-claire", "Nuit claire",    "montagnes", "nocturne",   1583),
    Fond("massif",      "Massif bleu",    "montagnes", "abysse",     6620),
    Fond("canopee",     "Canopée",        "montagnes", "foret",      3390),
    Fond("vallees",     "Vallées",        "vagues",    "foret",      8814),
    Fond("dunes",       "Dunes",          "vagues",    "braise",     2205),
    Fond("cristaux",    "Cristaux",       "lowpoly",   "nocturne",   5476),
    Fond("recif",       "Récif",          "lowpoly",   "abysse",     1069),
)

_PAR_ID = {fond.id: fond for fond in CATALOGUE}


def get(identifiant: str) -> Fond:
    """Retrouve une entrée par son identifiant."""
    try:
        return _PAR_ID[identifiant]
    except KeyError:
        connus = ", ".join(_PAR_ID)
        raise ValueError(f"Fond inconnu : {identifiant} (disponibles : {connus})") from None


def existe(identifiant: str) -> bool:
    return identifiant in _PAR_ID


def ancres_ecrans(monitors, largeur_cible: int | None = None) -> list[float]:
    """Abscisses des centres d'écran, pour n'y poser que des éléments entiers.

    `largeur_cible` met les ancres à l'échelle : une vignette d'aperçu doit
    placer ses éléments aux mêmes endroits relatifs que le rendu final.
    """
    if not monitors:
        return []
    largeur_bureau = max(m.x + m.width for m in monitors)
    echelle = (largeur_cible / largeur_bureau) if largeur_cible and largeur_bureau else 1.0
    return [(m.x + m.width / 2) * echelle for m in monitors]


def rendu(identifiant: str, taille: tuple[int, int], monitors=None) -> Image.Image:
    return get(identifiant).rendu(taille, ancres_ecrans(monitors, taille[0]))
