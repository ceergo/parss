import re
import requests
import base64
import socket
import os
import time
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import maxminddb

# --- CONFIGURATION (MEGA SOURCES) ---
# Combined from your old code and new global sources
SOURCES = [
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt",
    "https://raw.githubusercontent.com/freev2rayspeed/v2ray/main/v2ray.txt",
    "https://raw.githubusercontent.com/aiboboxx/v2rayfree/main/v2ray",
    "https://raw.githubusercontent.com/vpei/free-v2ray-config/master/v2ray.txt",
    "https://raw.githubusercontent.com/tbbatbb/Proxy/master/dist/v2ray.config",
    "https://raw.githubusercontent.com/StayHu/v2ray/master/v2ray.txt",
    "https://raw.githubusercontent.com/Sincere-Xue/v2ray-worker/main/sub/sub_merge.txt",
    "https://raw.githubusercontent.com/LoverSe/v2ray/master/v2ray.txt",
    "https://raw.githubusercontent.com/iwxf/free-v2ray/master/0218/v2ray.txt",
    "https://raw.githubusercontent.com/erkaipl/v2ray/master/v2ray.txt",
    "https://raw.githubusercontent.com/Pawel-H-H/v2ray/master/v2ray.txt",
    "https://raw.githubusercontent.com/mfuu/v2ray/master/v2ray.txt",
    "https://raw.githubusercontent.com/yebekhe/TV2RAY/main/sub/subscription",
    "https://raw.githubusercontent.com/freefq/free/master/v2",
    "https://raw.githubusercontent.com/Paw0015/Free-Vpn-Proxy/main/links/all",
    "https://raw.githubusercontent.com/V2Ray-Flags/V2Ray-Flags/main/V2Ray-Flags.txt"
]

# File paths
PERSONAL_LINKS_FILE = "my_personal_links.txt"
ACTIVITY_LOG = "activity_log.txt"
OUTPUT_FILE = "my_stable_configs.txt"
BY_FILE = "BY_stable.txt"
KZ_FILE = "BY_stable.txt"
CACHE_FILE = "proxy_cache.json"

# Target countries (Elite Filter)
TARGET_COUNTRIES = ['BY', 'KZ', 'PL', 'CH', 'SE', 'DE', 'US', 'GB', 'FI', 'TR', 'NL', 'FR']

# Emoji Flags Dictionary
COUNTRY_FLAGS = {
    'BY': '🇧🇾', 'KZ': '🇰🇿', 'PL': '🇵🇱', 'CH': '🇨🇭', 'SE': '🇸🇪', 
    'DE': '🇩🇪', 'US': '🇺🇸', 'GB': '🇬🇧', 'FI': '🇫🇮', 'TR': '🇹🇷', 
    'NL': '🇳🇱', 'FR': '🇫🇷', 'UN': '🌐'
}

# GeoIP settings
GEOIP_URL = "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb"
GEOIP_FILENAME = "GeoLite2-Country.mmdb"

# Performance settings
THREADS = 100
TIMEOUT = 1.2

# --- SMART CACHE LOGIC ---
def load_cache():
    """Load proxy cache from JSON file with 3-day cycle check."""
    if not os.path.exists(CACHE_FILE):
        return {"start_date": datetime.now().isoformat(), "data": {}}
    
    try:
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
        
        # Check if cache is older than 3 days
        start_date = datetime.fromisoformat(cache.get("start_date", datetime.now().isoformat()))
        if datetime.now() - start_date > timedelta(days=3):
            print("[CACHE] Цикл завершен (3 дня). Сброс кэша для свежей проверки...")
            return {"start_date": datetime.now().isoformat(), "data": {}}
            
        return cache
    except Exception as e:
        print(f"[CACHE] Ошибка загрузки: {e}")
        return {"start_date": datetime.now().isoformat(), "data": {}}

