import time
import threading
import subprocess
import re
import os
import csv
from collections import deque
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import psutil
import uvicorn

app = FastAPI()
# On augmente à 300 pour garder 5 minutes de contexte en RAM
stats_history = deque(maxlen=300)
GATEWAY = "192.168.88.1" 
CSV_FILE = "network_stats_history.csv"

# --- INITIALISATION CSV (Data Science) ---
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Download_KBps", "Upload_KBps", "Ping_ms", "Status"])

def get_active_interface():
    addrs = psutil.net_io_counters(pernic=True)
    best_iface = "Wi-Fi"
    max_total = -1
    for iface, data in addrs.items():
        total = data.bytes_recv + data.bytes_sent
        if "loopback" not in iface.lower() and total > max_total:
            max_total = total
            best_iface = iface
    return best_iface

INTERFACE = get_active_interface()

def get_ping(host):
    try:
        output = subprocess.check_output(f"ping -n 1 -w 500 {host}", shell=True).decode('cp850', errors='ignore')
        match = re.search(r"(\d+)\s*ms", output)
        return int(match.group(1)) if match else 999
    except Exception:
        return 999

def get_status(ms):
    if ms < 20: return "OPTIMAL (Direct)", "#2ecc71"
    if ms < 80: return "MOYEN (Congestion)", "#f39c12"
    return "MAUVAIS (Saturation/NAT)", "#e74c3c"

