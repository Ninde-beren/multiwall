# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Recherche de photos panoramiques sur Wikimedia Commons, via son API.

Pourquoi Commons plutôt qu'une banque de fonds d'écran :

* licences explicites (CC), auteur et page source fournis par l'API ;
* pas de clé d'API à obtenir, donc rien à configurer ;
* redimensionnement côté serveur : on récupère une image déjà à la bonne
  largeur au lieu de tirer un original de 15 Mo.

Wallhaven a un meilleur fonds spécifiquement « multi-écrans », mais ses filtres
de ratio se sont révélés incohérents et il renvoie des listes vides sous
rate-limiting ; ses images n'ont par ailleurs pas de licence garantie.

L'API de Wikimedia impose un User-Agent identifiant et un usage modéré : les
appels sont donc espacés, et un HTTP 429 déclenche une attente croissante.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import CONTACT, __version__
from . import core

API = "https://commons.wikimedia.org/w/api.php"
#: La politique d'accès de Wikimedia demande un User-Agent identifiant l'outil
#: et un moyen de contact — une URL convient, et évite d'exposer une adresse.
USER_AGENT = f"MultiWall/{__version__} (+{CONTACT})"

#: Cache des photos téléchargées.
CACHE = core.DATA_DIR / "photos"

#: Délai minimal entre deux accès réseau, par politesse envers Wikimedia.
#: S'applique aussi aux vignettes : sans cela, une poignée d'aperçus enchaînés
#: épuise le quota et le téléchargement qui suit est refusé. Mesuré : à cette
#: cadence les requêtes passent, et le quota se recharge en moins d'une minute.
DELAI_MINIMAL = 1.2
_dernier_appel = 0.0
_verrou_reseau = threading.Lock()  # les vignettes sont chargées depuis un thread


def _lire(url: str, timeout: int = 20, tentatives: int = 3,
          delai: float | None = None) -> bytes:
    """Lecture réseau unique : throttlée, avec attente croissante sur 429.

    Tous les accès passent par ici — API, vignettes et téléchargements — sinon
    le compteur de Wikimedia est atteint sans que le throttling s'en aperçoive.
    """
    global _dernier_appel
    delai = DELAI_MINIMAL if delai is None else delai
    requete = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    attente = 1.5
    for essai in range(tentatives):
        with _verrou_reseau:
            depuis = time.monotonic() - _dernier_appel
            if depuis < delai:
                time.sleep(delai - depuis)
            _dernier_appel = time.monotonic()
        try:
            with urllib.request.urlopen(requete, timeout=timeout) as reponse:
                return reponse.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and essai < tentatives - 1:
                time.sleep(attente)
                attente *= 2
                continue
            if exc.code == 429:
                raise ReseauIndisponible(
                    "Wikimedia limite temporairement les requêtes. "
                    "Patientez quelques secondes avant de réessayer."
                ) from exc
            raise ReseauIndisponible(f"Wikimedia a répondu HTTP {exc.code}.") from exc
        except (urllib.error.URLError, OSError) as exc:
            if essai < tentatives - 1:
                time.sleep(attente)
                attente *= 2
                continue
            raise ReseauIndisponible(
                "Impossible de joindre Wikimedia Commons — vérifiez votre connexion."
            ) from exc
    raise ReseauIndisponible("Wikimedia Commons est injoignable.")

#: Thèmes proposés par défaut, sans que l'utilisateur ait à chercher.
THEMES = (
    ("Montagnes", "panorama mountain landscape"),
    ("Côtes", "panorama coast sea"),
    ("Villes", "panorama city skyline"),
    ("Déserts", "panorama desert dunes"),
    ("Forêts", "panorama forest valley"),
    ("Lacs", "panorama lake reflection"),
    ("Ciel nocturne", "panorama night sky stars"),
    ("Campagne", "panorama countryside fields"),
)


class ReseauIndisponible(RuntimeError):
    """Pas de connexion, ou service injoignable."""


@dataclass(frozen=True)
class Photo:
    titre: str
    largeur: int
    hauteur: int
    url_vignette: str
    url_page: str
    licence: str
    auteur: str
    source: str = "commons"

    @property
    def ratio(self) -> float:
        return self.largeur / self.hauteur if self.hauteur else 0.0

    @property
    def nom(self) -> str:
        """Titre lisible : sans le préfixe « File: » ni l'extension."""
        titre = re.sub(r"^File:", "", self.titre)
        return re.sub(r"\.(jpe?g|png|tiff?|webp)$", "", titre, flags=re.I).replace("_", " ")

    @property
    def cle(self) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "-", self.titre)[:80].strip("-").lower()


def _nettoyer_html(valeur: str) -> str:
    """Les métadonnées de Commons contiennent du HTML (liens vers l'auteur)."""
    texte = re.sub(r"<[^>]+>", "", valeur or "")
    texte = texte.replace("&amp;", "&").replace("&nbsp;", " ").replace("&#160;", " ")
    return " ".join(texte.split())


def _appeler(params: dict, tentatives: int = 3) -> dict:
    """Appel de l'API, throttlé comme tous les accès réseau."""
    donnees = _lire(f"{API}?{urllib.parse.urlencode(params)}", timeout=15,
                    tentatives=tentatives)
    try:
        return json.loads(donnees.decode())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ReseauIndisponible("Réponse illisible de Wikimedia Commons.") from exc


