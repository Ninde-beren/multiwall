# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Tests unitaires : détection des écrans, ajustement d'image, composition, config."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from multiwall import core

# Sortie réelle de `xrandr --query` sur la machine cible (3 x 1920x1080).
XRANDR_TRIPLE = """Screen 0: minimum 320 x 200, current 5760 x 1080, maximum 16384 x 16384
DisplayPort-0 connected primary 1920x1080+1920+0 (normal left inverted right x axis y axis) 544mm x 303mm
   1920x1080     60.00*+  74.97
DisplayPort-1 connected 1920x1080+3840+0 (normal left inverted right x axis y axis) 544mm x 303mm
   1920x1080     60.00*+
DisplayPort-2 connected 1920x1080+0+0 (normal left inverted right x axis y axis) 544mm x 303mm
   1920x1080     60.00*+
HDMI-A-0 disconnected (normal left inverted right x axis y axis)
"""

XRANDR_UNUSED = """Screen 0: minimum 320 x 200, current 1920 x 1080, maximum 16384 x 16384
eDP-1 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis) 344mm x 193mm
   1920x1080     60.00*+
HDMI-1 connected (normal left inverted right x axis y axis) 0mm x 0mm
   1920x1080     60.00
"""

XRANDR_ROTATED = """Screen 0: minimum 320 x 200, current 3000 x 1920, maximum 16384 x 16384
DP-1 connected primary 1920x1080+1080+420 (normal left inverted right x axis y axis) 544mm x 303mm
DP-2 connected 1080x1920+0+0 left (normal left inverted right x axis y axis) 544mm x 303mm
"""


class TestParseXrandr(unittest.TestCase):
    def test_trois_ecrans_tries_de_gauche_a_droite(self):
        mons = core.parse_xrandr(XRANDR_TRIPLE)
        self.assertEqual([m.name for m in mons],
                         ["DisplayPort-2", "DisplayPort-0", "DisplayPort-1"])
        self.assertEqual([m.x for m in mons], [0, 1920, 3840])
        self.assertTrue(all(m.size == (1920, 1080) for m in mons))

    def test_ecran_primaire_identifie(self):
        mons = core.parse_xrandr(XRANDR_TRIPLE)
        primaires = [m.name for m in mons if m.primary]
        self.assertEqual(primaires, ["DisplayPort-0"])

    def test_sortie_debranchee_ignoree(self):
        self.assertNotIn("HDMI-A-0", [m.name for m in core.parse_xrandr(XRANDR_TRIPLE)])

    def test_sortie_branchee_sans_mode_actif_ignoree(self):
        mons = core.parse_xrandr(XRANDR_UNUSED)
        self.assertEqual([m.name for m in mons], ["eDP-1"])

    def test_ecran_pivote_garde_sa_geometrie_effective(self):
        mons = core.parse_xrandr(XRANDR_ROTATED)
        pivote = next(m for m in mons if m.name == "DP-2")
        self.assertEqual(pivote.size, (1080, 1920))

    def test_sortie_vide(self):
        self.assertEqual(core.parse_xrandr(""), [])


class TestDesktopSize(unittest.TestCase):
    def test_trois_ecrans_horizontaux(self):
        self.assertEqual(core.desktop_size(core.parse_xrandr(XRANDR_TRIPLE)), (5760, 1080))

    def test_ecrans_empiles_verticalement(self):
        mons = [core.Monitor("a", 1920, 1080, 0, 0), core.Monitor("b", 1920, 1080, 0, 1080)]
        self.assertEqual(core.desktop_size(mons), (1920, 2160))

    def test_ecrans_decales_verticalement(self):
        # Un écran pivoté à côté d'un paysage : le bureau englobe les deux.
        self.assertEqual(core.desktop_size(core.parse_xrandr(XRANDR_ROTATED)), (3000, 1920))

    def test_aucun_ecran_retourne_une_taille_par_defaut(self):
        self.assertEqual(core.desktop_size([]), (1920, 1080))