def save_to_csv(entry):
    """Sauvegarde persistante d'une ligne de donnée"""
    try:
        with open(CSV_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([entry['time'], entry['down'], entry['up'], entry['ping'], entry['status']])
    except Exception as e:
        print(f"Erreur d'écriture CSV : {e}")

# --- BACKEND ROBUSTE (Gestion crash silencieux) ---
def network_worker():
    print(f"[*] Diagnostic dynamique lancé sur : {INTERFACE}")
    last_csv_save = time.time()
    
    # Initialisation sécurisée des compteurs
    try:
        old_stats = psutil.net_io_counters(pernic=True).get(INTERFACE, psutil.net_io_counters())
        old_recv, old_sent = old_stats.bytes_recv, old_stats.bytes_sent
    except:
        old_recv, old_sent = 0, 0

    while True:
        try:
            time.sleep(1)
            # Vérification de l'existence de l'interface (évite le crash si on coupe le Wi-Fi)
            current_all_stats = psutil.net_io_counters(pernic=True)
            if INTERFACE not in current_all_stats:
                continue 
                
            new_stats = current_all_stats[INTERFACE]
            down = (new_stats.bytes_recv - old_recv) / 1024
            up = (new_stats.bytes_sent - old_sent) / 1024
            latency = get_ping(GATEWAY)
            status_text, status_color = get_status(latency)
            
            data_entry = {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "down": round(down, 2),
                "up": round(up, 2),
                "ping": latency,
                "status": status_text,
                "color": status_color
            }
            
            stats_history.append(data_entry)
            
            # Sauvegarde persistante toutes les 5 secondes (ajustable)
            if time.time() - last_csv_save > 5:
                save_to_csv(data_entry)
                last_csv_save = time.time()

            old_recv, old_sent = new_stats.bytes_recv, new_stats.bytes_sent
            
        except Exception as e:
            # Le "Anti-Crash" : On print l'erreur mais on ne casse pas la boucle
            print(f"[!] Erreur de monitoring (récupération en cours...) : {e}")
            time.sleep(2)

@app.on_event("startup")
def startup():
    threading.Thread(target=network_worker, daemon=True).start()

@app.get("/api/stats")
async def get_stats():
    return list(stats_history)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return """
    <html>
        <head>
            <title>Dynamic Monitor PRO</title>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
            <style>
                body { font-family: 'Segoe UI', sans-serif; background: #0b0e14; color: #e0e0e0; padding: 20px; }
                .card { background: #151921; border-radius: 12px; padding: 20px; max-width: 950px; margin: auto; border: 1px solid #232933; }
                .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 20px 0; }
                .box { background: #1c222d; padding: 15px; border-radius: 8px; text-align: center; border-bottom: 3px solid #2ecc71; }
                .val { font-size: 22px; font-weight: bold; color: #fff; display: block; }
                .unit { font-size: 13px; color: #888; margin-left: 4px; }
                .lbl { font-size: 11px; text-transform: uppercase; color: #5c6370; letter-spacing: 1px; }
                #badge { font-size: 12px; padding: 3px 10px; border-radius: 12px; display: inline-block; margin-top: 8px; }
                #location-display { font-size: 13px; color: #4ecca3; margin-top: 5px; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="card">
                <div style="text-align:center">
                    <h2 style="margin:0">Monitoring Réseau Dynamique</h2>
                    <div id="location-display">📍 Recherche de localisation...</div>
                </div>
                
                <div class="grid">
                    <div class="box" style="border-color: #4ecca3">
                        <span class="lbl">Download</span>
                        <div><span class="val" id="d-val">0</span><span class="unit" id="d-unit">Ko/s</span></div>
                    </div>
                    <div class="box" style="border-color: #45b7d1">
                        <span class="lbl">Upload</span>
                        <div><span class="val" id="u-val">0</span><span class="unit" id="u-unit">Ko/s</span></div>
                    </div>
                    <div class="box" style="border-color: #f39c12">
                        <span class="lbl">Latence</span>
                        <div><span class="val" id="p-val">0</span><span class="unit">ms</span></div>
                        <div id="badge">Diagnostic...</div>
                    </div>
                </div>

                <canvas id="chart" height="140"></canvas>
            </div>

            <script>
                // --- SÉCURITÉ FRONTEND & LOCALISATION ---
                async function updateLocation() {
                    const locEl = document.getElementById('location-display');
                    if (navigator.geolocation) {
                        navigator.geolocation.getCurrentPosition(async (pos) => {
                            const { latitude, longitude } = pos.coords;
                            try {
                                // AJOUT SÉCURITÉ : Identification User-Agent pour éviter le blocage Nominatim
                                const response = await fetch(
                                    `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}`,
                                    { headers: { 'User-Agent': 'NetworkMonitorApp/1.0' } }
                                );
                                const data = await response.json();
                                const city = data.address.city || data.address.town || data.address.village || "Antananarivo";
                                locEl.innerText = "📍 " + city + ", Madagascar";
                            } catch (error) {
                                locEl.innerText = "📍 Erreur de service Localisation";
                            }
                        }, (err) => {
                            locEl.innerText = "📍 Accès localisation refusé ou indisponible";
                        }, { timeout: 5000 }); // Sécurité : Timeout si le GPS ne répond pas
                    } else {
                        locEl.innerText = "📍 Géolocalisation non supportée";
                    }
                }
                updateLocation();

                const ctx = document.getElementById('chart').getContext('2d');
                const chart = new Chart(ctx, {
                    type: 'line',
                    data: { labels: [], datasets: [
                        { label: 'Download', data: [], borderColor: '#4ecca3', tension: 0.3, fill: true, backgroundColor: 'rgba(78,204,163,0.05)' },
                        { label: 'Ping', data: [], borderColor: '#e74c3c', yAxisID: 'y1', borderDash: [3,3] }
                    ]},
                    options: { 
                        scales: { 
                            y: { grid: {color:'#232933'}, ticks: {color:'#5c6370'} },
                            y1: { position: 'right', grid: {display:false}, ticks: {color:'#e74c3c'} }
                        },
                        plugins: { legend: { display: false } }
                    }
                });

                function updateDisplay(value, valId, unitId) {
                    const valEl = document.getElementById(valId);
                    const unitEl = document.getElementById(unitId);
                    if (value >= 1024) {
                        valEl.innerText = (value / 1024).toFixed(2);
                        unitEl.innerText = "Mo/s";
                        valEl.style.color = "#FFD700"; 
                    } else {
                        valEl.innerText = value.toFixed(1);
                        unitEl.innerText = "Ko/s";
                        valEl.style.color = "#fff";
                    }
                }

                async function refresh() {
                    try {
                        const r = await fetch('/api/stats');
                        const data = await r.json();
                        if(data.length > 0) {
                            const last = data[data.length - 1];
                            updateDisplay(last.down, 'd-val', 'd-unit');
                            updateDisplay(last.up, 'u-val', 'u-unit');
                            document.getElementById('p-val').innerText = last.ping;
                            const b = document.getElementById('badge');
                            b.innerText = last.status;
                            b.style.backgroundColor = last.color;

                            // Affichage uniquement de l'heure (HH:mm:ss) sur le graphe
                            chart.data.labels = data.map(d => d.time.split(' ')[1]);
                            chart.data.datasets[0].data = data.map(d => d.down);
                            chart.data.datasets[1].data = data.map(d => d.ping);
                            chart.update('none');
                        }
                    } catch(e) { console.log("Serveur injoignable..."); }
                }
                setInterval(refresh, 1000);
            </script>
        </body>
    </html>
    """

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)