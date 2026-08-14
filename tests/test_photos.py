# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Tests de la recherche de photos en ligne.

Aucun test ne sort sur le réseau : l'API et les téléchargements sont simulés.
Une suite qui dépend d'Internet est lente et échoue pour de mauvaises raisons.
"""

import unittest
import urllib.error

from multiwall import core, photos
from support import BaseIntegration
from test_cli import BaseCLI


def page(titre, largeur, hauteur, licence="CC BY-SA 4.0", auteur="Jane Doe"):
    return {
        "title": titre,
        "imageinfo": [{
            "width": largeur, "height": hauteur,
            "thumburl": f"https://exemple/thumb/500px-{titre}?utm_source=x",
            "descriptionurl": f"https://commons.wikimedia.org/wiki/{titre}",
            "extmetadata": {
                "LicenseShortName": {"value": licence},
                "Artist": {"value": f'<a href="//u/x" title="User:X">{auteur}</a>'},
            },
        }],
    }


REPONSE = {"query": {"pages": {
    "1": page("File:Panorama_A.jpg", 11000, 2062),   # ratio 5.33 — pile 3 écrans
    "2": page("File:Panorama_B.jpg", 8000, 1600),    # ratio 5.00 — proche
    "3": page("File:Portrait.jpg", 3000, 4000),      # ratio 0.75 — à écarter
    "4": page("File:Standard.jpg", 4000, 3000),      # ratio 1.33 — à écarter
    "5": page("File:Petit_pano.jpg", 900, 170),      # bon ratio mais trop petit
}}}


class BasePhotos(BaseIntegration):
    """Remplace les accès réseau par des doublures."""

    def setUp(self):
        super().setUp()
        photos.CACHE = self.root / "photos"
        self.appels = []
        self._appeler = photos._appeler
        photos._appeler = self._faux_appeler

    def tearDown(self):
        photos._appeler = self._appeler
        super().tearDown()

    def _faux_appeler(self, params, tentatives=3):
        self.appels.append(params)
        if params.get("generator") == "search":
            return REPONSE
        return {"query": {"pages": {"1": {"imageinfo": [
            {"thumburl": f"https://exemple/{params.get('iiurlwidth')}px-x.jpg?utm=1"}
        ]}}}}


class TestRecherche(BasePhotos):
    RATIO_3 = 5760 / 1080

    def test_ne_garde_que_les_formats_proches_du_bureau(self):
        res = photos.rechercher("test", self.RATIO_3)
        noms = [p.nom for p in res]
        self.assertIn("Panorama A", noms)
        self.assertNotIn("Portrait", noms)
        self.assertNotIn("Standard", noms)

    def test_ecarte_les_images_trop_petites(self):
        """Une image de 900 px de large ne remplira pas un bureau de 5760."""
        self.assertNotIn("Petit pano", [p.nom for p in photos.rechercher("t", self.RATIO_3)])

    def test_les_plus_proches_du_ratio_d_abord(self):
        res = photos.rechercher("test", self.RATIO_3)
        self.assertEqual(res[0].nom, "Panorama A", "5.33 avant 5.00")

    def test_ratio_deux_ecrans(self):
        """Le même corpus doit donner d'autres résultats pour un bureau 32:9."""
        res = photos.rechercher("test", 3840 / 1080, tolerance=0.32)
        self.assertEqual(res, [], "aucune de ces images n'est au format 2 écrans")

    def test_metadonnees_nettoyees_du_html(self):
        photo = photos.rechercher("test", self.RATIO_3)[0]
        self.assertEqual(photo.auteur, "Jane Doe")
        self.assertEqual(photo.licence, "CC BY-SA 4.0")
        self.assertTrue(photo.url_page.startswith("https://commons.wikimedia.org/"))

    def test_nom_lisible(self):
        photo = photos.rechercher("test", self.RATIO_3)[0]
        self.assertEqual(photo.nom, "Panorama A", "sans « File: » ni extension")

    def test_la_recherche_est_transmise_a_l_api(self):
        photos.rechercher("mountain lake", self.RATIO_3)
        self.assertIn("mountain lake", self.appels[0]["gsrsearch"])
        self.assertEqual(self.appels[0]["gsrnamespace"], 6)

    def test_reponse_vide_ou_malformee(self):
        photos._appeler = lambda p, tentatives=3: {}
        self.assertEqual(photos.rechercher("t", self.RATIO_3), [])


