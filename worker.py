import re
import requests
import base64
import socket
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import maxminddb

# --- CONFIGURATION & SOURCES ---
# Global automated sources
SOURCES = [
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt",
    "https://raw.githubusercontent.com/freev2rayspeed/v2ray/main/v2ray.txt",
    "https://raw.githubusercontent.com/aiboboxx/v2rayfree/main/v2ray",
    "https://raw.githubusercontent.com/vpei/free-v2ray-config/master/v2ray.txt",
    "https://raw.githubusercontent.com/tbbatbb/Proxy/master/dist/v2ray.config",
    "https://raw.githubusercontent.com/StayHu/v2ray/master/v2ray.txt"
]

# Personal file for "dumping" links or raw configs
PERSONAL_LINKS_FILE = "my_personal_links.txt"

# Target countries (ISO Codes)
TARGET_COUNTRIES = ['BY', 'KZ', 'PL', 'CH', 'SE', 'DE', 'US']
OUTPUT_FILE = "my_stable_configs.txt"

# GeoIP settings
GEOIP_URL = "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb"
GEOIP_FILENAME = "GeoLite2-Country.mmdb"

# Performance settings
THREADS = 100
TIMEOUT = 1.2

def download_geoip():
    """Download local GeoIP database if it does not exist"""
    if not os.path.exists(GEOIP_FILENAME):
        print(f"🌐 Database missing. Downloading GeoIP MMDB...")
        try:
            response = requests.get(GEOIP_URL, stream=True, timeout=20)
            response.raise_for_status()
            with open(GEOIP_FILENAME, 'wb') as f:
                f.write(response.content)
            print("✅ GeoIP database downloaded.")
        except Exception as e:
            print(f"❌ Failed to download GeoIP: {e}")

def get_ip_from_host(host):
    """Resolve domain name to IP address"""
    try:
        return socket.gethostbyname(host)
    except:
        return None

def check_tcp_port(ip, port):
    """Verify if the port is reachable via TCP"""
    try:
        with socket.create_connection((ip, int(port)), timeout=TIMEOUT):
            return True
    except:
        return False

def extract_host_port(config):
    """Parse proxy URL to extract host and port"""
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
    """Attempt to decode content if it's Base64, otherwise return as is"""
    try:
        # Simple check: if it doesn't look like a standard proxy URL, try base64
        if "://" not in content[:20]:
            return base64.b64decode(content).decode('utf-8')
    except:
        pass
    return content

def process_config(config, reader):
    """Full processing cycle: parsing, resolving, geo-checking, and port-checking"""
    config = config.strip()
    if not config or len(config) < 10:
        return None

    host, port = extract_host_port(config)
    if not host or not port:
        return None

    # Determine IP address
    ip = host if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host) else get_ip_from_host(host)
    if not ip:
        return None

    # 1. GeoIP Check (Local MMDB)
    try:
        geo_data = reader.get(ip)
        country_code = geo_data.get('country', {}).get('iso_code')
    except:
        country_code = None

    if country_code not in TARGET_COUNTRIES:
        return None

    # 2. Alive Check (TCP Ping)
    if not check_tcp_port(ip, port):
        return None

    # 3. Success: Format and Tag
    base_url = config.split("#")[0]
    final_name = f"[{country_code}]_Exp_{ip}"
    return {
        "fingerprint": f"{ip}:{port}",
        "data": f"{base_url}#{final_name}"
    }

def main():
    print("🚀 Starting HEAVY-DUTY AGGREGATOR v3.0...")
    download_geoip()
    
    if not os.path.exists(GEOIP_FILENAME):
        print("🛑 Critical Error: GeoIP file missing.")
        return

    reader = maxminddb.open_database(GEOIP_FILENAME)
    all_raw_configs = []

    # --- PART 1: Fetch Global Sources ---
    print(f"📡 Processing {len(SOURCES)} global sources...")
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=15)
            decoded = decode_content(r.text)
            lines = decoded.splitlines()
            all_raw_configs.extend([l.strip() for l in lines if l.strip()])
            print(f"✅ Fetched {len(lines)} from {url[:40]}...")
        except Exception as e:
            print(f"⚠️ Failed to fetch global source {url[:30]}: {e}")

    # --- PART 2: Fetch Personal Dump File ---
    if os.path.exists(PERSONAL_LINKS_FILE):
        print(f"📂 Processing personal dump: {PERSONAL_LINKS_FILE}...")
        try:
            with open(PERSONAL_LINKS_FILE, "r", encoding="utf-8") as f:
                personal_content = f.read()
                
                # Check each line: is it a URL or a direct config?
                for line in personal_content.splitlines():
                    line = line.strip()
                    if not line: continue
                    
                    if line.startswith("http"):
                        # If it's a URL, fetch it
                        try:
                            r = requests.get(line, timeout=10)
                            decoded = decode_content(r.text)
                            all_raw_configs.extend([l.strip() for l in decoded.splitlines() if l.strip()])
                        except:
                            print(f"⚠️ Failed to fetch personal URL: {line[:40]}")
                    else:
                        # If it's already a config (vless:// etc), add directly
                        all_raw_configs.append(line)
            print("✅ Personal dump integrated.")
        except Exception as e:
            print(f"⚠️ Error reading personal file: {e}")
    else:
        # Create the file if it doesn't exist so Boss can see it
        with open(PERSONAL_LINKS_FILE, "w", encoding="utf-8") as f:
            f.write("# Boss, throw your links or raw vless/trojan configs here!\n")
        print(f"📝 Created empty {PERSONAL_LINKS_FILE} for your future use.")

    # --- PART 3: Multithreaded Processing ---
    print(f"📊 Total raw items to process: {len(all_raw_configs)}")
    print(f"⚙️ Multithreaded check (Workers: {THREADS})...")

    results = {}
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        future_tasks = [executor.submit(process_config, cfg, reader) for cfg in all_raw_configs]
        
        for future in as_completed(future_tasks):
            res = future.result()
            if res:
                # Strong deduplication by IP:Port
                if res['fingerprint'] not in results:
                    results[res['fingerprint']] = res['data']

    # --- PART 4: Saving Results ---
    final_list = list(results.values())
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(final_list))

    reader.close()
    print(f"🏁 DONE! Total unique live configs: {len(final_list)}")
    print(f"💾 Results saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
