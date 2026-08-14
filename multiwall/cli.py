# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Interface en ligne de commande de MultiWall."""

from __future__ import annotations

import argparse
import random
import subprocess
import sys
from pathlib import Path

from . import core, doctor, library, photos


def _print_monitors(monitors: list[core.Monitor]) -> None:
    w, h = core.desktop_size(monitors)
    print(f"Bureau virtuel : {w}x{h}")
    for m in monitors:
        print(f"  {m}")


def _fichier(chemin: str) -> Path:
    """Résout un chemin d'image, en échouant tôt s'il n'est pas utilisable."""
    p = Path(chemin).expanduser().resolve()
    if not p.is_file():
        raise ValueError(f"Fichier introuvable : {p}")
    return p


def cmd_list(args, monitors):
    _print_monitors(monitors)
    return 0


def cmd_span(args, monitors):
    image = _fichier(args.image)
    cfg = core.Config.load()
    cfg.mode = "span"
    cfg.span = {"path": str(image), "fit": args.fit}
    cfg.noter_image(image)
    if args.background:
        cfg.background = args.background

    out = cfg.apply(monitors)
    cfg.save()  # on ne persiste qu'une configuration qui a fonctionné
    w, h = core.desktop_size(monitors)
    print(f"Fond panoramique appliqué ({w}x{h}) → {out}")
    return 0


def _resoudre_assignments(items: list[str], noms: list[str]) -> dict[str, str]:
    """Transforme les arguments en {nom_écran: chemin}.

    Accepte `NOM=chemin` et les chemins nus, qui remplissent les écrans libres
    de gauche à droite. Un « = » dans un nom de fichier ne doit pas être pris
    pour un ciblage d'écran.
    """
    resultat: dict[str, str] = {}
    for item in items:
        cible = None
        chemin = item
        if "=" in item:
            prefixe, reste = item.split("=", 1)
            if prefixe in noms:
                cible, chemin = prefixe, reste
            elif not Path(item).expanduser().is_file():
                # Ni un écran connu, ni un fichier existant : c'était un ciblage.
                raise ValueError(
                    f"Écran inconnu : {prefixe} (disponibles : {', '.join(noms)})"
                )
        if cible is None:
            libres = [n for n in noms if n not in resultat]
            if not libres:
                raise ValueError(f"Trop d'images pour {len(noms)} écran(s).")
            cible = libres[0]
        if cible in resultat:
            raise ValueError(f"Deux images visent le même écran : {cible}")
        resultat[cible] = str(_fichier(chemin))
    return resultat


def cmd_set(args, monitors):
    noms = [m.name for m in monitors]
    assignments = _resoudre_assignments(args.assignment, noms)

    cfg = core.Config.load()
    cfg.mode = "per-monitor"
    if args.background:
        cfg.background = args.background
    for nom, chemin in assignments.items():
        cfg.monitors[nom] = {"path": chemin, "fit": args.fit}
        cfg.noter_image(chemin)

    out = cfg.apply(monitors)
    cfg.save()
    for m in monitors:
        conf = cfg.monitors.get(m.name, {})
        print(f"  {m.name}: {conf.get('path', '(vide)')} [{conf.get('fit', '-')}]")
    print(f"Appliqué → {out}")
    return 0


def cmd_random(args, monitors):
    images = core.list_images(args.folder)
    if not images:
        raise ValueError(f"Aucune image trouvée dans {args.folder}")
    cfg = core.Config.load()
    cfg.last_random_folder = str(Path(args.folder).expanduser().resolve())

    if args.span:
        tiree = str(random.choice(images))
        cfg.span = {"path": tiree, "fit": args.fit}
        cfg.mode = "span"
        cfg.noter_image(tiree)
    else:
        cfg.mode = "per-monitor"
        # Évite de répéter la même image si le dossier en contient assez.
        pool = random.sample(images, len(monitors)) if len(images) >= len(monitors) \
            else [random.choice(images) for _ in monitors]
        for mon, img in zip(monitors, pool):
            cfg.monitors[mon.name] = {"path": str(img), "fit": args.fit}
            cfg.noter_image(img)

    out = cfg.apply(monitors)
    cfg.save()
    print(f"Aléatoire appliqué depuis {args.folder} → {out}")
    return 0


