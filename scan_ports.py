#!/usr/bin/env pybricks-micropython

from pybricks.pupdevices import Motor
from pybricks.parameters import Port
from pybricks.tools import wait

ports = [Port.A, Port.B, Port.C, Port.D]

print("Scan des ports...")

for p in ports:
    try:
        m = Motor(p)
        print("✅ Moteur détecté sur", p)
        # Petit mouvement pour confirmer visuellement
        m.run_angle(300, 90)
        wait(500)
        m.run_angle(300, -90)
        m.stop()
    except OSError:
        print("❌ Rien sur", p)

print("Scan terminé.")

while True:
    wait(1000)
