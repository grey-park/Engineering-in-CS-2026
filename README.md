# TapServe : objectifs de rating.

| # | Objectif | Points |
|---|---|---|
| 1 | Boîtier rechargeable avec boutons et LED fonctionnel | 3 |
| 2 | Routeur (broker MQTT) fonctionnel | 2 |
| 3 | Communication entre boîtier et routeur en local | 3 |
| 4 | Mise en place de Devices / Montres MQTT | 2 |
| 5 | Envoi et transmission sur montre / autres Devices | 3 |
| 6 | Micro fonctionnel sur boîtier | 3 |
| 7 | Interprétation Speech to Text sur le serveur | 2 |
| 8 | Tableau de bord administrateur | 3 |
| 9 | Démo fonctionnelle | 4 |
| | **Total** | **25** |

## Bonus

| # | Objectif | Points |
|---|---|---|
| B1 | Modèle local pour résumer la demande sur le routeur | 2 |
| B2 | Test du produit dans un bar | 3 |
| B3 | Application Android pour les tablettes cuisine et le rendu gérant | 3 |
| | **Total bonus** | **8** |


# TapServe : liste de matériel et coûts (magasins suisses)

Prix suissse estimation

## Matériel par boîtier (× 3)

| Élément | Qté | Magasin | Prix unitaire (CHF) | Total par boîtier (CHF) | Remarque |
|---|---|---|---|---|---|
| Bouton arcade lumineux, perçage 24 mm, LED 5–12 V | 3 | Bastelgarage | 4.90 (v) | 14.70 | Déjà en main |
| Microphone I2S | 1 | Bastelgarage | 8.90 (v) | 8.90 | |
| ESP32-C3 SuperMini | 1 | — | — | — | Déjà en main, pas vendu en Suisse |
| Batterie LiPo 3,7 V 2000 mAh (JST 1.25) | 1 | Bastelgarage | 13.90 (v) | 13.90 | En rupture, vérifier la polarité |
| Module de charge TP4056 USB-C avec protection | 1 | Digitec | 10.90 (v) | 10.90 | |
| Interrupteur marche/arrêt à glissière | 1 | — | ≈ 0.50 | ≈ 0.50 | |
| MOSFET AO3400 et résistances (LED des boutons) | 3 | — | ≈ 0.30 | ≈ 1.00 | |
| Résistances 100 kΩ (mesure de la batterie) | 2 | — | ≈ 0.10 | ≈ 0.20 | |
| Vis M3 × 10 auto-taraudeuses et patins antidérapants | 4 + 4 | — | — | ≈ 2.00 | |
| Coque et fond imprimés en 3D (PLA, environ 60 g) | 1 | — | — | ≈ 2.00 | |
| Convertisseur 5 V (MT3608) | 1 | — | ≈ 2.00 | ≈ 2.00 | LED des boutons en 5 V (batterie 3,7 V) |
| **À acheter par boîtier** | | | | **≈ 42** | Sans les boutons ni la SuperMini |
| **À acheter pour 3 boîtiers** | | | | **≈ 125** | |

## Récepteur montre

| Élément | Qté | Magasin | Prix unitaire (CHF) | Total (CHF) | Remarque |
|---|---|---|---|---|---|
| LilyGO T-Watch S3 | 2 | LilyGO / AliExpress (import) | ≈ 40–50 | ≈ 80–100 | Pas vendue en Suisse, 43 USD pièce, en rupture chez LilyGO |
| Câbles USB-C (charge et programmation) | 3 | — | ≈ 5–8 | ≈ 15–25 | |

## Récepteur admin

| Élément | Qté | Prix (CHF) | Remarque |
|---|---|---|---|
| Ordinateur portable (serveur et tableau de bord du gérant) | 1 | 0 | Déjà en main |

## Routeur / broker

| Élément | Qté | Magasin | Prix (CHF) | Remarque |
|---|---|---|---|---|
| Raspberry Pi 5, 8 Go | 1 | Galaxus | ≈ 135 | 8 Go nécessaires pour le speech to text et le modèle local |
| Alimentation officielle Raspberry Pi 27 W USB-C | 1 | — | ≈ 15 | |
| Carte microSD 32 Go | 1 | — | ≈ 12 | |
| Boîtier imprimé en 3D | 1 | — | ≈ 2 | |
| **Total** | | | **≈ 165** | |

## Récapitulatif

| Poste | Total (CHF) |
|---|---|
| 3 boîtiers (à acheter) | ≈ 125 |
| Récepteur montre | ≈ 95–125 |
| Récepteur admin | 0 |
| Routeur / broker | ≈ 165 |
| **Total à acheter** | **≈ 385–415** |


## Sources

- [Galaxus – Raspberry Pi 5 2GB](https://www.galaxus.ch/en/s1/product/raspberry-pi-5-2gb-single-board-computer-kits-47872500)
- [Bastelgarage – Arcade Taster beleuchtet 33mm](https://www.bastelgarage.ch/arcade-taster-button-beleuchtet-33mm-weiss)
- [Bastelgarage – I2S Mikrofon Modul](https://www.bastelgarage.ch/i2s-mikrofon-modul)
- [Bastelgarage – LiPo Akku 2000mAh](https://www.bastelgarage.ch/lipo-akku-2000mah-jst-1-25-lithium-ion-polymer)
- [Digitec – TP4056 USB-C](https://www.digitec.ch/en/s1/product/purecrea-tp4056-lithium-lipo-akku-batterie-lademodul-usb-c-5v-1a-single-board-computer-kits-48003317)
- [LilyGO – T-Watch S3](https://lilygo.cc/en-pl/products/t-watch-s3)