def cmd_library(args, monitors):
    if not args.fond:
        largeur, hauteur = core.desktop_size(monitors)
        print(f"Fonds générés, rendus à la taille de votre bureau ({largeur}x{hauteur}) :")
        for fond in library.CATALOGUE:
            print(f"  {fond.id:<12} {fond.nom:<14} {fond.style}/{fond.palette}")
        print("\nAppliquer : multiwall library <identifiant>")
        return 0

    fond = library.get(args.fond)  # lève une ValueError si inconnu
    cfg = core.Config.load()
    cfg.mode = "span"
    cfg.span = {"path": "", "fit": "cover", "library": fond.id}
    out = cfg.apply(monitors)
    cfg.save()
    largeur, hauteur = core.desktop_size(monitors)
    print(f"« {fond.nom} » appliqué en {largeur}x{hauteur} → {out}")
    return 0


def cmd_photos(args, monitors):
    largeur, hauteur = core.desktop_size(monitors)
    ratio = largeur / hauteur if hauteur else 0
    terme = args.terme or "panorama landscape"

    trouvees = photos.rechercher(terme, ratio)[:args.nombre]
    if not trouvees:
        raise ValueError(
            f"Aucune photo au format {largeur}x{hauteur} pour « {terme} ». "
            "Essayez un autre terme, en anglais."
        )

    if args.use is None:
        print(f"Photos au format de votre bureau ({largeur}x{hauteur}) — « {terme} » :")
        for i, photo in enumerate(trouvees, 1):
            print(f"  {i:>2}. {photo.largeur}x{photo.hauteur} ratio {photo.ratio:.2f}  "
                  f"[{photo.licence}] {photo.nom[:46]}")
        print(f"\nAppliquer : multiwall photos \"{terme}\" --use N")
        return 0

    if not 1 <= args.use <= len(trouvees):
        raise ValueError(f"Numéro hors liste : {args.use} (1 à {len(trouvees)})")

    photo = trouvees[args.use - 1]
    chemin = photos.obtenir(photo, largeur)
    photos.purger()

    cfg = core.Config.load()
    cfg.mode = "span"
    cfg.span = {"path": str(chemin), "fit": "cover", "library": ""}
    cfg.noter_image(chemin)
    out = cfg.apply(monitors)
    cfg.save()
    print(f"« {photo.nom[:50]} » appliqué → {out}")
    print(f"  {photo.licence} — {photo.auteur[:60]}")
    if photo.url_page:
        print(f"  {photo.url_page}")
    return 0


def cmd_doctor(args, monitors):
    if args.gui:
        from .windows import DiagnosticWindow
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        fenetre = DiagnosticWindow()
        fenetre.connect("destroy", Gtk.main_quit)
        fenetre.show_all()
        Gtk.main()
        return 0

    rapport = doctor.analyser()
    print(doctor.formater(rapport))

    if args.mire:
        if not rapport.utilisable:
            print("\nMire non posée : l'environnement n'est pas supporté.", file=sys.stderr)
            return 1
        print(f"\nUne couleur et un cadre par écran vont être appliqués "
              f"({len(monitors)} écran(s)).")
        etat = doctor.poser_mire(monitors)
        print("Mire posée. Affichez votre bureau pour la voir.")
        print("Attendu : chaque écran d'une couleur unie, avec un cadre blanc net "
              "qui suit ses bords.")
        print("Si un écran affiche toute la mire en réduction, le mode « étalé » "
              "n'est pas honoré.")
        try:
            input("\nAppuyez sur Entrée pour restaurer votre fond d'écran… ")
        except (EOFError, KeyboardInterrupt):
            print()
        doctor.restaurer(etat)
        print("Fond d'écran restauré.")

    return 0 if rapport.utilisable else 1


