import re
import requests
import base64
import socket
import os
import time
import json
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import maxminddb

# --- CONFIGURATION (MEGA SOURCES) ---
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
STATUS_FILE = "status.json"

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
THREADS = 150 
TIMEOUT = 2.5 

# Global counters for real-time reporting
stats_lock = threading.Lock()
processed_count = 0
total_configs_to_check = 0
alive_found = 0
dead_found = 0
skipped_cache = 0
dns_fail = 0
wrong_country = 0

# --- SMART CACHE LOGIC ---
def load_cache():
    """Load proxy cache with 3-day cycle check."""
    if not os.path.exists(CACHE_FILE):
        print(f"[CACHE] 🆕 File {CACHE_FILE} not found. Creating new.")
        return {"start_date": datetime.now().isoformat(), "data": {}}
    
    try:
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
        
        start_date = datetime.fromisoformat(cache.get("start_date", datetime.now().isoformat()))
        if datetime.now() - start_date > timedelta(days=3):
            print("[CACHE] 🔄 Cycle finished (3 days). Clearing old memory...")
            return {"start_date": datetime.now().isoformat(), "data": {}}
            
        return cache
    except Exception as e:
        print(f"[CACHE] ⚠️ Load error: {e}")
        return {"start_date": datetime.now().isoformat(), "data": {}}

def save_cache(cache_data):
    """Atomically save current proxy states to cache."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        print(f"✅ [CACHE] Memory saved in {CACHE_FILE}")
    except Exception as e:
        print(f"[CACHE] ⚠️ Save error: {e}")

# --- CORE FUNCTIONS ---
def download_geoip_with_retry(retries=3):
    """Download GeoIP database with existence check and retries."""
    if os.path.exists(GEOIP_FILENAME):
        print("✅ [GEOIP] Database is already present.")
        return True
    
    for i in range(retries):
        try:
            print(f"🌐 [GEOIP] Downloading database (Attempt {i+1})...")
            response = requests.get(GEOIP_URL, stream=True, timeout=30)
            response.raise_for_status()
            with open(GEOIP_FILENAME, 'wb') as f:
                f.write(response.content)
            print("✅ [GEOIP] Database successfully downloaded.")
            return True
        except Exception as e:
            print(f"⚠️ [GEOIP] Download failed: {e}")
            if i < retries - 1:
                time.sleep(5)
    return False

def get_ip_from_host(host):
    """Resolve domain to IP address."""
    try:
        clean_host = host.strip()
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", clean_host):
            return clean_host
        return socket.gethostbyname(clean_host)
    except:
        return None

def check_tcp_port(ip, port):
    """Check TCP port availability."""
    try:
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(TIMEOUT)
            s.connect((ip, int(port)))
            return True
    except:
        return False

def extract_host_port(config):
    """Universal data extractor for VLESS, VMess, Trojan, SS."""
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
            if ":" in encoded_part and "@" not in encoded_part: 
                 parts = encoded_part.split(":")
                 return parts[0].strip(), parts[1].strip(), "SS"
            
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
    """Decode Base64 content of subscription."""
    try:
        if "://" not in content[:50]:
            return base64.b64decode(content).decode('utf-8')
    except: pass
    return content

def process_config(config, reader, cached_data):
    """Core logic for filtering and checking config with Total Caching."""
    global processed_count, alive_found, dead_found, skipped_cache, dns_fail, wrong_country
    
    config = config.strip()
    if not config or "://" not in config: return None

    # TRACE LOGIC: Check if this config is a suspected target
    is_target_trace = any(x in config.upper() for x in ["BY", "BELARUS", "KZ", "KAZAKHSTAN"])
    
    host, port, proto = extract_host_port(config)
    if not host or not port: return None

    fingerprint = f"{host}:{port}:{proto}"
    
    # 1. Total Cache Check
    if fingerprint in cached_data:
        entry = cached_data[fingerprint]
        
        if entry["status"] == "dead":
            with stats_lock: 
                processed_count += 1
                skipped_cache += 1
            return {"status": "skipped"}
        
        if entry["status"] == "alive":
            country_code = str(entry.get("country", "UN")).strip().upper()
            ip = entry.get("ip", host)
            
            with stats_lock:
                processed_count += 1
                alive_found += 1
                skipped_cache += 1 
            
            flag = COUNTRY_FLAGS.get(country_code, '🌐')
            base_url = config.split("#")[0]
            final_name = f"{flag} [{country_code}] {proto} | {ip}"
            
            # TRACE: Log cached hits for BY/KZ
            if is_target_trace or country_code in ['BY', 'KZ']:
                print(f"🕵️‍♂️ [TRACE_CACHE] {country_code} | {ip} found in memory. Returning to list.")
            
            return {
                "id": fingerprint, 
                "country": country_code, 
                "data": f"{base_url}#{final_name}",
                "status": "success"
            }

    # 2. DNS Resolving
    ip = get_ip_from_host(host)
    if not ip: 
        with stats_lock: 
            processed_count += 1
            dns_fail += 1
        return None

    # 3. Country detection STRICTLY by IP
    try:
        geo_data = reader.get(ip)
        country_code = str(geo_data.get('country', {}).get('iso_code', 'UN')).strip().upper()
    except:
        country_code = "UN"

    # 4. Country filter
    if country_code not in TARGET_COUNTRIES:
        with stats_lock: 
            processed_count += 1
            wrong_country += 1
        
        if is_target_trace:
             print(f"🕵️‍♂️ [TRACE_REJECT] Config mentioned target, but IP ({ip}) is in {country_code}")
        return None
    
    # 5. TCP Port check
    is_alive = check_tcp_port(ip, port)
    
    with stats_lock:
        processed_count += 1
        if is_alive: alive_found += 1
        else: dead_found += 1
        
    if is_target_trace:
        status_str = "ALIVE" if is_alive else "DEAD"
        print(f"🕵️‍♂️ [TRACE_CHECK] {country_code} | {ip}:{port} | Result: {status_str}")
    
    # Update state in memory
    cached_data[fingerprint] = {
        "status": "alive" if is_alive else "dead",
        "time": datetime.now().isoformat(),
        "ip": ip,
        "country": country_code
    }

    if not is_alive: 
        return None

    # 6. Format new name
    flag = COUNTRY_FLAGS.get(country_code, '🌐')
    base_url = config.split("#")[0]
    final_name = f"{flag} [{country_code}] {proto} | {ip}"
    
    return {
        "id": fingerprint, 
        "country": country_code, 
        "data": f"{base_url}#{final_name}",
        "status": "success"
    }

def update_activity_log(found, skipped, dead, dns, geo):
    """Write extended statistics to activity log."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(ACTIVITY_LOG, "a", encoding="utf-8") as f:
            log_line = (f"[{now}] Alive: {found} | Dead: {dead} | Cache_Hit: {skipped} | "
                        f"DNS_Fail: {dns} | Wrong_Geo: {geo}\n")
            f.write(log_line)
    except: pass

