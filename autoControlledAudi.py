from pybricks.hubs import TechnicHub

try:
    from pybricks.pupdevices import DistanceSensor
except ImportError:  # Compatibilité Pybricks < v3.5
    try:
        from pybricks.pupdevices import UltrasonicSensor as DistanceSensor
    except ImportError:
        DistanceSensor = None

try:
    from pybricks.pupdevices import ColorDistanceSensor
except ImportError:
    ColorDistanceSensor = None

from pybricks.pupdevices import Motor, Remote
from pybricks.parameters import Button, Color, Direction, Port, Stop
from pybricks.tools import StopWatch, wait

hub = TechnicHub()

# Ports par défaut pour l'Audi RS Q e-tron (modifier si nécessaire).
PORT_DRIVE_LEFT = Port.A
PORT_DRIVE_RIGHT = Port.B
# La direction essaiera C puis D (adapter ici si besoin).
PORT_STEER_PRIORITY = (Port.C, Port.D)
# Le capteur testera d'abord D puis C pour éviter les conflits.
PORT_DISTANCE = (Port.D, Port.C)


def connect_device(cls, name, ports, **kwargs):
    """Essaie de connecter un périphérique PUP sur un ensemble de ports."""
    if not isinstance(ports, (tuple, list)):
        ports = (ports,)

    last_error = None
    for port in ports:
        try:
            device = cls(port, **kwargs)
            print(f"{name} détecté sur {port}.")
            return device
        except OSError as exc:
            last_error = exc
    raise OSError(f"{name}: aucun périphérique trouvé sur {', '.join(str(p) for p in ports)}") from last_error


drive_left = connect_device(
    Motor, "Moteur gauche", PORT_DRIVE_LEFT, positive_direction=Direction.CLOCKWISE
)
drive_right = connect_device(
    Motor, "Moteur droit", PORT_DRIVE_RIGHT, positive_direction=Direction.CLOCKWISE
)
steer = connect_device(
    Motor, "Direction", PORT_STEER_PRIORITY, positive_direction=Direction.CLOCKWISE
)
DISTANCE_SENSOR_CLASSES = [
    ("DistanceSensor", DistanceSensor),
    ("ColorDistanceSensor", ColorDistanceSensor),
]


def connect_distance_sensor(ports):
    for name, cls in DISTANCE_SENSOR_CLASSES:
        if cls is None:
            continue
        try:
            return connect_device(cls, name, ports)
        except OSError:
            continue
    raise ImportError(
        "Aucune classe compatible pour le capteur de distance (DistanceSensor / ColorDistanceSensor)."
    )


distance_sensor = connect_distance_sensor(PORT_DISTANCE)

remote = Remote()

MAX_SPEED = 1200         # vitesse de croisière en deg/s
REVERSE_SPEED = 900      # vitesse en marche arrière
# Mettre à 1 si la voiture avance déjà dans le bon sens, à -1 sinon.
FORWARD_SIGN = -1
STEER_MARGIN = 2         # marge pour éviter la contrainte sur les butées
STEER_SPEED = 800        # vitesse de braquage en deg/s
OBSTACLE_THRESHOLD_MM = 250
REVERSE_TURN_MS = 1200   # durée de marche arrière braquée
FORWARD_TURN_MS = 800    # durée de braquage en avançant pour finir l'évitement
STALL_SPEED_THRESHOLD = 150     # vitesse réelle moyenne sous laquelle on considère un blocage
STALL_COMMAND_THRESHOLD = 400   # commande minimale pour considérer une avance réelle
STALL_TIME_MS = 400             # durée du blocage avant de déclencher l'évitement


def shutdown_system():
    """Arrête proprement la voiture, le hub et la télécommande."""
    print("Arrêt demandé (boutons centraux).")
    drive_left.stop()
    drive_right.stop()
    steer.stop()
    hub.light.on(Color.RED)
    try:
        remote.system.shutdown()
    except AttributeError:
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

state = "forward"
state_watch = StopWatch()
stall_watch = StopWatch()
stall_timer_active = False


def enter_state(new_state):
    global state
    state = new_state
    state_watch.reset()
    print(f"--> Etat {state}")


def motor_stall_detected(command_speed):
    """Retourne True si la voiture force en voulant avancer."""
    global stall_timer_active

    commanded_forward = command_speed * FORWARD_SIGN > 0
    if not commanded_forward or abs(command_speed) < STALL_COMMAND_THRESHOLD:
        if stall_timer_active:
            stall_watch.reset()
            stall_timer_active = False
        return False

    avg_speed = (abs(drive_left.speed()) + abs(drive_right.speed())) / 2
    if avg_speed >= STALL_SPEED_THRESHOLD:
        if stall_timer_active:
            stall_watch.reset()
            stall_timer_active = False
        return False

    if not stall_timer_active:
        stall_timer_active = True
        stall_watch.reset()
        return False

    if stall_watch.time() >= STALL_TIME_MS:
        return True

    return False

while True:
    buttons = remote.buttons.pressed() or ()
    if Button.LEFT in buttons and Button.RIGHT in buttons:
        shutdown_system()

    try:
        distance_mm = distance_sensor.distance()
    except (OSError, ValueError):
        distance_mm = None

    if state == "forward":
        speed = FORWARD_SIGN * MAX_SPEED
        angle = 0
        hub.light.on(Color.GREEN)
        obstacle_by_distance = (
            distance_mm is not None and distance_mm <= OBSTACLE_THRESHOLD_MM
        )
        obstacle_by_stall = motor_stall_detected(speed)
        if obstacle_by_distance:
            print(f"Obstacle détecté à {distance_mm} mm.")
        elif obstacle_by_stall:
            print("Obstacle détecté par effort moteur.")
        if obstacle_by_distance or obstacle_by_stall:
            enter_state("reverse_turn")

    elif state == "reverse_turn":
        speed = -FORWARD_SIGN * REVERSE_SPEED
        angle = -STEER_ANGLE
        hub.light.on(Color.ORANGE)
        if state_watch.time() >= REVERSE_TURN_MS:
            enter_state("forward_turn")

    elif state == "forward_turn":
        speed = FORWARD_SIGN * MAX_SPEED
        angle = -STEER_ANGLE
        hub.light.on(Color.YELLOW)
        obstacle_by_distance = (
            distance_mm is not None and distance_mm <= OBSTACLE_THRESHOLD_MM
        )
        obstacle_by_stall = motor_stall_detected(speed)
        if obstacle_by_distance or obstacle_by_stall:
            print("Obstacle toujours présent pendant l'évitement.")
            enter_state("reverse_turn")
        elif state_watch.time() >= FORWARD_TURN_MS:
            enter_state("forward")
            angle = 0

    steer.run_target(STEER_SPEED, angle, Stop.HOLD, wait=False)
    drive_left.run(speed)
    drive_right.run(speed)

    wait(50)