def _rechercher_commons(terme: str, ratio_cible: float, limite: int = 40,
                        tolerance: float = 0.32, largeur_min: int = 2500) -> list[Photo]:
    """Photos dont le ratio approche celui du bureau.

    Commons ne sait pas filtrer sur le ratio : on demande large et on trie ici.
    """
    donnees = _appeler({
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"filetype:bitmap {terme}", "gsrlimit": limite,
        "gsrnamespace": 6, "prop": "imageinfo",
        "iiprop": "url|size|extmetadata", "iiurlwidth": 480,
    })
    pages = (donnees.get("query") or {}).get("pages") or {}

    resultats = []
    for page in pages.values():
        infos = (page.get("imageinfo") or [{}])[0]
        largeur, hauteur = infos.get("width", 0), infos.get("height", 0)
        if not hauteur or largeur < largeur_min:
            continue
        ratio = largeur / hauteur
        if ratio_cible and abs(ratio - ratio_cible) / ratio_cible > tolerance:
            continue
        meta = infos.get("extmetadata") or {}
        resultats.append(Photo(
            titre=page.get("title", ""),
            largeur=largeur,
            hauteur=hauteur,
            url_vignette=infos.get("thumburl") or infos.get("url", ""),
            url_page=infos.get("descriptionurl", ""),
            licence=_nettoyer_html(meta.get("LicenseShortName", {}).get("value", "")) or "?",
            auteur=_nettoyer_html(meta.get("Artist", {}).get("value", "")) or "inconnu",
            source="commons",
        ))
    # Les plus proches du ratio du bureau d'abord : moins de recadrage.
    resultats.sort(key=lambda p: abs(p.ratio - ratio_cible) if ratio_cible else 0)
    return resultats


@dataclass(frozen=True)
class Source:
    id: str
    nom: str
    rechercher: object
    themes: tuple
    delai: float
    note: str


#: Sources de photos. Le registre reste ouvert : en ajouter une revient à
#: écrire sa fonction de recherche et une entrée ici.
SOURCES: dict[str, Source] = {
    "commons": Source(
        id="commons", nom="Wikimedia Commons", rechercher=_rechercher_commons,
        themes=THEMES, delai=DELAI_MINIMAL,
        note="Photographies sous licence Creative Commons. Recherches en anglais.",
    ),
}


def rechercher(terme: str, ratio_cible: float, source: str = "commons",
               limite: int = 40, tolerance: float = 0.32,
               largeur_min: int = 2500) -> list[Photo]:
    """Recherche dans la source demandée."""
    if source not in SOURCES:
        raise ValueError(f"Source inconnue : {source} "
                         f"(disponibles : {', '.join(SOURCES)})")
    return SOURCES[source].rechercher(terme, ratio_cible, limite, tolerance, largeur_min)


def _telecharger(url: str, destination: Path) -> Path:
    donnees = _lire(url, timeout=90, tentatives=4)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporaire = destination.with_suffix(destination.suffix + ".part")
    temporaire.write_bytes(donnees)
    os.replace(temporaire, destination)  # jamais de fichier à moitié écrit
    return destination


def url_a_la_largeur(photo: Photo, largeur: int) -> str:
    """URL de la photo à la largeur voulue, obtenue via l'API.

    Commons n'accepte qu'une liste fermée de largeurs de vignettes : fabriquer
    l'URL à la main donne un HTTP 400 (« Use thumbnail sizes listed on… »).
    C'est l'API qui doit produire l'URL — elle accepte n'importe quelle largeur
    et renvoie un lien valide, redimensionné côté serveur.
    """
    largeur = max(min(largeur, photo.largeur), 1)
    donnees = _appeler({
        "action": "query", "format": "json", "titles": photo.titre,
        "prop": "imageinfo", "iiprop": "url|size", "iiurlwidth": largeur,
    })
    pages = (donnees.get("query") or {}).get("pages") or {}
    for page in pages.values():
        infos = (page.get("imageinfo") or [{}])[0]
        url = infos.get("thumburl") or infos.get("url")
        if url:
            return url.split("?")[0]  # sans les paramètres de suivi
    raise ReseauIndisponible(f"Image introuvable sur Commons : {photo.nom}")


def obtenir(photo: Photo, largeur: int) -> Path:
    """Récupère la photo à la largeur voulue et renvoie son chemin local."""
    destination = CACHE / f"{photo.source}-{photo.cle}-{largeur}.jpg"
    if destination.is_file() and destination.stat().st_size > 0:
        return destination  # déjà en cache

    return _telecharger(url_a_la_largeur(photo, largeur), destination)


def telecharger_vignette(photo: Photo) -> bytes:
    """Octets de la vignette d'aperçu (URL fournie par la recherche)."""
    return _lire(photo.url_vignette.split("?")[0], timeout=20,
                 delai=SOURCES[photo.source].delai)


def purger(garder: int = 12) -> None:
    """Ne conserve que les photos les plus récemment récupérées."""
    if not CACHE.is_dir():
        return
    fichiers = []
    for chemin in CACHE.glob("*.jpg"):
        try:
            fichiers.append((chemin.stat().st_mtime, chemin))
        except OSError:
            continue
    fichiers.sort(reverse=True)
    for _, chemin in fichiers[garder:]:
        try:
            chemin.unlink()
        except OSError:
            pass