class TestTelechargement(BasePhotos):
    def setUp(self):
        super().setUp()
        self.telecharges = []
        photos._telecharger = self._faux_telecharger

    def _faux_telecharger(self, url, destination):
        self.telecharges.append(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"jpeg-simule")
        return destination

    def test_l_url_est_demandee_a_l_api_pas_fabriquee(self):
        """Commons rejette (HTTP 400) les largeurs qu'il n'a pas prévues :
        seule l'API sait produire une URL valide."""
        photo = photos.rechercher("t", 5760 / 1080)[0]
        photos.obtenir(photo, 5760)
        self.assertTrue(any(a.get("iiurlwidth") == 5760 for a in self.appels))
        self.assertNotIn("utm", self.telecharges[0], "paramètres de suivi retirés")

    def test_la_largeur_ne_depasse_pas_l_original(self):
        photo = photos.rechercher("t", 5760 / 1080)[0]
        photos.obtenir(photo, 99999)
        largeurs = [a.get("iiurlwidth") for a in self.appels if "iiurlwidth" in a]
        self.assertEqual(max(largeurs), photo.largeur)

    def test_le_cache_evite_un_second_telechargement(self):
        photo = photos.rechercher("t", 5760 / 1080)[0]
        premier = photos.obtenir(photo, 2000)
        self.telecharges.clear()
        self.assertEqual(photos.obtenir(photo, 2000), premier)
        self.assertEqual(self.telecharges, [], "le fichier était déjà en cache")

    def test_la_purge_conserve_les_plus_recents(self):
        photos.CACHE.mkdir(parents=True, exist_ok=True)
        for i in range(20):
            (photos.CACHE / f"p{i}.jpg").write_bytes(b"x")
        photos.purger(garder=5)
        self.assertEqual(len(list(photos.CACHE.glob("*.jpg"))), 5)

    def test_purge_sans_cache(self):
        photos.purger()  # ne doit pas lever si le dossier n'existe pas


class TestErreursReseau(BaseIntegration):
    def setUp(self):
        super().setUp()
        photos.CACHE = self.root / "photos"
        photos.DELAI_MINIMAL = 0  # pas d'attente en test

    def test_pas_de_connexion(self):
        def echec(*_a, **_k):
            raise urllib.error.URLError("nom de domaine introuvable")

        original = photos.urllib.request.urlopen
        photos.urllib.request.urlopen = echec
        try:
            with self.assertRaises(photos.ReseauIndisponible) as ctx:
                photos._appeler({"action": "query"}, tentatives=1)
            self.assertIn("connexion", str(ctx.exception).lower())
        finally:
            photos.urllib.request.urlopen = original

    def test_erreur_http_est_traduite(self):
        def refus(*_a, **_k):
            raise urllib.error.HTTPError("url", 500, "Server Error", {}, None)

        original = photos.urllib.request.urlopen
        photos.urllib.request.urlopen = refus
        try:
            with self.assertRaises(photos.ReseauIndisponible) as ctx:
                photos._appeler({"action": "query"}, tentatives=1)
            self.assertIn("500", str(ctx.exception))
        finally:
            photos.urllib.request.urlopen = original

    def test_le_429_est_retente(self):
        etat = {"appels": 0}

        class Reponse:
            def read(self):
                return b'{"query": {"pages": {}}}'

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        def parfois(*_a, **_k):
            etat["appels"] += 1
            if etat["appels"] == 1:
                raise urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
            return Reponse()

        original = photos.urllib.request.urlopen
        photos.urllib.request.urlopen = parfois
        try:
            self.assertEqual(photos._appeler({"action": "query"}), {"query": {"pages": {}}})
            self.assertEqual(etat["appels"], 2, "une seconde tentative doit avoir lieu")
        finally:
            photos.urllib.request.urlopen = original


class TestCommandePhotos(BaseCLI):
    def setUp(self):
        super().setUp()
        photos.CACHE = self.root / "photos"
        self._appeler = photos._appeler
        self._telecharger = photos._telecharger
        photos._appeler = lambda p, tentatives=3: (
            REPONSE if p.get("generator") == "search"
            else {"query": {"pages": {"1": {"imageinfo": [{"thumburl": "https://x/y.jpg"}]}}}}
        )

        def faux_telecharger(url, destination):
            from PIL import Image

            destination.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (4000, 750), (12, 34, 56)).save(destination)
            return destination

        photos._telecharger = faux_telecharger

    def tearDown(self):
        photos._appeler = self._appeler
        photos._telecharger = self._telecharger
        super().tearDown()

    def test_la_liste_affiche_licence_et_format(self):
        code, out, err = self.run_cli("photos", "montagne")
        self.assertEqual(code, 0, err)
        self.assertIn("Panorama A", out)
        self.assertIn("CC BY-SA 4.0", out)
        self.assertIn("5760x1080", out)

    def test_appliquer_une_photo(self):
        code, out, err = self.run_cli("photos", "montagne", "--use", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("Panorama A", out)
        self.assertIn("CC BY-SA 4.0", out, "l'auteur et la licence doivent être rappelés")
        self.assertEqual(self.valeur_definie("picture-options"), "spanned")

        cfg = core.Config.load()
        self.assertEqual(cfg.mode, "span")
        self.assertTrue(cfg.span["path"].endswith(".jpg"))

    def test_numero_hors_liste(self):
        code, _, err = self.run_cli("photos", "montagne", "--use", "99")
        self.assertEqual(code, 1)
        self.assertIn("hors liste", err)
        self.assertNotIn("Traceback", err)

    def test_aucun_resultat(self):
        photos._appeler = lambda p, tentatives=3: {"query": {"pages": {}}}
        code, _, err = self.run_cli("photos", "xyzzy")
        self.assertEqual(code, 1)
        self.assertIn("Aucune photo", err)

    def test_reseau_indisponible_reste_lisible(self):
        def coupe(*_a, **_k):
            raise photos.ReseauIndisponible("Impossible de joindre Wikimedia Commons.")

        photos._appeler = coupe
        code, _, err = self.run_cli("photos", "montagne")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        self.assertIn("Commons", err)


if __name__ == "__main__":
    unittest.main()
