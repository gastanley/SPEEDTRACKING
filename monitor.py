import psutil
import time
import os

# --- CONFIGURATION ---
INTERFACE = "Wi-Fi"  # Remplace par "Ethernet" si besoin
# ---------------------

def get_bandwidth(iface):
    stat = psutil.net_io_counters(pernic=True)
    if iface in stat:
        return stat[iface].bytes_recv, stat[iface].bytes_sent
    return 0, 0

print(f"--- Monitoring de l'interface : {INTERFACE} ---")

try:
    old_recv, old_sent = get_bandwidth(INTERFACE)
    while True:
        time.sleep(1) # Mesure sur 1 seconde
        new_recv, new_sent = get_bandwidth(INTERFACE)
        
        # Calcul de la différence (Octets par seconde)
        diff_recv = new_recv - old_recv
        diff_sent = new_sent - old_sent
        
        # Conversions
        down_kb = diff_recv / 1024
        up_kb = diff_sent / 1024
        down_mb = (diff_recv * 8) / (1024 * 1024)
        
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"Interface : {INTERFACE}")
        print("-" * 30)
        print(f"DOWNLOAD : {down_kb:8.2f} Ko/s  ({down_mb:.2f} Mbps)")
        print(f"UPLOAD   : {up_kb:8.2f} Ko/s")
        print("-" * 30)
        print("Appuyez sur Ctrl+C pour arrêter.")
        
        old_recv, old_sent = new_recv, new_sent

except KeyboardInterrupt:
    print("\nArrêt du monitoring.")
except Exception as e:
    print(f"Erreur : {e}")