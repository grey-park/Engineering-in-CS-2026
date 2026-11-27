# TapServe

Le client appuie sur un bouton à sa table, la montre du serveur vibre, le serveur touche l'écran pour dire "J'arrive" et la LED de la table s'allume pour le confirmer.

Le Raspberry Pi fait le lien entre tout ça : il crée le Wi-Fi, reçoit les appels et affiche un tableau de bord pour le gérant.

## Dossiers

- `box/` : le boîtier de table (ESP32-C3, 3 boutons, 3 LEDs)
- `watch/` : la montre du serveur (LilyGO T-Watch S3)
- `server/` : le serveur et le tableau de bord (Raspberry Pi)
- `common/` : le code partagé entre le boîtier et la montre

## Lancer le projet

Avant de compiler, copier `common/secrets.example.h` en `common/secrets.h` et y mettre le mot de passe Wi-Fi.

```
cd box   && pio run -e table1 -t upload --upload-port COMx
cd watch && pio run -t upload --upload-port COMx
cd server && pip install -r requirements.txt && python server.py
```

Le tableau de bord s'ouvre sur `http://10.42.0.1:8000`.

Sans matériel : `python server.py --simulate`.

## Câblage du boîtier

| | XIAO ESP32-C3 | SuperMini |
|---|---|---|
| Boutons (vers GND) | D1, D2, D3 | GPIO3, 4, 5 |
| LEDs (+ 330 ohms) | D4, D5, D10 | GPIO6, 7, 10 |
| Batterie (pont 100k/100k) | D0 | GPIO1 |

## Plus de détails

- [installation.md](installation.md) : installation du Pi et protocole MQTT
- [materiel.md](materiel.md) : liste du matériel et coûts

## La suite

Micro sur le boîtier, speech to text sur le Pi, batterie et boîtier imprimé en 3D.