def save_cache(cache_data):
    """Save current proxy states to cache."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)
    except Exception as e:
        print(f"[CACHE] Ошибка сохранения: {e}")

# --- CORE FUNCTIONS ---
def download_geoip_with_retry(retries=3):
    if os.path.exists(GEOIP_FILENAME):
        print("✅ База GeoIP найдена.")
        return True
    
    for i in range(retries):
        try:
            print(f"🌐 Загрузка GeoIP (Попытка {i+1})...")
            response = requests.get(GEOIP_URL, stream=True, timeout=30)
            response.raise_for_status()
            with open(GEOIP_FILENAME, 'wb') as f:
                f.write(response.content)
            print("✅ База GeoIP успешно загружена.")
            return True
        except Exception as e:
            print(f"⚠️ Ошибка загрузки базы: {e}")
            if i < retries - 1:
                time.sleep(5)
    return False

def get_ip_from_host(host):
    try:
        return socket.gethostbyname(host)
    except:
        return None

def check_tcp_port(ip, port):
    try:
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(TIMEOUT)
            s.connect((ip, int(port)))
            return True
    except:
        return False

def extract_host_port(config):
    """Advanced extractor from your V3.8 code."""
    try:
        if config.startswith("vmess://"):
            vmess_data = config.replace("vmess://", "")
            padding = len(vmess_data) % 4
            if padding: vmess_data += "=" * (4 - padding)
            try:
                decoded_js = json.loads(base64.b64decode(vmess_data).decode('utf-8'))
                host = decoded_js.get('add')
                port = decoded_js.get('port')
                if host and port:
                    return str(host).strip(), str(port).strip(), "VMESS"
            except: pass

        if "@" in config:
            protocol = config.split("://")[0].upper()
            address_part = config.split("@")[1].split("?")[0].split("#")[0].split("/")[0]
            
            if address_part.startswith("["):
                match = re.search(r"\[(.+)\]:(\d+)", address_part)
                if match:
                    return match.group(1), match.group(2), protocol
            
            if ":" in address_part:
                parts = address_part.split(":")
                return parts[0].strip(), parts[-1].strip(), protocol

        elif config.startswith("ss://"):
            encoded_part = config.replace("ss://", "").split("#")[0]
            padding = len(encoded_part) % 4
            if padding: encoded_part += "=" * (4 - padding)
            try:
                decoded = base64.b64decode(encoded_part).decode('utf-8', errors='ignore')
                if "@" in decoded:
                    address_part = decoded.split("@")[1].split("/")[0]
                    if ":" in address_part:
                        host, port = address_part.split(":")[:2]
                        return host.strip(), port.strip(), "SS"
            except: pass
    except: pass
    return None, None, "UNKNOWN"

def decode_content(content):
    try:
        if "://" not in content[:20]:
            return base64.b64decode(content).decode('utf-8')
    except: pass
    return content

def process_config(config, reader, cached_data):
    config = config.strip()
    if not config or len(config) < 10: return None
    
    host, port, proto = extract_host_port(config)
    if not host or not port: return None

    fingerprint = f"{host}:{port}:{proto}"
    
    # --- CACHE CHECK ---
    if fingerprint in cached_data:
        if cached_data[fingerprint]["status"] == "dead":
            return {"status": "skipped"}

    ip = host if (":" in host or re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host)) else get_ip_from_host(host)
    if not ip: 
        cached_data[fingerprint] = {"status": "dead", "time": datetime.now().isoformat()}
        return None

    # GeoIP Filter
    try:
        geo_data = reader.get(ip)
        country_code = geo_data.get('country', {}).get('iso_code', 'UN')
    except: country_code = "UN"

    if country_code not in TARGET_COUNTRIES:
        return None
    
    # TCP Check
    is_alive = check_tcp_port(ip, port)
    
    # Update Cache
    cached_data[fingerprint] = {
        "status": "alive" if is_alive else "dead",
        "time": datetime.now().isoformat()
    }

    if not is_alive: return None

    # Success!
    flag = COUNTRY_FLAGS.get(country_code, '🌐')
    base_url = config.split("#")[0]
    final_name = f"{flag} [{country_code}] {proto} | {ip}"
    return {
        "id": fingerprint, 
        "country": country_code, 
        "data": f"{base_url}#{final_name}",
        "status": "success"
    }

def update_activity_log(count, skipped):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(ACTIVITY_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{now}] Found: {count} | Skipped: {skipped} | Cycle: Active\n")
        print(f"💓 Лог обновлен: {now}")
    except: pass

def main():
    print("🚀 --- MEGA WORKER V4.1 [Smart Cache & Multi-Country] ---")
    start_time = time.time()

    if not download_geoip_with_retry(): return

    reader = maxminddb.open_database(GEOIP_FILENAME)
    cache = load_cache()
    cached_data = cache["data"]
    
    all_raw_configs = []

    # Phase 1: Global Sources
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=15)
            decoded = decode_content(r.text)
            all_raw_configs.extend([l.strip() for l in decoded.splitlines() if l.strip()])
        except: pass

    # Phase 2: Personal Links
    if os.path.exists(PERSONAL_LINKS_FILE):
        with open(PERSONAL_LINKS_FILE, "r", encoding="utf-8") as f:
            for line in f.read().splitlines():
                line = line.strip()
                if not line or line.startswith("#"): continue
                if line.startswith("http"):
                    try:
                        r = requests.get(line, timeout=10)
                        all_raw_configs.extend([l.strip() for l in decode_content(r.text).splitlines() if l.strip()])
                    except: pass
                else: all_raw_configs.append(line)

    # Phase 3: Processing
    total_raw = len(set(all_raw_configs))
    print(f"📊 Уникальных ссылок: {total_raw}")

    results_list = []
    skipped = 0
    seen_ids = set()
    
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        future_tasks = [executor.submit(process_config, cfg, reader, cached_data) for cfg in list(set(all_raw_configs))]
        for future in as_completed(future_tasks):
            res = future.result()
            if res:
                if res.get("status") == "skipped":
                    skipped += 1
                elif res.get("status") == "success" and res['id'] not in seen_ids:
                    seen_ids.add(res['id'])
                    results_list.append(res)

    # Phase 4: Sorting & Saving
    results_list.sort(key=lambda x: x['country'])
    
    by_configs = [r['data'] for r in results_list if r['country'] == 'BY']
    kz_configs = [r['data'] for r in results_list if r['country'] == 'KZ']
    all_configs = [r['data'] for r in results_list]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f: f.write("\n".join(all_configs))
    with open(BY_FILE, "w", encoding="utf-8") as f: f.write("\n".join(by_configs))
    with open(KZ_FILE, "w", encoding="utf-8") as f: f.write("\n".join(kz_configs))

    save_cache(cache)
    update_activity_log(len(all_configs), skipped)
    reader.close()
    
    duration = time.time() - start_time
    print("-" * 40)
    print(f"🏁 ФИНИШ! Найдено: {len(all_configs)} (BY: {len(by_configs)}, KZ: {len(kz_configs)})")
    print(f"🔹 Пропущено (кэш): {skipped} | Время: {duration:.1f} сек")
    print("-" * 40)

if __name__ == "__main__":
    main()
