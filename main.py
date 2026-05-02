import time
import threading
import subprocess
import re
import os
import csv
import statistics
from datetime import datetime
from collections import deque
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import psutil
import uvicorn

app = FastAPI()
stats_history = deque(maxlen=300)
latency_samples = deque(maxlen=20) 
GATEWAY = "192.168.1.1" 
CSV_FILE = "network_stats_history.csv"

if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Download_KBps", "Upload_KBps", "Ping_ms", "Jitter_ms", "Loss", "Status"])

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

def get_ping_with_loss(host):
    """Reprend ta logique de regex originale (\d+)\s*ms pour éviter le 999ms constant"""
    try:
        output = subprocess.check_output(f"ping -n 1 -w 500 {host}", shell=True).decode('cp850', errors='ignore')
        match = re.search(r"(\d+)\s*ms", output)
        if match:
            return int(match.group(1)), 0  # Ping trouvé, 0% perte
        return 999, 100 # Pas de match, 100% perte
    except Exception:
        return 999, 100

def get_network_analysis(ms, jitter, loss):
    """Ton analyse originale avec prise en compte de la perte pour l'alignement"""
    if loss > 0 or ms > 250 or jitter > 80:
        return "CRITIQUE (Saturation)", "#e74c3c"
    if ms > 100 or jitter > 40:
        return "CONGESTION (Dépriorisation)", "#f39c12"
    return "STABLE (Normal)", "#2ecc71"

def check_monthly_cycle():
    day = datetime.now().day
    if day >= 25:
        return "⚠️ Fin de mois : Risque de bridage quota élevé."
    if day <= 5:
        return "✅ Début de mois : Rétablissement des services."
    return "Cycle standard en cours..."

