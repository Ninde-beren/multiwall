<div align="center">

<img src="multiwall/data/logo.svg" width="96" alt="MultiWall">

# MultiWall

**Un fond d'écran différent sur chaque moniteur, ou une image panoramique unique étalée sur tous les écrans.**

Application de bureau GTK 3 pour Linux · Python, sans dépendance à installer

[![Licence : PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/licence-PolyForm%20Noncommercial%201.0.0-0b7285)](LICENSE)
[![Tests : 253](https://img.shields.io/badge/tests-263%20✓-2b8a3e)](tests/)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-offrir%20un%20café-ff5e5b?logo=ko-fi&logoColor=white)](https://ko-fi.com/sigilbo)

</div>

---

## Le problème

GNOME et les bureaux qui en dérivent ne savent poser qu'**un seul** fond d'écran, répété
à l'identique sur chaque moniteur. Impossible d'affecter une image par écran, ni
d'étaler proprement un panorama 5760×1080 sur trois écrans.

## La solution

Sous X11, les écrans ne forment qu'**une seule surface** — trois moniteurs 1920×1080
côte à côte, c'est un bureau de 5760×1080. MultiWall compose donc une image unique à
cette taille et l'installe avec `picture-options = spanned`, ce qui la répartit pixel
pour pixel sur l'ensemble.

Un fond différent par écran revient alors à coller chaque image à la bonne position
dans ce grand canevas, d'après la géométrie réelle renvoyée par `xrandr`.

## Fonctionnalités

- **Une image par écran**, avec six modes d'ajustement indépendants
- **Image panoramique** étalée sur l'ensemble du bureau
- **Bibliothèque** en trois onglets : fonds générés, photos en ligne, vos propres images
- **Détection à chaud** des branchements et débranchements d'écrans
- **Aperçu interactif** reproduisant la disposition réelle : clic, double-clic,
  glisser-déposer, navigation au clavier
- **Ligne de commande** complète, pour un raccourci clavier ou une tâche planifiée
- **Guide d'utilisation intégré** (`F1`) et **diagnostic d'environnement**

### Modes d'ajustement

| Mode | Effet |
|------|-------|
| `cover` | Remplit l'écran, recadrage centré (défaut) |
| `contain` | Image entière, bandes de la couleur de fond |
| `blur` | Image entière sur un fond flouté tiré de l'image elle-même |
| `stretch` | Étire l'image, sans respecter les proportions |
| `center` | Taille réelle, centrée |
| `tile` | Répétition en mosaïque |

### Bibliothèque

**Fonds générés** — dix fonds panoramiques calculés localement, sans aucun fichier sur
disque : une entrée est une *recette* (style, palette, graine) recalculée à la
résolution exacte du bureau. Un changement d'écrans les régénère au lieu de les
redimensionner. Quatre styles procéduraux en Pillow pur, cinq palettes. Les éléments
focaux (un astre, un sommet) sont posés au centre d'un écran, jamais sur la bordure
entre deux moniteurs.

**Photos en ligne** — recherche sur [Wikimedia Commons](https://commons.wikimedia.org),
sans quitter l'application. Conformément à la politique d'accès de Wikimedia, les
requêtes portent un User-Agent identifiant l'application et son auteur. Seules les photos dont le format approche celui du bureau
sont proposées, triées par proximité de ratio. Licence et auteur sont affichés sous
chaque vignette ; les images restent la propriété de leurs auteurs.

**Mes fonds** — les images déjà utilisées au moins une fois, la plus récente en tête.
Une image déplacée ou supprimée disparaît d'elle-même de la liste.

## Compatibilité

Ce qui compte n'est pas la distribution, mais **l'environnement de bureau** : MultiWall
pilote `org.gnome.desktop.background`.

| | |
|---|---|
| ✅ **Fonctionne** | GNOME, Budgie, Cinnamon, MATE, Unity, Pantheon — sur n'importe quelle distribution |
| ❌ **Ne fonctionne pas** | KDE Plasma, XFCE, LXQt, i3, Sway — ils gèrent leur fond autrement |
| ⚠️ **Non vérifié** | Wayland : le repli sans `xrandr` est implémenté, mais le mode « étalé » dépend du compositeur |

Validé sur Ubuntu 24.04 / Budgie / X11 avec trois écrans 1920×1080. Debian, Fedora et
Arch avec un bureau de la liste devraient fonctionner à l'identique — les paquets y
portent les mêmes noms.

**Versions minimales** : Python 3.7, GTK 3.20, Pillow 6.0 (recommandé — sans lui,
l'orientation EXIF des photos est ignorée).

En cas de doute, l'application se diagnostique elle-même :

```bash
multiwall doctor          # vérifie l'environnement, ne modifie rien
multiwall doctor --gui    # même chose, dans une fenêtre
multiwall doctor --mire   # applique une mire de contrôle, puis restaure le fond
```

L'application se contrôle aussi elle-même **au démarrage** : si l'environnement ne
permet pas de poser un fond d'écran, une fenêtre l'explique au lieu de laisser croire à
une panne. Le diagnostic est accessible à tout moment par `Ctrl+D`, avec un bouton
« Copier le rapport » à joindre à un signalement.

`doctor` renvoie `0` si l'environnement est supporté, `1` sinon — utilisable dans un
script d'installation.

## Installation

Les dépendances sont présentes par défaut sur tout bureau GNOME. Au besoin :

```bash
# Debian / Ubuntu
sudo apt install python3-gi gir1.2-gtk-3.0 python3-pil libglib2.0-bin x11-xserver-utils

# Fedora
sudo dnf install python3-gobject gtk3 python3-pillow glib2 xrandr

# Arch
sudo pacman -S python-gobject gtk3 python-pillow glib2 xorg-xrandr
```

### Paquet Debian / Ubuntu

```bash
sudo apt install ./multiwall_1.0.0_all.deb
```

Le `.deb` déclare ses dépendances, installe la page de manuel et l'icône, et se retire
proprement avec `sudo apt remove multiwall`. Pour le construire depuis les sources :
`./build-deb.sh` (nécessite `dpkg-deb` et `fakeroot`, présents par défaut).

### Installation utilisateur, sans paquet

```bash
git clone https://github.com/Ninde-beren/multiwall.git
cd multiwall
./install.sh                # commande `multiwall` + entrée dans le menu + icône
./install.sh --autostart    # + réapplication à l'ouverture de session
```

Cette variante ne touche qu'à votre dossier personnel (`~/.local/bin`,
`~/.local/share/applications`, `~/.local/share/icons`). Aucun `sudo`, aucun paquet
Python à installer.

Pour désinstaller : supprimer ces trois fichiers, plus `~/.config/multiwall` et
`~/.local/share/multiwall`.

## Interface graphique

```bash
multiwall
```

L'aperçu reproduit la disposition réelle de vos écrans.

- **Clic** : sélectionner un écran · **double-clic** : choisir son image · **clic
  droit** : menu contextuel
- **Glisser-déposer** une image sur un écran ; en déposer plusieurs les répartit sur
  les écrans suivants
- La configuration est enregistrée à la fermeture, même sans avoir appliqué
- La composition tourne dans un thread : la fenêtre reste réactive

### Raccourcis clavier

| Raccourci | Action |
|---|---|
| `←` `→` `1`–`9` | Changer d'écran dans l'aperçu |
| `Entrée` | Choisir l'image de l'écran sélectionné |
| `Suppr` | Effacer l'image de l'écran |
| `Ctrl+O` | Choisir une image |
| `Ctrl+Entrée` ou `Ctrl+S` | Appliquer |
| `Ctrl+1` / `Ctrl+2` | Mode par écran / panoramique |
| `Ctrl+L` | Bibliothèque |
| `Ctrl+P` | Bibliothèque, onglet « Photos en ligne » |
| `Ctrl+R` | Nouveau tirage aléatoire |
| `Ctrl+E` | Exporter le composite |
| `F1` | Guide d'utilisation |
| `Ctrl+?` | Fenêtre des raccourcis |
| `Ctrl+D` | Vérifier la compatibilité |
| `F5` | Redétecter les écrans |

## Ligne de commande

```bash
multiwall list                                   # écrans détectés
multiwall set gauche.jpg centre.jpg droite.jpg   # une image par écran
multiwall set DP-1=a.jpg --fit blur              # en ciblant une sortie par son nom
multiwall span pano-5760x1080.jpg                # une image sur tous les écrans
multiwall library                                # fonds générés disponibles
multiwall library dunes                          # applique « Dunes »
multiwall photos "coast"                         # cherche des photos panoramiques
multiwall photos "coast" --use 2                 # applique la 2e de la liste
multiwall random ~/Images/Fonds                  # tirage au sort
multiwall apply                                  # réapplique la dernière configuration
multiwall export ~/Images/bureau.png             # enregistre le composite
multiwall doctor                                 # diagnostic de l'environnement
```

Options : `--fit` (cover, contain, blur, stretch, center, tile), `--background '#101010'`,
`--span` pour `random`.

### Changer de fond automatiquement

```bash
systemd-run --user --on-calendar=hourly multiwall random ~/Images/Fonds
```

## Tests

```bash
./run-tests.sh          # 263 tests, ~16 s
./run-tests.sh -v       # détail test par test
```

`unittest` de la bibliothèque standard, rien à installer. Les tests **ne touchent jamais
au vrai bureau ni au réseau** : `gsettings` est remplacé par un script factice placé en
tête du `PATH`, l'API distante et les téléchargements sont simulés, et les chemins de
configuration sont redirigés vers un dossier temporaire. Les tests d'interface
construisent la fenêtre GTK sans l'afficher, et sont ignorés automatiquement sans
serveur graphique.

## Architecture

| Fichier | Rôle |
|---|---|
| `multiwall/core.py` | Détection des écrans, ajustement, composition, application via `gsettings` |
| `multiwall/gui.py` | Fenêtre principale et aperçu interactif |
| `multiwall/windows.py` | Bibliothèque (trois onglets) et guide d'utilisation |
| `multiwall/library.py` | Fonds panoramiques procéduraux |
| `multiwall/photos.py` | Recherche Wikimedia Commons (throttling, cache) |
| `multiwall/doctor.py` | Diagnostic de l'environnement |
| `multiwall/cli.py` | Commandes en ligne |

Données : `~/.config/multiwall/config.json` · composites et photos en cache dans
`~/.local/share/multiwall/`.

## Limites connues

- Conçu pour **X11**. Sous Wayland, la détection retombe sur GDK mais le mode « étalé »
  n'est pas garanti selon le compositeur.
- Le composite est un PNG de la taille du bureau (~10 Mo en 5760×1080), régénéré à
  chaque application ; seuls les deux derniers sont conservés.
- Les recherches de photos se font **en anglais** — c'est ainsi que Commons est indexé.
- Peu de photos existent exactement au format 48:9, d'où un recadrage en mode
  « remplir ».
- La compensation des bordures d'écran (*bezel*) n'est pas implémentée : en panoramique,
  le sujet est coupé par les cadres physiques des moniteurs.

## Contribuer

Les contributions sont les bienvenues : correctifs, nouveaux styles de fonds, prise en
charge d'autres bureaux, test sous Wayland.

Avant de proposer un changement, lancez `./run-tests.sh` — la suite doit rester verte,
et tout comportement corrigé mérite son test de non-régression.

## Licence

`SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0`

[PolyForm Noncommercial 1.0.0](LICENSE) — usage, modification et redistribution libres
**à des fins non commerciales**. Cela couvre l'usage personnel, les projets amateurs,
l'enseignement, la recherche publique et les associations.

Tout usage commercial requiert l'accord préalable de Sigilbo : contactez-moi via
[LinkedIn](https://www.linkedin.com/in/antoine-obligis/), une licence adaptée peut être
accordée.

Ce n'est pas une licence open source au sens de l'OSI : le code est public, modifiable
et ouvert aux contributions, mais son exploitation commerciale reste réservée.

## Soutenir le projet

MultiWall est développé et maintenu sur mon temps libre, et reste gratuit pour tout
usage non commercial. Si l'application vous est utile, vous pouvez m'offrir un café :

**[ko-fi.com/sigilbo](https://ko-fi.com/sigilbo)**

## Contact

**Sigilbo** — [Antoine Obligis sur LinkedIn](https://www.linkedin.com/in/antoine-obligis/)

© 2026 **Sigilbo**