def main():
    global total_configs_to_check, processed_count, alive_found, dead_found, skipped_cache, dns_fail, wrong_country
    
    print("🚀 --- MEGA WORKER V4.4 [DEBUG TRACE ENABLED] ---")
    start_time = time.time()

    if not download_geoip_with_retry(): return

    reader = maxminddb.open_database(GEOIP_FILENAME)
    cache = load_cache()
    cached_data = cache["data"]
    
    try:
        all_raw_configs = []
        
        # 1. Cloud sources
        print(f"📡 --- COLLECTION PHASE ---")
        for idx, url in enumerate(SOURCES, 1):
            try:
                r = requests.get(url, timeout=15)
                decoded = decode_content(r.text)
                lines = [l.strip() for l in decoded.splitlines() if l.strip()]
                valid_links = [l for l in lines if "://" in l]
                all_raw_configs.extend(valid_links)
            except: pass

        # 2. Personal links
        if os.path.exists(PERSONAL_LINKS_FILE):
            with open(PERSONAL_LINKS_FILE, "r", encoding="utf-8") as f:
                personal_lines = f.read().splitlines()
                for line in personal_lines:
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    if line.startswith("http"):
                        try:
                            r = requests.get(line, timeout=15)
                            content = decode_content(r.text)
                            links = [l.strip() for l in content.splitlines() if "://" in l]
                            all_raw_configs.extend(links)
                        except: pass
                    else: 
                        all_raw_configs.append(line)

        unique_candidates = list(set(all_raw_configs))
        total_configs_to_check = len(unique_candidates)
        
        print(f"🔍 Candidates: {total_configs_to_check}")
        
        results_list = []
        seen_ids = set()
        
        with ThreadPoolExecutor(max_workers=THREADS) as executor:
            future_tasks = [executor.submit(process_config, cfg, reader, cached_data) for cfg in unique_candidates]
            for future in as_completed(future_tasks):
                res = future.result()
                if res and res.get("status") == "success" and res['id'] not in seen_ids:
                    seen_ids.add(res['id'])
                    results_list.append(res)

        # 3. SPLIT LOGIC & DEBUG
        print("\n📂 --- FINAL DISTRIBUTION AUDIT ---")
        by_configs = [r['data'] for r in results_list if r['country'] == 'BY']
        kz_configs = [r['data'] for r in results_list if r['country'] == 'KZ']
        
        # Explicit trace of found targets
        if by_configs:
            print("🇧🇾 [BY] Found IPs:")
            for b in by_configs: print(f"  -> {b.split('| ')[-1]}")
        else:
            print("🇧🇾 [BY] No configs passed all filters.")

        if kz_configs:
            print("🇰🇿 [KZ] Found IPs:")
            for k in kz_configs: print(f"  -> {k.split('| ')[-1]}")
        else:
            print("🇰🇿 [KZ] No configs passed all filters.")
        
        results_list.sort(key=lambda x: x['country'])
        all_configs = [r['data'] for r in results_list]

        def safe_write(filename, data_list):
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    if data_list:
                        f.write("\n".join(data_list) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                print(f"💾 [FILE] {filename:18} | Count: {len(data_list):4}")
            except Exception as e:
                print(f"❌ [ERROR] Write {filename}: {e}")

        safe_write(OUTPUT_FILE, all_configs)
        safe_write(BY_FILE, by_configs)
        safe_write(KZ_FILE, kz_configs)

        update_activity_log(len(all_configs), skipped_cache, dead_found, dns_fail, wrong_country)
        
        duration = time.time() - start_time
        print(f"\n✅ Total Alive: {len(all_configs)} | Time: {duration:.1f}s")

    except Exception as e:
        print(f"🚨 [FATAL ERROR] {e}")
    finally:
        save_cache(cache)
        reader.close()

if __name__ == "__main__":
    main()