class TestFitImage(unittest.TestCase):
    def setUp(self):
        # Image 4:3 nettement plus "carrée" que les cadres 16:9 testés.
        self.img = Image.new("RGB", (400, 300), (255, 0, 0))

    def test_tous_les_modes_rendent_exactement_la_taille_demandee(self):
        for mode in core.FIT_MODES:
            for size in ((1920, 1080), (300, 900), (1, 1), (5760, 1080)):
                with self.subTest(mode=mode, size=size):
                    self.assertEqual(core.fit_image(self.img, size, mode).size, size)

    def test_image_1px_ne_plante_pas(self):
        tiny = Image.new("RGB", (1, 1), (0, 255, 0))
        for mode in core.FIT_MODES:
            with self.subTest(mode=mode):
                self.assertEqual(core.fit_image(tiny, (640, 480), mode).size, (640, 480))

    def test_taille_cible_degeneree_ne_plante_pas(self):
        out = core.fit_image(self.img, (0, 0), "cover")
        self.assertEqual(out.size, (1, 1))

    def test_cover_ne_laisse_aucune_bande_de_fond(self):
        out = core.fit_image(self.img, (1920, 1080), "cover", background=(0, 0, 255))
        couleurs = {out.getpixel(p) for p in
                    ((0, 0), (1919, 0), (0, 1079), (1919, 1079), (960, 540))}
        self.assertNotIn((0, 0, 255), couleurs)

    def test_contain_remplit_les_bandes_avec_la_couleur_de_fond(self):
        out = core.fit_image(self.img, (1920, 1080), "contain", background=(0, 0, 255))
        # Image 4:3 dans un cadre 16:9 : bandes verticales à gauche et à droite.
        self.assertEqual(out.getpixel((5, 540)), (0, 0, 255))
        self.assertEqual(out.getpixel((1914, 540)), (0, 0, 255))
        self.assertEqual(out.getpixel((960, 540)), (255, 0, 0))

    def test_blur_ne_laisse_pas_de_bande_unie(self):
        # Le fond est tiré de l'image elle-même : pas de bande de couleur brute.
        img = Image.new("RGB", (400, 300), (200, 100, 50))
        out = core.fit_image(img, (1920, 1080), "blur", background=(0, 0, 255))
        self.assertNotEqual(out.getpixel((5, 540)), (0, 0, 255))

    def test_center_centre_une_petite_image_sans_la_redimensionner(self):
        out = core.fit_image(self.img, (1920, 1080), "center", background=(0, 0, 255))
        self.assertEqual(out.getpixel((960, 540)), (255, 0, 0))   # image au centre
        self.assertEqual(out.getpixel((10, 10)), (0, 0, 255))     # fond autour
        # Bord de l'image : (1920-400)/2 = 760
        self.assertEqual(out.getpixel((755, 540)), (0, 0, 255))
        self.assertEqual(out.getpixel((765, 540)), (255, 0, 0))

    def test_center_recadre_une_image_plus_grande_que_le_cadre(self):
        grande = Image.new("RGB", (3000, 2000), (255, 0, 0))
        out = core.fit_image(grande, (800, 600), "center", background=(0, 0, 255))
        self.assertEqual(out.size, (800, 600))
        self.assertEqual(out.getpixel((0, 0)), (255, 0, 0))  # aucun fond visible

    def test_tile_couvre_tout_le_cadre(self):
        out = core.fit_image(self.img, (1000, 700), "tile", background=(0, 0, 255))
        coins = {out.getpixel(p) for p in ((0, 0), (999, 0), (0, 699), (999, 699))}
        self.assertEqual(coins, {(255, 0, 0)})

    def test_stretch_deforme_sans_bandes(self):
        out = core.fit_image(self.img, (1920, 1080), "stretch", background=(0, 0, 255))
        self.assertEqual(out.getpixel((0, 0)), (255, 0, 0))

    def test_mode_inconnu_retombe_sur_cover(self):
        attendu = core.fit_image(self.img, (800, 600), "cover")
        obtenu = core.fit_image(self.img, (800, 600), "mode-bidon")
        self.assertEqual(list(obtenu.getdata()), list(attendu.getdata()))


