import re
import requests
import base64
import socket
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import maxminddb # Library for local GeoIP database

# --- CONFIGURATION ---
# Sources of proxy configs
SOURCES = [
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt"
]

# Target countries for Kaliningrad and general stability
TARGET_COUNTRIES = ['BY', 'KZ', 'PL', 'CH', 'SE', 'DE', 'US']
OUTPUT_FILE = "my_stable_configs.txt"

# URL for downloading the local GeoIP database (MMDB)
GEOIP_URL = "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb"
GEOIP_FILENAME = "GeoLite2-Country.mmdb"

# Performance settings
THREADS = 60      # Number of parallel threads for checking
TIMEOUT = 1.5     # Seconds to wait for port response

def download_geoip():
    """Download local GeoIP database if it does not exist"""
    if not os.path.exists(GEOIP_FILENAME):
        print(f"🌐 Database not found. Downloading GeoIP MMDB...")
        try:
            response = requests.get(GEOIP_URL, stream=True, timeout=15)
            response.raise_for_status()
            with open(GEOIP_FILENAME, 'wb') as f:
                f.write(response.content)
            print("✅ GeoIP database downloaded successfully.")
        except Exception as e:
            print(f"❌ Failed to download GeoIP: {e}")
    else:
        print("✅ Local GeoIP database is present.")

def get_ip_from_host(host):
    """Resolve domain name to IP address"""
    try:
        return socket.gethostbyname(host)
    except:
        return None

def check_tcp_port(ip, port):
    """Attempt to open a TCP connection to verify the port is open"""
    try:
        with socket.create_connection((ip, int(port)), timeout=TIMEOUT):
            return True
    except:
        return False

def extract_host_port(config):
    """Parse proxy URL to extract host and port for checking"""
    try:
        # Removing protocol and splitting by @
        if "@" in config:
            connection_part = config.split("@")[1]
            # Removing everything after host:port (params, fragments)
            address_info = connection_part.split("?")[0].split("#")[0]
            if ":" in address_info:
                host, port = address_info.split(":")[:2]
                return host.strip(), port.strip()
    except Exception:
        pass
    return None, None

def process_config(config, reader):
    """Full cycle: parsing -> resolving -> geo-checking -> port-checking"""
    host, port = extract_host_port(config)
    if not host or not port:
        return None

    # Resolve IP if host is a domain
    ip = host if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host) else get_ip_from_host(host)
    if not ip:
        return None

    # 1. GeoIP Check (Instant local lookup)
    try:
        geo_data = reader.get(ip)
        country_code = geo_data.get('country', {}).get('iso_code')
    except Exception:
        country_code = None

    if country_code not in TARGET_COUNTRIES:
        return None

    # 2. Port Check (Active health check)
    if not check_tcp_port(ip, port):
        return None

    # 3. Success: Format the config with country tag
    clean_part = config.split("#")[0]
    # Adding a unique tag to the name
    final_config = f"{clean_part}#[{country_code}]_Live_{ip}"
    
    return {
        "fingerprint": f"{ip}:{port}",
        "data": final_config
    }

def main():
    print("🚀 Starting Extreme Professional Worker...")
    download_geoip()
    
    if not os.path.exists(GEOIP_FILENAME):
        print("🛑 Critical: Database missing. Aborting.")
        return

    # Loading the local database into memory
    reader = maxminddb.open_database(GEOIP_FILENAME)
    
    total_raw = []
    print("📡 Fetching subscriptions...")
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=10)
            text = r.text
            # Checking if the source is Base64 encoded (typical for subscriptions)
            try:
                text = base64.b64decode(text).decode('utf-8')
            except:
                pass
            total_raw.extend(text.splitlines())
        except Exception as e:
            print(f"⚠️ Source error {url}: {e}")

    print(f"📊 Total items found: {len(total_raw)}")
    print(f"⚙️ Running multithreaded check ({THREADS} threads)...")

    final_unique_configs = {}
    
    # Multithreading magic
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        # We pass a reference to the reader to each task
        future_to_cfg = {executor.submit(process_config, cfg, reader): cfg for cfg in total_raw if cfg.strip()}
        
        for future in as_completed(future_to_cfg):
            result = future.result()
            if result:
                # Deduplication by IP:Port fingerprint
                if result['fingerprint'] not in final_unique_configs:
                    final_unique_configs[result['fingerprint']] = result['data']

    # Saving only unique, live configs
    output_data = list(final_unique_configs.values())
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(output_data))

    reader.close()
    print(f"✅ Success! Saved {len(output_data)} unique live configs to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
