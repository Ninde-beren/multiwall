# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Tests de non-régression des défauts remontés par la revue de code.

Chaque test porte le symptôme observé, pour qu'une régression soit lisible sans
avoir à retrouver la revue d'origine.
"""

import json
import time
import unittest

from PIL import Image

from multiwall import core
from support import FAUX_GSETTINGS_ECHEC, BaseIntegration
from test_cli import TROIS_ECRANS, BaseCLI


class TestConfigEmpoisonnee(BaseCLI):
    """`span` sur un fichier absent enregistrait la config avant de l'appliquer :
    tout `apply` suivant (dont l'autostart) plantait à chaque ouverture de session."""

    def test_span_sur_fichier_absent_ne_persiste_rien(self):
        code, _, err = self.run_cli("span", "/nexiste/pas.jpg")
        self.assertEqual(code, 1)
        self.assertIn("introuvable", err)
        self.assertFalse(core.CONFIG_PATH.exists(), "aucune config ne doit être écrite")

    def test_span_en_echec_preserve_la_config_precedente(self):
        bonne = self.image_test("bonne.png", size=(5760, 1080))
        self.run_cli("span", str(bonne))
        self.run_cli("span", "/nexiste/pas.jpg")
        self.assertEqual(core.Config.load().span["path"], str(bonne))

    def test_apply_reste_utilisable_apres_un_span_rate(self):
        bonne = self.image_test("bonne.png", size=(5760, 1080))
        self.run_cli("span", str(bonne))
        self.run_cli("span", "/nexiste/pas.jpg")
        self.assertEqual(self.run_cli("apply")[0], 0)


class TestEcransDisparus(BaseCLI):
    """Après un changement de configuration d'écrans, `apply` composait un fond
    entièrement noir et renvoyait 0, sans rien signaler."""

    def test_apply_refuse_de_poser_un_fond_noir(self):
        img = self.image_test("a.png", couleur=(255, 0, 0))
        self.run_cli("set", f"DP-centre={img}")

        # L'utilisateur débranche tout et branche un écran de portable.
        self.ecrans = [core.Monitor("eDP-1", 1920, 1080, 0, 0)]
        core.detect_monitors = lambda: list(self.ecrans)

        code, _, err = self.run_cli("apply")
        self.assertEqual(code, 1)
        self.assertIn("DP-centre", err)
        self.assertIn("eDP-1", err)

    def test_un_seul_ecran_encore_present_suffit(self):
        img = self.image_test("a.png", couleur=(255, 0, 0))
        self.run_cli("set", f"DP-gauche={img}")
        self.ecrans = [core.Monitor("DP-gauche", 1920, 1080, 0, 0)]
        core.detect_monitors = lambda: list(self.ecrans)
        self.assertEqual(self.run_cli("apply")[0], 0)


class TestGsettingsEnEchec(BaseCLI):
    """L'échec de gsettings n'est pas une OSError : il passait à travers les
    `except` et sortait en trace Python."""

    gsettings_script = FAUX_GSETTINGS_ECHEC

    def test_message_lisible_et_code_de_retour(self):
        img = self.image_test("a.png")
        code, _, err = self.run_cli("set", f"DP-gauche={img}")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        self.assertIn("bus de session", err, "le stderr de gsettings doit remonter")

    def test_l_erreur_est_typee(self):
        with self.assertRaises(core.WallpaperError):
            core.apply_wallpaper(Image.new("RGB", (40, 40)))


class TestRatiosExtremes(unittest.TestCase):
    """`cover` redimensionnait l'image entière avant de recadrer : une bannière
    ou une capture de page longue faisait exploser la mémoire."""

    def test_banniere_tres_large(self):
        depart = time.monotonic()
        out = core.fit_image(Image.new("RGB", (3000, 2), (255, 0, 0)), (1920, 1080), "cover")
        self.assertEqual(out.size, (1920, 1080))
        self.assertLess(time.monotonic() - depart, 5.0)

    def test_capture_de_page_longue_en_panoramique(self):
        depart = time.monotonic()
        out = core.fit_image(Image.new("RGB", (1080, 12000), (0, 255, 0)), (5760, 1080), "cover")
        self.assertEqual(out.size, (5760, 1080))
        self.assertLess(time.monotonic() - depart, 5.0)

    def test_meme_protection_en_mode_blur(self):
        out = core.fit_image(Image.new("RGB", (3000, 2)), (1920, 1080), "blur")
        self.assertEqual(out.size, (1920, 1080))

    def test_cover_reste_centre(self):
        # Bande horizontale rouge au centre d'une image haute : après un cover
        # vers un cadre large, le centre doit rester rouge.
        img = Image.new("RGB", (1000, 3000), (0, 0, 255))
        img.paste(Image.new("RGB", (1000, 1000), (255, 0, 0)), (0, 1000))
        out = core.fit_image(img, (1000, 500), "cover")
        self.assertEqual(out.getpixel((500, 250)), (255, 0, 0))


class TestMosaiqueLente(unittest.TestCase):
    """Une image minuscule en mosaïque demandait des millions de collages."""

    def test_image_1px_sur_un_bureau_5760(self):
        depart = time.monotonic()
        out = core.fit_image(Image.new("RGB", (1, 1), (255, 0, 0)), (5760, 1080), "tile")
        self.assertEqual(out.size, (5760, 1080))
        self.assertEqual(out.getpixel((5759, 1079)), (255, 0, 0))
        self.assertLess(time.monotonic() - depart, 2.0)

    def test_le_motif_est_conserve(self):
        # Damier 2x2 : le motif doit se répéter à l'identique.
        img = Image.new("RGB", (2, 2))
        img.putpixel((0, 0), (255, 0, 0))
        img.putpixel((1, 0), (0, 255, 0))
        img.putpixel((0, 1), (0, 0, 255))
        img.putpixel((1, 1), (255, 255, 0))
        out = core.fit_image(img, (100, 100), "tile")
        for x, y in ((0, 0), (50, 50), (98, 98)):
            self.assertEqual(out.getpixel((x, y)), (255, 0, 0))
            self.assertEqual(out.getpixel((x + 1, y)), (0, 255, 0))


class TestCoordonneesNegatives(unittest.TestCase):
    """Un écran à gauche de l'origine était silencieusement perdu."""

    XRANDR = (
        "DP-1 connected primary 1920x1080+0+0 (normal left inverted right) 544mm x 303mm\n"
        "DP-2 connected 1920x1080+-1920+0 (normal left inverted right) 544mm x 303mm\n"
    )

    def test_les_deux_ecrans_sont_vus(self):
        mons = core.parse_xrandr(self.XRANDR)
        self.assertEqual(len(mons), 2)

    def test_origine_ramenee_a_zero(self):
        mons = core.parse_xrandr(self.XRANDR)
        self.assertEqual([m.x for m in mons], [0, 1920])
        self.assertEqual(core.desktop_size(mons), (3840, 1080))

    def test_composition_sur_les_deux_ecrans(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            gauche = Path(d) / "g.png"
            Image.new("RGB", (100, 100), (255, 0, 0)).save(gauche)
            mons = core.parse_xrandr(self.XRANDR)
            out = core.compose_per_monitor(
                mons, {"DP-2": {"path": str(gauche), "fit": "cover"}}, "#000000"
            )
            self.assertEqual(out.size, (3840, 1080))
            self.assertEqual(out.getpixel((960, 540)), (255, 0, 0))


class TestConfigInvalide(BaseIntegration):
    """Un config.json bricolé à la main empêchait l'application de démarrer."""

    def _ecrire(self, contenu: str) -> core.Config:
        core.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        core.CONFIG_PATH.write_text(contenu)
        return core.Config.load()

    def test_racine_qui_n_est_pas_un_objet(self):
        for contenu in ("[]", '"texte"', "42", "null"):
            with self.subTest(contenu=contenu):
                self.assertEqual(self._ecrire(contenu).mode, "per-monitor")

    def test_monitors_du_mauvais_type(self):
        for contenu in ('{"monitors": null}', '{"monitors": ["DP-2"]}',
                        '{"monitors": {"DP-2": "a.jpg"}}'):
            with self.subTest(contenu=contenu):
                cfg = self._ecrire(contenu)
                self.assertEqual(cfg.monitors, {})
                self.assertFalse(cfg.has_image())

    def test_span_du_mauvais_type(self):
        cfg = self._ecrire('{"span": null}')
        self.assertEqual(cfg.span, {"path": "", "fit": "cover", "library": ""})

    def test_valeurs_scalaires_du_mauvais_type(self):
        cfg = self._ecrire('{"background": 42, "mode": 7, "last_folder": []}')
        self.assertEqual(cfg.background, "#000000")
        self.assertEqual(cfg.mode, "per-monitor")
        self.assertEqual(cfg.last_folder, "")
        core.hex_to_rgb(cfg.background)  # ne doit pas lever

    def test_mode_d_ajustement_inconnu_corrige(self):
        cfg = self._ecrire('{"monitors": {"DP-1": {"path": "/a.png", "fit": "bidon"}}}')
        self.assertEqual(cfg.monitors["DP-1"]["fit"], "cover")


class TestSauvegardeConfig(BaseIntegration):
    def test_ecriture_atomique_sans_fichier_residuel(self):
        cfg = core.Config()
        cfg.monitors = {"DP-1": {"path": "/a.png", "fit": "cover"}}
        cfg.save()
        self.assertEqual(list(core.CONFIG_DIR.glob("*.tmp")), [])
        json.loads(core.CONFIG_PATH.read_text())  # JSON complet et valide

    def test_les_ecrans_sans_image_ne_sont_pas_persistes(self):
        """Sélectionner un écran dans la GUI ne doit pas laisser de trace."""
        cfg = core.Config()
        cfg.monitors = {
            "DP-1": {"path": "/a.png", "fit": "cover"},
            "DP-2": {"path": "", "fit": "cover"},  # simplement cliqué
        }
        cfg.save()
        self.assertEqual(list(core.Config.load().monitors), ["DP-1"])


class TestImageIllisible(BaseIntegration):
    """Une seule image corrompue vidait tout le composite, pas seulement son écran."""

    def test_les_autres_ecrans_sont_preserves(self):
        bonne = self.image_test("bonne.png", size=(1920, 1080), couleur=(0, 255, 0))
        cassee = self.root / "cassee.png"
        cassee.write_text("ceci n'est pas une image")

        out = core.compose_per_monitor(
            TROIS_ECRANS,
            {
                "DP-gauche": {"path": str(cassee), "fit": "cover"},
                "DP-centre": {"path": str(bonne), "fit": "cover"},
            },
            background="#000000",
        )
        self.assertEqual(out.size, (5760, 1080))
        self.assertEqual(out.getpixel((2880, 540)), (0, 255, 0), "l'écran valide survit")
        self.assertEqual(out.getpixel((960, 540)), (0, 0, 0), "l'écran fautif reste au fond")


class TestArgumentsCLI(BaseCLI):
    def test_nom_de_fichier_contenant_un_egal(self):
        img = self.image_test("photo=2.png", couleur=(1, 2, 3))
        code, _, err = self.run_cli("set", str(img))
        self.assertEqual(code, 0, err)
        self.assertEqual(core.Config.load().monitors["DP-gauche"]["path"], str(img))

    def test_melange_ciblage_et_positionnel_sans_ecrasement(self):
        a = self.image_test("a.png", couleur=(255, 0, 0))
        b = self.image_test("b.png", couleur=(0, 0, 255))
        code, _, err = self.run_cli("set", f"DP-gauche={a}", str(b))
        self.assertEqual(code, 0, err)
        monitors = core.Config.load().monitors
        self.assertEqual(monitors["DP-gauche"]["path"], str(a))
        self.assertNotIn(str(b), [monitors["DP-gauche"]["path"]])
        self.assertEqual(monitors["DP-centre"]["path"], str(b))

    def test_deux_images_pour_le_meme_ecran_refusees(self):
        a = self.image_test("a.png")
        b = self.image_test("b.png")
        code, _, err = self.run_cli("set", f"DP-gauche={a}", f"DP-gauche={b}")
        self.assertEqual(code, 1)
        self.assertIn("même écran", err)

    def test_export_sans_extension_connue(self):
        img = self.image_test("a.png")
        self.run_cli("set", f"DP-gauche={img}")
        code, _, err = self.run_cli("export", str(self.root / "sortie"))
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)

    def test_export_sans_config(self):
        code, _, err = self.run_cli("export", str(self.root / "sortie.png"))
        self.assertEqual(code, 1)
        self.assertIn("Aucune image", err)


if __name__ == "__main__":
    unittest.main()
