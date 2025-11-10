from pybricks.hubs import TechnicHub
from pybricks.pupdevices import Motor, Remote
from pybricks.parameters import Port, Direction, Stop, Button, Color
from pybricks.tools import wait

hub = TechnicHub()

# Ports par défaut pour l'Audi RS Q e-tron (modifier si nécessaire).
PORT_DRIVE_LEFT = Port.A
PORT_DRIVE_RIGHT = Port.B
# Essaye d'abord C, puis D si rien n'est branché sur C.
PORT_STEER_PRIORITY = (Port.C, Port.D)


def connect_motor(name, ports, **kwargs):
    """Retourne un moteur connecté sur l'un des ports donnés."""
    if not isinstance(ports, (tuple, list)):
        ports = (ports,)

    last_error = None
    for port in ports:
        try:
            motor = Motor(port, **kwargs)
            print(f"{name} détecté sur {port}.")
            return motor
        except OSError as exc:
            last_error = exc
    raise OSError(f"{name}: aucun moteur trouvé sur {', '.join(str(p) for p in ports)}") from last_error


drive_left = connect_motor(
    "Moteur gauche", PORT_DRIVE_LEFT, positive_direction=Direction.CLOCKWISE
)
drive_right = connect_motor(
    "Moteur droit", PORT_DRIVE_RIGHT, positive_direction=Direction.CLOCKWISE
)
steer = connect_motor(
    "Direction", PORT_STEER_PRIORITY, positive_direction=Direction.CLOCKWISE
)

remote = Remote()

MAX_SPEED = 1000         # vitesse max en deg/s
STEER_STEP = 20           # incrément par appui court sur B+ ou B-
STEER_MARGIN = 2         # marge pour éviter la contrainte sur les butées
STEER_SPEED = 1200       # vitesse de braquage en deg/s (augmentée pour répondre plus vite)


def shutdown_system():
    """Arrête proprement la voiture, le hub et la télécommande."""
    print("Arrêt demandé (bouton A central).")
    drive_left.stop()
    drive_right.stop()
    steer.stop()
    hub.light.on(Color.RED)
    try:
        remote.system.shutdown()
    except AttributeError:
        # Anciennes versions exposent power.off()
        if hasattr(remote, "power"):
            remote.power.off()
    hub.system.shutdown()


def calibrate_steering():
    """Balaye la direction pour trouver les butées et calcule l'amplitude safe."""
    print("Calibration direction...")

    steer.reset_angle(0)
    steer.run_until_stalled(-600, Stop.COAST, duty_limit=70)  # butée gauche forcée
    left = steer.angle()
    print(f"Butée gauche détectée à {left:.0f}°")

    steer.run_until_stalled(600, Stop.COAST, duty_limit=70)   # butée droite forcée
    right = steer.angle()
    print(f"Butée droite détectée à {right:.0f}°")

    sweep = right - left
    if sweep <= 0:
        raise RuntimeError("Calibration impossible : balayage nul")

    center = left + sweep / 2
    steer.run_target(STEER_SPEED, center, Stop.HOLD)
    steer.reset_angle(0)

    usable = max(10, sweep / 2 - STEER_MARGIN) * 1.5
    print(f"Amplitude utilisable : ±{usable:.0f}° (course totale {sweep:.0f}°)")
    return usable


STEER_ANGLE = calibrate_steering()

speed = 0
angle = 0

while True:
    buttons = remote.buttons.pressed() or ()

    if Button.LEFT in buttons:
        print("Shutdown!")
        shutdown_system()

    # A+/A- contrôle direct de la propulsion : relâcher = stop.
    if Button.LEFT_PLUS in buttons:
        speed = MAX_SPEED
    elif Button.LEFT_MINUS in buttons:
        speed = -MAX_SPEED
    else:
        speed = 0

    # B+/B- ajustent le volant et conservent l'angle, B (milieu) recentre.
    if Button.RIGHT_PLUS in buttons:
        angle = min(STEER_ANGLE, angle + STEER_STEP)
    elif Button.RIGHT_MINUS in buttons:
        angle = max(-STEER_ANGLE, angle - STEER_STEP)
    elif Button.RIGHT in buttons:
        angle = 0

    steer.run_target(STEER_SPEED, angle, Stop.HOLD, wait=False)
    drive_left.run(speed)
    drive_right.run(speed)

    hub.light.on(Color.GREEN if speed >= 0 else Color.RED)
    wait(50)
