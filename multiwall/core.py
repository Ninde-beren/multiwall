# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Cœur de MultiWall : détection des moniteurs, composition et application du fond d'écran.

Principe : sous X11 (Budgie/GNOME), le bureau est une seule surface virtuelle
(ici 5760x1080). On compose donc UNE image aux dimensions du bureau entier, puis
on l'applique avec `picture-options = spanned`, ce qui l'étale pixel pour pixel
sur l'ensemble des écrans. Un fond différent par moniteur revient à coller
chaque image à la bonne position dans ce grand canevas.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image, ImageFilter

from . import library

# Emplacements XDG
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "multiwall"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "multiwall"
CONFIG_PATH = CONFIG_DIR / "config.json"

SCHEMA = "org.gnome.desktop.background"

#: Modes d'ajustement d'une image dans un cadre donné.
FIT_MODES = ("cover", "contain", "blur", "stretch", "center", "tile")

FIT_LABELS = {
    "cover": "Remplir (recadré)",
    "contain": "Entier (bandes)",
    "blur": "Entier (fond flouté)",
    "stretch": "Étirer",
    "center": "Taille réelle centrée",
    "tile": "Mosaïque",
}

#: Nombre d'images conservées dans l'historique.
HISTORIQUE_MAX = 60

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".jxl", ".avif")


# --------------------------------------------------------------------------- #
# Détection des moniteurs
# --------------------------------------------------------------------------- #

@dataclass
class Monitor:
    """Un écran physique, avec sa géométrie dans le bureau virtuel."""

    name: str
    width: int
    height: int
    x: int
    y: int
    primary: bool = False

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)

    @property
    def origin(self) -> tuple[int, int]:
        return (self.x, self.y)

    def __str__(self) -> str:
        star = " *" if self.primary else ""
        return f"{self.name}: {self.width}x{self.height}+{self.x}+{self.y}{star}"


_XRANDR_RE = re.compile(
    r"^(?P<name>\S+) connected (?P<primary>primary )?"
    r"(?P<w>\d+)x(?P<h>\d+)\+(?P<x>-?\d+)\+(?P<y>-?\d+)"
)


def parse_xrandr(output: str) -> list[Monitor]:
    """Extrait les écrans actifs d'une sortie `xrandr --query`.

    Les sorties débranchées, ou branchées mais sans mode actif, n'ont pas de
    géométrie sur leur ligne : elles ne matchent pas et sont donc ignorées.
    """
    monitors = [
        Monitor(
            name=m["name"],
            width=int(m["w"]),
            height=int(m["h"]),
            x=int(m["x"]),
            y=int(m["y"]),
            primary=bool(m["primary"]),
        )
        for m in (_XRANDR_RE.match(line) for line in output.splitlines())
        if m
    ]
    return normalize_origin(monitors)


def normalize_origin(monitors: list[Monitor]) -> list[Monitor]:
    """Ramène le coin supérieur gauche du bureau à (0, 0) et trie les écrans.

    Une disposition peut comporter des coordonnées négatives ; sans translation,
    `desktop_size` sous-estimerait le bureau et les écrans de gauche seraient
    collés hors du canevas, donc perdus.
    """
    if not monitors:
        return []
    dx = min(m.x for m in monitors)
    dy = min(m.y for m in monitors)
    if dx or dy:
        for m in monitors:
            m.x -= dx
            m.y -= dy
    monitors.sort(key=lambda mo: (mo.x, mo.y))
    return monitors


