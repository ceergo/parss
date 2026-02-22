import re
import requests
import base64
import socket
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import maxminddb


# --- CONFIGURATION ---
SOURCES = [
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt",
    "https://raw.githubusercontent.com/freev2rayspeed/v2ray/main/v2ray.txt",
    "https://raw.githubusercontent.com/aiboboxx/v2rayfree/main/v2ray",
    "https://raw.githubusercontent.com/vpei/free-v2ray-config/master/v2ray.txt",
    "https://raw.githubusercontent.com/tbbatbb/Proxy/master/dist/v2ray.config",
    "https://raw.githubusercontent.com/StayHu/v2ray/master/v2ray.txt"
]

PERSONAL_LINKS_FILE = "my_personal_links.txt"
ACTIVITY_LOG = "activity_log.txt"
TARGET_COUNTRIES = ['BY', 'KZ', 'PL', 'CH', 'SE', 'DE', 'US']
OUTPUT_FILE = "my_stable_configs.txt"

GEOIP_URL = "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb"
GEOIP_FILENAME = "GeoLite2-Country.mmdb"

THREADS = 100
TIMEOUT = 1.2

def download_geoip_with_retry(retries=3):
    """Downloads GeoIP database with retry logic"""
    if os.path.exists(GEOIP_FILENAME):
        print("✅ GeoIP database is already present.")
        return True
    
    for i in range(retries):
        try:
            print(f"🌐 Downloading GeoIP (Attempt {i+1})...")
            response = requests.get(GEOIP_URL, stream=True, timeout=30)
            response.raise_for_status()
            with open(GEOIP_FILENAME, 'wb') as f:
                f.write(response.content)
            print("✅ GeoIP database downloaded successfully.")
            return True
        except Exception as e:
            print(f"⚠️ Download failed: {e}")
            time.sleep(5)
    return False

def get_ip_from_host(host):
    try:
        return socket.gethostbyname(host)
    except:
        return None

def check_tcp_port(ip, port):
    try:
        with socket.create_connection((ip, int(port)), timeout=TIMEOUT):
            return True
    except:
        return False

def extract_host_port(config):
    try:
        if "@" in config:
            address_part = config.split("@")[1].split("?")[0].split("#")[0]
            if ":" in address_part:
                host, port = address_part.split(":")[:2]
                return host.strip(), port.strip()
    except:
        pass
    return None, None

def decode_content(content):
    try:
        if "://" not in content[:20]:
            return base64.b64decode(content).decode('utf-8')
    except:
        pass
    return content

def process_config(config, reader):
    config = config.strip()
    if not config or len(config) < 10: return None
    
    host, port = extract_host_port(config)
    if not host or not port: return None

    ip = host if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host) else get_ip_from_host(host)
    if not ip: return None

    try:
        geo_data = reader.get(ip)
        country_code = geo_data.get('country', {}).get('iso_code')
    except:
        country_code = None

    if country_code not in TARGET_COUNTRIES: return None
    if not check_tcp_port(ip, port): return None

    base_url = config.split("#")[0]
    final_name = f"[{country_code}]_Verified_{ip}"
    return {"id": f"{ip}:{port}", "data": f"{base_url}#{final_name}"}

def update_activity_log(count):
    """Updates activity log to keep GitHub Actions awake"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ACTIVITY_LOG, "w", encoding="utf-8") as f:
        f.write(f"Last Check: {now}\nFound Alive: {count}\nStatus: Active")

def main():
    print("🚀 Starting HEAVY-DUTY WORKER v3.2 [Anti-Stall Mode]...")
    if not download_geoip_with_retry():
        print("🛑 Failed to load database. Exiting.")
        return

    reader = maxminddb.open_database(GEOIP_FILENAME)
    all_raw_configs = []

    # 1. Global sources
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=15)
            decoded = decode_content(r.text)
            all_raw_configs.extend([l.strip() for l in decoded.splitlines() if l.strip()])
        except:
            print(f"⚠️ Skipping source: {url[:30]}")

    # 2. Personal dump file
    if not os.path.exists(PERSONAL_LINKS_FILE):
        with open(PERSONAL_LINKS_FILE, "w", encoding="utf-8") as f:
            f.write("# Throw your links or raw vless/trojan configs here!\n")
        print(f"📝 Created {PERSONAL_LINKS_FILE}")
    else:
        try:
            with open(PERSONAL_LINKS_FILE, "r", encoding="utf-8") as f:
                for line in f.read().splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    if line.startswith("http"):
                        try:
                            r = requests.get(line, timeout=10)
                            all_raw_configs.extend([l.strip() for l in decode_content(r.text).splitlines() if l.strip()])
                        except: pass
                    else:
                        all_raw_configs.append(line)
        except: pass

    # 3. Processing
    results = {}
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = [executor.submit(process_config, cfg, reader) for cfg in all_raw_configs]
        for future in as_completed(futures):
            res = future.result()
            if res and res['id'] not in results:
                results[res['id']] = res['data']

    # 4. Saving & Pulsing
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(results.values()))

    update_activity_log(len(results))
    reader.close()
    print(f"🏁 Success! Saved: {len(results)}")

if __name__ == "__main__":
    main()
