# PyBricks – Audi RS Q e-tron Helpers

Scripts pour piloter une Audi RS Q e-tron modifiée avec PyBricks. Tous les programmes supposent un Technic Hub avec deux moteurs de propulsion (ports A/B par défaut) et un moteur de direction (ports C/D).

## Fichiers

- `autoControlledAudi.py`  
  Voiture autonome avec capteur de distance (DistanceSensor ou ColorDistanceSensor). Utilise un automate à états pour avancer, reculer et contourner les obstacles, avec détection de blocage moteur via `motor_stall_detected`.

- `remoteControlledAudi.py`  
  Pilotage via la manette PUP (`Remote`). La calibration des butées est identique, mais les commandes viennent des boutons A/B (propulsion et direction). Le bouton central gauche coupe tout (`shutdown_system`).

- `keyboardControlledAudi.py`  
  Version PC/terminal : configuration interactive des touches (par défaut les flèches) puis pilotage en temps réel via `stdin` USB/BLE. Inclut lecture non bloquante avec `uselect` et arrêt par `q` / `Ctrl+C`.

- `scan_ports.py`  
  Outil de diagnostic : parcourt les ports A–D, connecte un `Motor` si possible, affiche un ✅/❌ et fait un léger mouvement pour vérifier que le moteur répond.

- `ex.py`  
  Actuellement un simple import (`import os`). Sert d’exemple minimal ou de placeholder.

## Conseils d’exécution

1. Installe `pybricksdev` et relie ton hub en USB ou BLE (`pybricksdev run usb …` ou `pybricksdev run ble --name …`).
2. Avant chaque session, assure-toi qu’aucun autre script ne tient le hub (redémarre-le si besoin).
3. Pour les scripts clavier, garde le terminal actif (pas de console non interactive) afin que `stdin` transmette bien les touches.