def cmd_apply(args, monitors):
    out = core.Config.load().apply(monitors)
    print(f"Configuration réappliquée → {out}")
    return 0


def cmd_export(args, monitors):
    cfg = core.Config.load()
    img = cfg.compose(monitors)
    dest = Path(args.output).expanduser().resolve()
    img.save(dest)
    print(f"Composite {img.width}x{img.height} enregistré → {dest}")
    return 0


def cmd_gui(args, monitors):
    from .gui import run

    return run()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="multiwall",
        description="Un fond d'écran différent par moniteur, ou une image panoramique "
                    "étalée sur tous les écrans.",
    )
    sub = p.add_subparsers(dest="command")

    sub.add_parser("gui", help="Ouvre l'interface graphique (défaut)")
    sub.add_parser("list", help="Affiche les écrans détectés")

    sp = sub.add_parser("span", help="Étale une image panoramique sur tous les écrans")
    sp.add_argument("image")
    sp.add_argument("--fit", choices=core.FIT_MODES, default="cover")
    sp.add_argument("--background", help="Couleur de fond, ex. #101010")

    st = sub.add_parser("set", help="Assigne une image par écran (NOM=chemin ou juste chemins)")
    st.add_argument("assignment", nargs="+")
    st.add_argument("--fit", choices=core.FIT_MODES, default="cover")
    st.add_argument("--background", help="Couleur de fond, ex. #101010")

    rd = sub.add_parser("random", help="Tire au sort dans un dossier d'images")
    rd.add_argument("folder")
    rd.add_argument("--span", action="store_true", help="Une seule image étalée sur tous les écrans")
    rd.add_argument("--fit", choices=core.FIT_MODES, default="cover")

    lb = sub.add_parser("library", help="Fonds panoramiques générés (sans argument : la liste)")
    lb.add_argument("fond", nargs="?", help="Identifiant du fond à appliquer")

    ph = sub.add_parser("photos", help="Photos panoramiques libres (Wikimedia Commons)")
    ph.add_argument("terme", nargs="?", help="Recherche, en anglais (ex. « mountain »)")
    ph.add_argument("--use", type=int, metavar="N", help="Applique la N-ième photo listée")
    ph.add_argument("--nombre", type=int, default=12, help="Nombre de résultats (12 par défaut)")

    dc = sub.add_parser("doctor", help="Vérifie que l'environnement est supporté")
    dc.add_argument("--mire", action="store_true",
                    help="Applique une mire de contrôle, puis restaure le fond")
    dc.add_argument("--gui", action="store_true",
                    help="Affiche le diagnostic dans une fenêtre")

    sub.add_parser("apply", help="Réapplique la dernière configuration (login, hotplug…)")

    ex = sub.add_parser("export", help="Enregistre le composite dans un fichier")
    ex.add_argument("output")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "gui"

    monitors = core.detect_monitors()
    if not monitors and command != "doctor":
        print("Aucun écran détecté.", file=sys.stderr)
        return 1

    handlers = {
        "gui": cmd_gui,
        "list": cmd_list,
        "span": cmd_span,
        "set": cmd_set,
        "random": cmd_random,
        "library": cmd_library,
        "photos": cmd_photos,
        "doctor": cmd_doctor,
        "apply": cmd_apply,
        "export": cmd_export,
    }
    try:
        return handlers[command](args, monitors)
    except (ValueError, OSError, subprocess.SubprocessError, core.WallpaperError,
            photos.ReseauIndisponible) as exc:
        # Une erreur attendue (fichier manquant, écrans changés, gsettings en
        # échec…) doit sortir un message lisible, pas une trace Python.
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