def detect_monitors() -> list[Monitor]:
    """Liste les écrans actifs, triés de gauche à droite puis de haut en bas.

    Passe par xrandr (X11) ; retombe sur GDK si xrandr est absent (Wayland).
    """
    try:
        out = subprocess.run(
            ["xrandr", "--query"], capture_output=True, text=True, check=True
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        return normalize_origin(_detect_monitors_gdk())
    return parse_xrandr(out)


def _detect_monitors_gdk() -> list[Monitor]:
    """Repli sans xrandr (utile sous Wayland)."""
    import gi

    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk

    display = Gdk.Display.get_default()
    if display is None:
        return []
    result = []
    for i in range(display.get_n_monitors()):
        mon = display.get_monitor(i)
        geo = mon.get_geometry()
        result.append(
            Monitor(
                name=mon.get_model() or f"monitor-{i}",
                width=geo.width,
                height=geo.height,
                x=geo.x,
                y=geo.y,
                primary=mon.is_primary(),
            )
        )
    return result


def desktop_size(monitors: list[Monitor]) -> tuple[int, int]:
    """Dimensions du bureau virtuel englobant tous les écrans."""
    if not monitors:
        return (1920, 1080)
    return (
        max(m.x + m.width for m in monitors),
        max(m.y + m.height for m in monitors),
    )


# --------------------------------------------------------------------------- #
# Ajustement d'une image dans un cadre
# --------------------------------------------------------------------------- #

def _open(path: str | Path) -> Image.Image:
    img = Image.open(path)
    # Respecte l'orientation EXIF des photos.
    try:
        from PIL import ImageOps

        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    return img.convert("RGB")


def fit_image(
    img: Image.Image,
    size: tuple[int, int],
    mode: str = "cover",
    background: tuple[int, int, int] = (0, 0, 0),
) -> Image.Image:
    """Renvoie une image exactement aux dimensions `size`, selon le mode choisi."""
    tw, th = size
    iw, ih = img.size
    if tw <= 0 or th <= 0 or iw <= 0 or ih <= 0:
        return Image.new("RGB", (max(tw, 1), max(th, 1)), background)

    if mode == "stretch":
        return img.resize(size, Image.LANCZOS)

    if mode == "tile":
        # Doubler la tuile avant de la répéter : sinon une image minuscule
        # demanderait des millions de collages pour couvrir 5760x1080.
        tuile = img
        while tuile.width < min(tw, 512) or tuile.height < min(th, 512):
            double = Image.new("RGB", (tuile.width * 2, tuile.height * 2))
            for oy in (0, tuile.height):
                for ox in (0, tuile.width):
                    double.paste(tuile, (ox, oy))
            tuile = double
        canvas = Image.new("RGB", size, background)
        for oy in range(0, th, tuile.height):
            for ox in range(0, tw, tuile.width):
                canvas.paste(tuile, (ox, oy))
        return canvas

    if mode == "center":
        canvas = Image.new("RGB", size, background)
        crop = img
        # Si l'image dépasse le cadre, on la recadre au centre.
        if iw > tw or ih > th:
            left = max((iw - tw) // 2, 0)
            top = max((ih - th) // 2, 0)
            crop = img.crop((left, top, left + min(iw, tw), top + min(ih, th)))
        cw, ch = crop.size
        canvas.paste(crop, ((tw - cw) // 2, (th - ch) // 2))
        return canvas

    if mode in ("contain", "blur"):
        ratio = min(tw / iw, th / ih)
        new = img.resize((max(round(iw * ratio), 1), max(round(ih * ratio), 1)), Image.LANCZOS)
        if mode == "blur":
            canvas = fit_image(img, size, "cover")
            canvas = canvas.filter(
                ImageFilter.GaussianBlur(radius=max(max(size) // 40, 1))
            )
            # Assombrit légèrement le fond pour faire ressortir l'image nette.
            canvas = Image.blend(canvas, Image.new("RGB", size, (0, 0, 0)), 0.35)
        else:
            canvas = Image.new("RGB", size, background)
        canvas.paste(new, ((tw - new.width) // 2, (th - new.height) // 2))
        return canvas

    # cover (défaut) : remplit tout le cadre, recadrage centré.
    # Le recadrage est calculé dans l'espace SOURCE et passé à resize(box=…) :
    # une image au ratio extrême (bannière, capture de page longue) ferait
    # exploser la mémoire si on redimensionnait avant de recadrer.
    ratio = max(tw / iw, th / ih)
    src_w = min(iw, tw / ratio)
    src_h = min(ih, th / ratio)
    left = (iw - src_w) / 2
    top = (ih - src_h) / 2
    return img.resize(size, Image.LANCZOS, box=(left, top, left + src_w, top + src_h))


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #

def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (0, 0, 0)


def compose_per_monitor(
    monitors: list[Monitor],
    assignments: dict[str, dict],
    background: str = "#000000",
    opener: Callable[[Path], Image.Image] | None = None,
) -> Image.Image:
    """Compose une image du bureau entier, une image source par moniteur.

    `assignments` : {nom_moniteur: {"path": str, "fit": str}}
    `opener` : ouverture alternative des images — la GUI y branche son cache de
    vignettes pour ne pas redécoder des JPEG pleine résolution à chaque aperçu.
    """
    load = opener or _open
    bg = hex_to_rgb(background)
    canvas = Image.new("RGB", desktop_size(monitors), bg)
    for mon in monitors:
        conf = assignments.get(mon.name)
        if not conf:
            continue

        identifiant = conf.get("library")
        if identifiant:
            # Fond généré : calculé à la taille exacte de CET écran, avec son
            # centre pour ancre — l'écran est ici le cadre, pas le bureau.
            seul = Monitor(mon.name, mon.width, mon.height, 0, 0)
            canvas.paste(library.rendu(identifiant, mon.size, [seul]), mon.origin)
            continue

        if not conf.get("path"):
            continue
        path = Path(conf["path"]).expanduser()
        if not path.is_file():
            continue
        try:
            source = load(path)
        except (OSError, ValueError):
            continue  # fichier illisible ou format non supporté
        canvas.paste(fit_image(source, mon.size, conf.get("fit", "cover"), bg), mon.origin)
    return canvas


def compose_span(
    monitors: list[Monitor],
    path: str | Path,
    fit: str = "cover",
    background: str = "#000000",
    opener: Callable[[Path], Image.Image] | None = None,
) -> Image.Image:
    """Compose le bureau entier à partir d'une seule image panoramique (5760x1080…)."""
    load = opener or _open
    bg = hex_to_rgb(background)
    return fit_image(load(Path(path).expanduser()), desktop_size(monitors), fit, bg)


# --------------------------------------------------------------------------- #
# Application via gsettings
# --------------------------------------------------------------------------- #

class WallpaperError(RuntimeError):
    """Échec de l'installation du fond d'écran (gsettings indisponible, etc.)."""


def _gsettings(*args: str) -> None:
    try:
        subprocess.run(["gsettings", *args], check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise WallpaperError(
            "La commande `gsettings` est introuvable — MultiWall cible les bureaux "
            "GNOME/Budgie."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or f"code de retour {exc.returncode}"
        raise WallpaperError(f"gsettings {' '.join(args)} a échoué : {detail}") from exc


def _has_key(key: str) -> bool:
    out = subprocess.run(
        ["gsettings", "list-keys", SCHEMA], capture_output=True, text=True
    ).stdout
    return key in out.split()


def apply_wallpaper(image: Image.Image, background: str = "#000000") -> Path:
    """Écrit le composite sur disque et l'installe comme fond d'écran étalé.

    Le fichier est horodaté : GNOME/Budgie ignore un `picture-uri` identique à
    l'actuel, donc réutiliser le même nom empêcherait le rafraîchissement.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Deux applications rapprochées peuvent tomber sur la même milliseconde :
    # on incrémente jusqu'à trouver un nom libre, sinon l'URI serait inchangée
    # et le bureau ne se rafraîchirait pas.
    stamp = int(time.time() * 1000)
    out = DATA_DIR / f"wall-{stamp}.png"
    while out.exists():
        stamp += 1
        out = DATA_DIR / f"wall-{stamp}.png"
    image.save(out, "PNG", optimize=False)

    uri = out.as_uri()
    _gsettings("set", SCHEMA, "picture-options", "spanned")
    _gsettings("set", SCHEMA, "primary-color", background)
    _gsettings("set", SCHEMA, "color-shading-type", "solid")
    _gsettings("set", SCHEMA, "picture-uri", uri)
    if _has_key("picture-uri-dark"):
        _gsettings("set", SCHEMA, "picture-uri-dark", uri)

    _cleanup(keep=out)
    return out


def _cleanup(keep: Path, max_files: int = 2) -> None:
    """Ne conserve que les composites les plus récents."""
    horodates = []
    for candidat in DATA_DIR.glob("wall-*.png"):
        try:
            horodates.append((candidat.stat().st_mtime, candidat))
        except OSError:
            continue  # supprimé entre-temps par une autre instance
    horodates.sort(reverse=True)
    for _, old in horodates[max_files:]:
        if old != keep:
            try:
                old.unlink()
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# Configuration persistée
# --------------------------------------------------------------------------- #

@dataclass
class Config:
    mode: str = "per-monitor"  # "per-monitor" | "span"
    background: str = "#000000"
    span: dict = field(default_factory=lambda: {"path": "", "fit": "cover", "library": ""})
    monitors: dict = field(default_factory=dict)  # {nom: {"path": ..., "fit": ...}}
    last_folder: str = ""         # dernier dossier du sélecteur d'images
    last_random_folder: str = ""  # dernier dossier de tirage aléatoire
    #: Images déjà utilisées au moins une fois, la plus récente en tête.
    historique: list = field(default_factory=list)

    @classmethod
    def load(cls) -> "Config":
        """Relit la config. Un fichier absent, corrompu ou bricolé à la main ne
        doit jamais empêcher l'application de démarrer : on repart des défauts."""
        if not CONFIG_PATH.is_file():
            return cls()
        try:
            data = json.loads(CONFIG_PATH.read_text())
        except Exception:
            return cls()
        if not isinstance(data, dict):
            return cls()

        def texte(cle: str, defaut: str) -> str:
            valeur = data.get(cle, defaut)
            return valeur if isinstance(valeur, str) else defaut

        span = data.get("span")
        if not isinstance(span, dict):
            span = {}
        biblio = span.get("library")
        span = {
            "path": span.get("path") if isinstance(span.get("path"), str) else "",
            "fit": span.get("fit") if span.get("fit") in FIT_MODES else "cover",
            # Fond généré : on ne garde l'identifiant que s'il existe encore.
            "library": biblio if isinstance(biblio, str) and library.existe(biblio) else "",
        }

        bruts = data.get("monitors")
        monitors = {}
        if isinstance(bruts, dict):
            for nom, conf in bruts.items():
                if not isinstance(nom, str) or not isinstance(conf, dict):
                    continue
                chemin = conf.get("path")
                biblio_ecran = conf.get("library")
                monitors[nom] = {
                    "path": chemin if isinstance(chemin, str) else "",
                    "fit": conf.get("fit") if conf.get("fit") in FIT_MODES else "cover",
                    "library": biblio_ecran if isinstance(biblio_ecran, str)
                    and library.existe(biblio_ecran) else "",
                }

        # Historique : on ne garde que des entrées exploitables.
        historique = []
        for entree in (data.get("historique") or []):
            if isinstance(entree, dict) and isinstance(entree.get("path"), str):
                historique.append({
                    "path": entree["path"],
                    "date": entree.get("date") if isinstance(
                        entree.get("date"), (int, float)) else 0,
                })

        mode = texte("mode", "per-monitor")
        return cls(
            mode=mode if mode in ("per-monitor", "span") else "per-monitor",
            background=texte("background", "#000000"),
            span=span,
            monitors=monitors,
            last_folder=texte("last_folder", ""),
            last_random_folder=texte("last_random_folder", ""),
            historique=historique,
        )

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        contenu = json.dumps(
            {
                "mode": self.mode,
                "background": self.background,
                "span": self.span,
                # Les écrans simplement sélectionnés, sans image, ne méritent
                # pas d'entrée : on ne garde que ce qui porte une affectation.
                "monitors": {n: c for n, c in self.monitors.items()
                             if c.get("path") or c.get("library")},
                "last_folder": self.last_folder,
                "last_random_folder": self.last_random_folder,
                "historique": self.historique,
            },
            indent=2,
            ensure_ascii=False,
        )
        # Écriture atomique : une interruption ne doit pas laisser un JSON
        # tronqué, que la prochaine lecture rejetterait silencieusement.
        temporaire = CONFIG_PATH.with_suffix(".json.tmp")
        temporaire.write_text(contenu)
        os.replace(temporaire, CONFIG_PATH)

    def noter_image(self, chemin: str | Path) -> None:
        """Mémorise une image apportée par l'utilisateur, pour la retrouver plus tard."""
        chemin = str(Path(chemin).expanduser())
        self.historique = [e for e in self.historique if e.get("path") != chemin]
        self.historique.insert(0, {"path": chemin, "date": time.time()})
        del self.historique[HISTORIQUE_MAX:]

    def oublier_image(self, chemin: str | Path) -> None:
        chemin = str(chemin)
        self.historique = [e for e in self.historique if e.get("path") != chemin]

    def images_connues(self) -> list[str]:
        """Images de l'historique encore présentes sur le disque, plus récente en tête.

        Un fichier déplacé ou supprimé — ou une photo sortie du cache — ne doit
        pas apparaître dans la bibliothèque.
        """
        vues, resultat = set(), []
        for entree in self.historique:
            chemin = entree.get("path", "")
            if chemin and chemin not in vues and Path(chemin).expanduser().is_file():
                vues.add(chemin)
                resultat.append(chemin)
        return resultat

    def has_image(self, monitors: list[Monitor] | None = None) -> bool:
        """Y a-t-il de quoi composer dans le mode courant ?

        Si `monitors` est fourni, seules les images affectées à un écran
        RÉELLEMENT présent comptent.
        """
        if self.mode == "span":
            return bool(self.span.get("path") or self.span.get("library"))
        rempli = lambda c: bool(c.get("path") or c.get("library"))  # noqa: E731
        if monitors is None:
            return any(rempli(c) for c in self.monitors.values())
        presents = {m.name for m in monitors}
        return any(rempli(c) for n, c in self.monitors.items() if n in presents)

    def compose(self, monitors: list[Monitor], opener=None) -> Image.Image:
        if self.mode == "span":
            # Un fond de la bibliothèque se recalcule à la taille exacte du
            # bureau : il suit un changement d'écrans sans être redimensionné.
            identifiant = self.span.get("library")
            if identifiant:
                return library.rendu(identifiant, desktop_size(monitors), monitors)
            if not self.span.get("path"):
                raise ValueError("Aucune image panoramique sélectionnée.")
            return compose_span(
                monitors, self.span["path"], self.span.get("fit", "cover"),
                self.background, opener,
            )
        if not self.has_image():
            raise ValueError("Aucune image sélectionnée pour les moniteurs.")
        if not self.has_image(monitors):
            # Cas typique après un changement de configuration d'écrans :
            # composer quand même produirait un fond entièrement noir, sans rien dire.
            configures = ", ".join(sorted(n for n, c in self.monitors.items()
                                          if c.get("path"))) or "aucun"
            detectes = ", ".join(m.name for m in monitors) or "aucun"
            raise ValueError(
                "Aucune image ne correspond aux écrans détectés "
                f"(configurés : {configures} · détectés : {detectes})."
            )
        return compose_per_monitor(monitors, self.monitors, self.background, opener)

    def apply(self, monitors: list[Monitor] | None = None) -> Path:
        monitors = monitors or detect_monitors()
        return apply_wallpaper(self.compose(monitors), self.background)


def scaled_monitors(monitors: list[Monitor], scale: float) -> list[Monitor]:
    """Même disposition à une autre échelle — sert à composer un aperçu léger."""
    return [
        Monitor(
            name=m.name,
            width=max(round(m.width * scale), 1),
            height=max(round(m.height * scale), 1),
            x=round(m.x * scale),
            y=round(m.y * scale),
            primary=m.primary,
        )
        for m in monitors
    ]


def list_images(folder: str | Path) -> list[Path]:
    """Toutes les images d'un dossier (récursif), triées."""
    root = Path(folder).expanduser()
    return sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
