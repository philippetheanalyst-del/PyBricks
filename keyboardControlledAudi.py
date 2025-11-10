from pybricks.hubs import TechnicHub
from pybricks.pupdevices import Motor
from pybricks.parameters import Color, Direction, Port, Stop
from pybricks.tools import StopWatch, wait

try:
    import sys
except ImportError:
    import usys as sys

try:
    import uselect as select
except ImportError:
    select = None


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

MAX_SPEED = 1200             # vitesse max en deg/s
STEER_STEP = 5               # incrément par tick clavier gauche/droite
STEER_MARGIN = 2             # marge pour éviter la contrainte sur les butées
STEER_SPEED = 800            # vitesse de braquage en deg/s
KEY_HOLD_TIMEOUT_MS = 160    # délai sans répétition avant de considérer la touche relâchée


class KeyboardController:
    """Capture les touches envoyées sur stdin par le terminal."""

    ARROW_CODES = {
        "A": "ARROW_UP",
        "B": "ARROW_DOWN",
        "C": "ARROW_RIGHT",
        "D": "ARROW_LEFT",
    }
    RESERVED_KEYS = {"q", "Q"}   # utilisé pour quitter pendant la conduite

    def __init__(self, timeout_ms):
        if select is None:
            raise ImportError(
                "Le module uselect n'est pas disponible : impossible de lire le clavier."
            )

        self.timeout_ms = timeout_ms
        self.clock = StopWatch()
        self.clock.reset()

        self.bindings = {}
        self.action_states = {}
        self.key_states = {}
        self.key_deadlines = {}
        self.quit_requested = False
        self._buffer = ""

        self._stream = sys.stdin
        try:
            self._poller = select.poll()
            event_flag = getattr(select, "POLLIN", 1)
            self._poller.register(self._stream, event_flag)
        except Exception as exc:
            raise RuntimeError(
                "Impossible d'initialiser la lecture clavier. Lance le script depuis un terminal USB."
            ) from exc

    def set_bindings(self, bindings):
        """Associe les actions logique aux touches physiques."""
        self.bindings = dict(bindings)
        self.action_states = {action: False for action in self.bindings}

    def describe_key(self, key_id):
        if key_id is None:
            return "aucune"
        labels = {
            "ARROW_UP": "Flèche Haut",
            "ARROW_DOWN": "Flèche Bas",
            "ARROW_LEFT": "Flèche Gauche",
            "ARROW_RIGHT": "Flèche Droite",
        }
        return labels.get(key_id, f"'{key_id}'")

    def configure_bindings(self, prompts, defaults):
        """Dialogue interactif pour choisir les touches."""
        print("Configuration des commandes clavier :")
        selected = {}
        for action, message in prompts:
            default_key = defaults.get(action)
            selected[action] = self._prompt_single_binding(
                message, default_key, selected
            )
            print(f"  -> {self.describe_key(selected[action])}")
        self.set_bindings(selected)
        return selected

    def _prompt_single_binding(self, message, default_key, already_chosen):
        while True:
            default_text = (
                f"(Entrée = {self.describe_key(default_key)})"
                if default_key
                else "(appuie sur une touche)"
            )
            print(f"{message} {default_text}")
            key_id = self._wait_for_keypress(allow_default=bool(default_key))
            if key_id is None:
                key_id = default_key
            if key_id is None:
                print("Aucune touche détectée, recommence.")
                continue
            if key_id in self.RESERVED_KEYS:
                print("Cette touche est réservée pour quitter. Choisis-en une autre.")
                continue
            if key_id in already_chosen.values():
                print("Touche déjà affectée, choisis-en une autre.")
                continue
            return key_id

    def _wait_for_keypress(self, allow_default):
        """Bloque jusqu'à détection d'une touche (ou Entrée si autorisé)."""
        self._buffer = ""
        while True:
            events = self._poller.poll(None)
            if not events:
                continue
            char = self._stream.read(1)
            if not char:
                continue
            if isinstance(char, bytes):
                char = char.decode()
            if char in ("\r", "\n") and allow_default and not self._buffer:
                return None
            key_id = self._process_char(char, capture_mode=True)
            if key_id:
                return key_id

    def update(self):
        """Met à jour l'état des touches et retourne les actions."""
        if not self.bindings:
            raise RuntimeError("Aucune touche n'est configurée.")

        self._drain_input(register=True)
        now = self.clock.time()
        for key, pressed in list(self.key_states.items()):
            if pressed and now > self.key_deadlines.get(key, 0):
                self.key_states[key] = False
        for action, key_id in self.bindings.items():
            self.action_states[action] = self.key_states.get(key_id, False)
        return dict(self.action_states)

    def _drain_input(self, register):
        while self._poller.poll(0):
            char = self._stream.read(1)
            if not char:
                break
            if isinstance(char, bytes):
                char = char.decode()
            key_id = self._process_char(char, capture_mode=False)
            if key_id:
                self._mark_pressed(key_id, register)

    def _mark_pressed(self, key, register):
        if not register:
            return
        self.key_states[key] = True
        self.key_deadlines[key] = self.clock.time() + self.timeout_ms

    def _process_char(self, char, capture_mode):
        if char in ("\x03", "\x04"):   # Ctrl+C / Ctrl+D
            raise KeyboardInterrupt
        if not capture_mode and char in self.RESERVED_KEYS:
            self.quit_requested = True
            return None

        self._buffer += char
        if self._buffer in ("\x1b", "\x1b["):
            return None

        if self._buffer.startswith("\x1b["):
            code = self._buffer[-1]
            key = self.ARROW_CODES.get(code)
            if key:
                self._buffer = ""
                return key
            if len(self._buffer) > 3:
                self._buffer = ""
            return None

        key = self._buffer
        self._buffer = ""
        if key in ("\n", "\r"):
            return None
        return key


def shutdown_system():
    """Arrête proprement la voiture et le hub."""
    print("Arrêt demandé.")
    drive_left.stop()
    drive_right.stop()
    steer.stop()
    hub.light.on(Color.RED)
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

ACTIONS = [
    ("forward", "Appuie sur la touche pour AVANCER"),
    ("reverse", "Appuie sur la touche pour RECULER"),
    ("left", "Appuie sur la touche pour TOURNER A GAUCHE"),
    ("right", "Appuie sur la touche pour TOURNER A DROITE"),
]
DEFAULT_BINDINGS = {
    "forward": "ARROW_UP",
    "reverse": "ARROW_DOWN",
    "left": "ARROW_LEFT",
    "right": "ARROW_RIGHT",
}

keyboard = KeyboardController(KEY_HOLD_TIMEOUT_MS)
keyboard.configure_bindings(ACTIONS, DEFAULT_BINDINGS)

speed = 0
angle = 0

try:
    while True:
        keys = keyboard.update()
        if keyboard.quit_requested:
            break

        if keys["forward"]:
            speed = MAX_SPEED
        elif keys["reverse"]:
            speed = -MAX_SPEED
        else:
            speed = 0

        if keys["right"]:
            angle = min(STEER_ANGLE, angle + STEER_STEP)
        elif keys["left"]:
            angle = max(-STEER_ANGLE, angle - STEER_STEP)
        else:
            angle = 0

        steer.run_target(STEER_SPEED, angle, Stop.HOLD, wait=False)
        drive_left.run(speed)
        drive_right.run(speed)

        hub.light.on(Color.GREEN if speed >= 0 else Color.RED)
        wait(50)
except KeyboardInterrupt:
    print("Interruption clavier.")
finally:
    shutdown_system()
