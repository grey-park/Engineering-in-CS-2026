*	Boitier rechargeable avec boutons et leds fonctionnel.
*	Routeur (broker MQTT) Fonctionnel.
*	Communication entre boitier et routeur en local. 
*	Micro fonctionnel sur boitier.
*	Interprétation Speech to Text sur le serveur.
*	Modèle local pour résumer la demande sur le routeur.
*	Mise en place de Devices / Montres MQTT.
*	Envoie et transmission sur montre / Autres Devices.
*	Tableau de bord administrateur.
*	Démo fonctionnel.
*	Test du produit dans un bar.

BONUS:
*	Affichage via une application sur android pour les tablettes cuisine et le rendu gérant.


# TapServe : liste de matériel et coûts (magasins suisses)

Prix relevés le 13.10.2026 dans des magasins suisses, TVA incluse, hors frais de port.
(v) = prix vérifié sur le site du magasin, ≈ = estimation

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
| **À acheter par boîtier** | | | | **≈ 40** | Sans les boutons ni la SuperMini |
| **À acheter pour 3 boîtiers** | | | | **≈ 120** | |

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
| Raspberry Pi 5, 2 Go | 1 | Galaxus | 92.90 (v) | 2 Go suffisent pour le broker et le tableau de bord |
| Alimentation officielle Raspberry Pi 27 W USB-C | 1 | — | ≈ 15 | |
| Carte microSD 32 Go | 1 | — | ≈ 12 | |
| Boîtier imprimé en 3D | 1 | — | ≈ 2 | |
| ESP32 ESP-WROOM-32 (passerelle) | 1 | Bastelgarage | 5.90 (v) | |
| **Total** | | | **≈ 128** | |

## Récapitulatif

| Poste | Total (CHF) |
|---|---|
| 3 boîtiers (à acheter) | ≈ 120 |
| Récepteur montre | ≈ 95–125 |
| Récepteur admin | 0 |
| Routeur / broker | ≈ 128 |
| **Total à acheter** | **≈ 340–370** |

## Remarques

- Les boutons arcade et les ESP32-C3 SuperMini sont déjà en main : ils ne sont pas comptés dans les totaux.
- Les petites pièces (TP4056, MOSFET, interrupteurs) coûtent beaucoup moins cher sur AliExpress, par exemple environ 0.50 CHF pour un TP4056 contre 10.90 CHF chez Digitec. Comptez 2 à 3 semaines de délai.
- Coût d'un boîtier au détail en Suisse, boutons et SuperMini compris : environ 50–60 CHF. En volume, avec des composants importés : environ 15 CHF.

## Sources

- [Galaxus – Raspberry Pi 5 2GB](https://www.galaxus.ch/en/s1/product/raspberry-pi-5-2gb-single-board-computer-kits-47872500)
- [Bastelgarage – Arcade Taster beleuchtet 33mm](https://www.bastelgarage.ch/arcade-taster-button-beleuchtet-33mm-weiss)
- [Bastelgarage – I2S Mikrofon Modul](https://www.bastelgarage.ch/i2s-mikrofon-modul)
- [Bastelgarage – LiPo Akku 2000mAh](https://www.bastelgarage.ch/lipo-akku-2000mah-jst-1-25-lithium-ion-polymer)
- [Bastelgarage – ESP32 ESP-WROOM-32](https://www.bastelgarage.ch/esp32-esp-wroom-32)
- [Digitec – TP4056 USB-C](https://www.digitec.ch/en/s1/product/purecrea-tp4056-lithium-lipo-akku-batterie-lademodul-usb-c-5v-1a-single-board-computer-kits-48003317)
- [LilyGO – T-Watch S3](https://lilygo.cc/en-pl/products/t-watch-s3)