class TestHexToRgb(unittest.TestCase):
    def test_formats_valides(self):
        self.assertEqual(core.hex_to_rgb("#ff0000"), (255, 0, 0))
        self.assertEqual(core.hex_to_rgb("00ff00"), (0, 255, 0))
        self.assertEqual(core.hex_to_rgb("#fff"), (255, 255, 255))
        self.assertEqual(core.hex_to_rgb("  #101010  "), (16, 16, 16))

    def test_valeur_invalide_retombe_sur_noir(self):
        self.assertEqual(core.hex_to_rgb("pas-une-couleur"), (0, 0, 0))
        self.assertEqual(core.hex_to_rgb(""), (0, 0, 0))


class TestComposition(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.monitors = core.parse_xrandr(XRANDR_TRIPLE)
        self.paths = {}
        for nom, couleur in (("rouge", (255, 0, 0)), ("vert", (0, 255, 0)), ("bleu", (0, 0, 255))):
            p = Path(self.tmp.name) / f"{nom}.png"
            Image.new("RGB", (1920, 1080), couleur).save(p)
            self.paths[nom] = str(p)

    def tearDown(self):
        self.tmp.cleanup()

    def test_chaque_image_atterrit_sur_le_bon_ecran(self):
        assignments = {
            "DisplayPort-2": {"path": self.paths["rouge"], "fit": "cover"},
            "DisplayPort-0": {"path": self.paths["vert"], "fit": "cover"},
            "DisplayPort-1": {"path": self.paths["bleu"], "fit": "cover"},
        }
        out = core.compose_per_monitor(self.monitors, assignments)
        self.assertEqual(out.size, (5760, 1080))
        self.assertEqual(out.getpixel((960, 540)), (255, 0, 0))    # écran gauche  (x 0)
        self.assertEqual(out.getpixel((2880, 540)), (0, 255, 0))   # écran centre  (x 1920)
        self.assertEqual(out.getpixel((4800, 540)), (0, 0, 255))   # écran droit   (x 3840)

    def test_ecran_sans_image_recoit_la_couleur_de_fond(self):
        out = core.compose_per_monitor(
            self.monitors,
            {"DisplayPort-2": {"path": self.paths["rouge"], "fit": "cover"}},
            background="#123456",
        )
        self.assertEqual(out.getpixel((960, 540)), (255, 0, 0))
        self.assertEqual(out.getpixel((2880, 540)), (0x12, 0x34, 0x56))

    def test_image_supprimee_entre_temps_ne_plante_pas(self):
        assignments = {"DisplayPort-2": {"path": "/chemin/inexistant.png", "fit": "cover"}}
        out = core.compose_per_monitor(self.monitors, assignments, background="#000000")
        self.assertEqual(out.size, (5760, 1080))
        self.assertEqual(out.getpixel((960, 540)), (0, 0, 0))

    def test_assignment_pour_un_ecran_disparu_est_ignore(self):
        assignments = {
            "DisplayPort-2": {"path": self.paths["rouge"], "fit": "cover"},
            "ECRAN-DEBRANCHE": {"path": self.paths["vert"], "fit": "cover"},
        }
        out = core.compose_per_monitor(self.monitors, assignments)
        self.assertEqual(out.getpixel((960, 540)), (255, 0, 0))

    def test_bureau_non_rectangulaire(self):
        mons = core.parse_xrandr(XRANDR_ROTATED)
        out = core.compose_per_monitor(
            mons, {"DP-2": {"path": self.paths["rouge"], "fit": "stretch"}}, background="#000000"
        )
        self.assertEqual(out.size, (3000, 1920))
        self.assertEqual(out.getpixel((540, 960)), (255, 0, 0))
        self.assertEqual(out.getpixel((2000, 1900)), (0, 0, 0))  # zone hors écrans

    def test_span_couvre_tout_le_bureau(self):
        pano = Path(self.tmp.name) / "pano.png"
        Image.new("RGB", (5760, 1080), (10, 20, 30)).save(pano)
        out = core.compose_span(self.monitors, pano)
        self.assertEqual(out.size, (5760, 1080))
        for x in (0, 1920, 3840, 5759):
            self.assertEqual(out.getpixel((x, 540)), (10, 20, 30))

    def test_span_d_une_petite_image_est_agrandi(self):
        petite = Path(self.tmp.name) / "petite.png"
        Image.new("RGB", (100, 100), (10, 20, 30)).save(petite)
        out = core.compose_span(self.monitors, petite, "contain", "#000000")
        self.assertEqual(out.size, (5760, 1080))


class TestScaledMonitors(unittest.TestCase):
    def test_mise_a_l_echelle_conserve_la_disposition(self):
        mons = core.scaled_monitors(core.parse_xrandr(XRANDR_TRIPLE), 0.1)
        self.assertEqual([(m.x, m.width) for m in mons], [(0, 192), (192, 192), (384, 192)])
        self.assertEqual(core.desktop_size(mons), (576, 108))

    def test_echelle_minuscule_ne_produit_pas_de_dimension_nulle(self):
        mons = core.scaled_monitors(core.parse_xrandr(XRANDR_TRIPLE), 0.0001)
        self.assertTrue(all(m.width >= 1 and m.height >= 1 for m in mons))


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = (core.CONFIG_DIR, core.CONFIG_PATH)
        core.CONFIG_DIR = Path(self.tmp.name) / "multiwall"
        core.CONFIG_PATH = core.CONFIG_DIR / "config.json"

    def tearDown(self):
        core.CONFIG_DIR, core.CONFIG_PATH = self._orig
        self.tmp.cleanup()

    def test_aller_retour_sauvegarde_chargement(self):
        cfg = core.Config(mode="span", background="#112233")
        cfg.span = {"path": "/a/b.png", "fit": "blur"}
        cfg.monitors = {"DP-1": {"path": "/c/d.png", "fit": "tile"}}
        cfg.save()

        relu = core.Config.load()
        self.assertEqual(relu.mode, "span")
        self.assertEqual(relu.background, "#112233")
        self.assertEqual(relu.span["fit"], "blur")
        self.assertEqual(relu.monitors["DP-1"]["path"], "/c/d.png")

    def test_absence_de_fichier_donne_les_valeurs_par_defaut(self):
        cfg = core.Config.load()
        self.assertEqual(cfg.mode, "per-monitor")
        self.assertEqual(cfg.background, "#000000")
        self.assertEqual(cfg.monitors, {})

    def test_config_corrompue_ne_plante_pas(self):
        core.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        core.CONFIG_PATH.write_text("{ ceci n'est pas du JSON")
        self.assertEqual(core.Config.load().mode, "per-monitor")

    def test_config_partielle_complete_les_manquants(self):
        core.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        core.CONFIG_PATH.write_text(json.dumps({"mode": "span"}))
        cfg = core.Config.load()
        self.assertEqual(cfg.mode, "span")
        self.assertEqual(cfg.background, "#000000")
        self.assertEqual(cfg.span["fit"], "cover")

    def test_compose_sans_image_leve_une_erreur_explicite(self):
        with self.assertRaises(ValueError):
            core.Config().compose(core.parse_xrandr(XRANDR_TRIPLE))
        with self.assertRaises(ValueError):
            core.Config(mode="span").compose(core.parse_xrandr(XRANDR_TRIPLE))

    def test_accents_et_espaces_preserves_dans_la_config(self):
        cfg = core.Config()
        cfg.monitors = {"DP-1": {"path": "/home/été/mon fond d'écran.png", "fit": "cover"}}
        cfg.save()
        self.assertEqual(
            core.Config.load().monitors["DP-1"]["path"], "/home/été/mon fond d'écran.png"
        )


class TestListImages(unittest.TestCase):
    def test_parcourt_recursivement_et_filtre_les_extensions(self):
        with tempfile.TemporaryDirectory() as d:
            racine = Path(d)
            (racine / "sous").mkdir()
            for nom in ("a.jpg", "b.PNG", "notes.txt", "sous/c.webp", "sous/.cache"):
                (racine / nom).write_bytes(b"x")
            trouvees = [p.name for p in core.list_images(racine)]
            self.assertCountEqual(trouvees, ["a.jpg", "b.PNG", "c.webp"])

    def test_dossier_inexistant_retourne_une_liste_vide(self):
        self.assertEqual(core.list_images("/chemin/qui/nexiste/pas"), [])


if __name__ == "__main__":
    unittest.main()
