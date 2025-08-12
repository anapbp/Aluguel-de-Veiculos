import datetime
import threading

log_lock = threading.Lock()

def get_timestamp():
    # Formato YYYY-MM-DD HH:MM:SS.mmm (milissegundos)
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def write_log(file_path, message):
    with log_lock:
        with open(file_path, "a") as f:
            f.write(message + "\n")

TERMINAL_CONFIG = {
    "Terminal 1": {"porta": "50151", "classes": ["Executivos", "Minivan"]},
    "Terminal 2": {"porta": "50152", "classes": ["Intermediarios", "SUV"]},
    "Terminal 3": {"porta": "50153", "classes": ["Economicos"]},
}

ALL_VEHICLE_CLASSES = [
    "Economicos", "Intermediarios", "SUV", "Executivos", "Minivan"
]

ALL_VEHICLES_DEFINITION = {
    "Economicos": ["Chevrolet Onix", "Renault Kwid", "Peugeot 208"],
    "Intermediarios": ["Honda City", "Fiat Cronos", "Volkswagen Virtus"],
    "SUV": ["Jeep Commander", "Audi Q7", "Lexus RX"],
    "Executivos": ["BMW Série 5", "Toyota Corolla Altis Híbrido"],
    "Minivan": ["Chevrolet Spin", "Fiat Doblo", "Nissan Livina", "Citroën C4 Picasso", "Chevrolet Zafira"]
}