def save_to_csv(entry):
    try:
        with open(CSV_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([entry['time'], entry['down'], entry['up'], entry['ping'], entry['jitter'], entry['loss'], entry['status']])
    except Exception as e:
        print(f"Erreur CSV : {e}")

def network_worker():
    print(f"[*] Monitoring avec outil d'alignement sur : {INTERFACE}")
    last_csv_save = time.time()
    
    try:
        old_stats = psutil.net_io_counters(pernic=True).get(INTERFACE, psutil.net_io_counters())
        old_recv, old_sent = old_stats.bytes_recv, old_stats.bytes_sent
    except:
        old_recv, old_sent = 0, 0

    while True:
        try:
            time.sleep(1)
            current_all_stats = psutil.net_io_counters(pernic=True)
            if INTERFACE not in current_all_stats: continue 
                
            new_stats = current_all_stats[INTERFACE]
            down = (new_stats.bytes_recv - old_recv) / 1024
            up = (new_stats.bytes_sent - old_sent) / 1024
            
            latency, loss = get_ping_with_loss(GATEWAY)
            latency_samples.append(latency)
            jitter = round(statistics.stdev(latency_samples), 2) if len(latency_samples) > 1 else 0
            
            status_text, status_color = get_network_analysis(latency, jitter, loss)
            cycle_msg = check_monthly_cycle()
            
            data_entry = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "down": round(down, 2),
                "up": round(up, 2),
                "ping": latency,
                "jitter": jitter,
                "loss": loss,
                "status": status_text,
                "color": status_color,
                "cycle": cycle_msg
            }
            
            stats_history.append(data_entry)
            
            if time.time() - last_csv_save > 5:
                save_to_csv(data_entry)
                last_csv_save = time.time()

            old_recv, old_sent = new_stats.bytes_recv, new_stats.bytes_sent
            
        except Exception as e:
            print(f"Erreur Worker : {e}")
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
            <title>Starlink Monitor PRO</title>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
            <style>
                body { font-family: 'Segoe UI', sans-serif; background: #0b0e14; color: #e0e0e0; padding: 20px; }
                .card { background: #151921; border-radius: 12px; padding: 20px; max-width: 950px; margin: auto; border: 1px solid #232933; }
                .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }
                .box { background: #1c222d; padding: 15px; border-radius: 8px; text-align: center; border-bottom: 3px solid #2ecc71; }
                .val { font-size: 20px; font-weight: bold; color: #fff; display: block; }
                .lbl { font-size: 10px; text-transform: uppercase; color: #5c6370; letter-spacing: 1px; }
                #cycle-info { background: #1a202c; padding: 10px; border-radius: 6px; font-size: 13px; color: #4db8ff; margin-bottom: 15px; text-align: center; border: 1px solid #2d3748; }
                #badge { font-size: 11px; padding: 3px 8px; border-radius: 10px; margin-top: 5px; display: inline-block; }
            </style>
        </head>
        <body>
            <div class="card">
                <div id="cycle-info">Analyse du cycle mensuel en cours...</div>
                <div style="text-align:center">
                    <h2 style="margin:0">Diagnostic Starlink Madagascar</h2>
                    <div id="location-display" style="font-size:12px; color:#4ecca3">Localisation...</div>
                </div>
                
                <div class="grid">
                    <div class="box" style="border-color: #4ecca3">
                        <span class="lbl">Download</span>
                        <span class="val" id="d-val">0</span><span id="d-unit" style="font-size:10px">Ko/s</span>
                    </div>
                    <div class="box" style="border-color: #f39c12">
                        <span class="lbl">Latence</span>
                        <span class="val" id="p-val">0</span><span style="font-size:10px">ms</span>
                    </div>
                    <div class="box" style="border-color: #e74c3c">
                        <span class="lbl">Perte / Jitter</span>
                        <span class="val"><span id="l-val" style="color:#e74c3c">0%</span> / <span id="j-val" style="font-size:14px">0</span>ms</span>
                    </div>
                    <div class="box" style="border-color: #45b7d1">
                        <span class="lbl">Qualité</span>
                        <div id="badge">Analyse...</div>
                    </div>
                </div>
                <canvas id="chart" height="120"></canvas>
            </div>

            <script>
                async function updateLocation() {
                    const locEl = document.getElementById('location-display');
                    navigator.geolocation.getCurrentPosition(async (pos) => {
                        try {
                            const response = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${pos.coords.latitude}&lon=${pos.coords.longitude}`, {headers:{'User-Agent':'Monitor'}});
                            const data = await response.json();
                            locEl.innerText = "📍 " + (data.address.city || "Madagascar");
                        } catch(e) { locEl.innerText = "📍 Madagascar"; }
                    });
                }
                updateLocation();

                const ctx = document.getElementById('chart').getContext('2d');
                const chart = new Chart(ctx, {
                    type: 'line',
                    data: { labels: [], datasets: [
                        { label: 'Download', data: [], borderColor: '#4ecca3', tension: 0.3, yAxisID: 'y' },
                        { label: 'Jitter', data: [], borderColor: '#e74c3c', yAxisID: 'y1', borderDash: [2,2] }
                    ]},
                    options: { scales: { y: { display: true }, y1: { position: 'right', display: true } }, plugins: { legend: { display: false } } }
                });

                async function refresh() {
                    const r = await fetch('/api/stats');
                    const data = await r.json();
                    if(data.length > 0) {
                        const last = data[data.length - 1];
                        document.getElementById('d-val').innerText = last.down > 1024 ? (last.down/1024).toFixed(2) : last.down;
                        document.getElementById('d-unit').innerText = last.down > 1024 ? " Mo/s" : " Ko/s";
                        document.getElementById('p-val').innerText = last.ping;
                        document.getElementById('j-val').innerText = last.jitter;
                        document.getElementById('l-val').innerText = last.loss + "%";
                        document.getElementById('cycle-info').innerText = last.cycle;
                        
                        const b = document.getElementById('badge');
                        b.innerText = last.status;
                        b.style.backgroundColor = last.color;

                        chart.data.labels = data.map(d => d.time.split(' ')[1]);
                        chart.data.datasets[0].data = data.map(d => d.down);
                        chart.data.datasets[1].data = data.map(d => d.jitter);
                        chart.update('none');
                    }
                }
                setInterval(refresh, 1000);
            </script>
        </body>
    </html>
    """

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)