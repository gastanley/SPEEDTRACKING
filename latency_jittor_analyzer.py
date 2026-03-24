import subprocess
import time
import statistics
import locale

def check_jitter(host="192.168.88.1", count=10):
    latencies = []
    for _ in range(count):
        cmd = ["ping", "-n", "1", host] # -c 1 sur Linux
        current_encoding = locale.getpreferredencoding() 
        output = subprocess.check_output(cmd).decode(current_encoding)
        if "temps=" in output: # "time=" sur Linux
            ms = float(output.split("temps=")[1].split("ms")[0])
            latencies.append(ms)
        time.sleep(0.5)
    
    if latencies:
        jitter = statistics.stdev(latencies) if len(latencies) > 1 else 0
        print(f"Moyenne: {sum(latencies)/len(latencies):.2f}ms | Jitter: {jitter:.2f}ms")

check_jitter()