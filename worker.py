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

    "https://raw.githubusercontent.com/V2Ray-Flags/V2Ray-Flags/main/V2Ray-Flags.txt"
]

# File paths
PERSONAL_LINKS_FILE = "my_personal_links.txt"
ACTIVITY_LOG = "activity_log.txt"
OUTPUT_FILE = "my_stable_configs.txt"
BY_FILE = "BY_stable.txt"
KZ_FILE = "KZ_stable.txt"
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

# Глобальные счетчики для реал-тайм отчета
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
    """Загрузка кэша прокси с проверкой 3-дневного цикла."""
    if not os.path.exists(CACHE_FILE):
        print(f"[CACHE] 🆕 Файл {CACHE_FILE} не найден. Будет создан новый.")
        return {"start_date": datetime.now().isoformat(), "data": {}}
    
    try:
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
        
        start_date = datetime.fromisoformat(cache.get("start_date", datetime.now().isoformat()))
        if datetime.now() - start_date > timedelta(days=3):
            print("[CACHE] 🔄 Цикл завершен (3 дня). Очистка старой памяти...")
            return {"start_date": datetime.now().isoformat(), "data": {}}
            
        return cache
    except Exception as e:
        print(f"[CACHE] ⚠️ Ошибка загрузки: {e}")
        return {"start_date": datetime.now().isoformat(), "data": {}}

def save_cache(cache_data):
    """Сохранение текущих состояний прокси в кэш."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)
            f.flush()
        print(f"✅ [CACHE] Память сохранена in {CACHE_FILE}")
    except Exception as e:
        print(f"[CACHE] ⚠️ Ошибка сохранения: {e}")

# --- CORE FUNCTIONS ---
def download_geoip_with_retry(retries=3):
    """Скачивание базы GeoIP с проверкой существования и повторами."""
    if os.path.exists(GEOIP_FILENAME):
        print("✅ [GEOIP] База уже на месте.")
        return True
    
    for i in range(retries):
        try:
            print(f"🌐 [GEOIP] Загрузка базы (Попытка {i+1})...")
            response = requests.get(GEOIP_URL, stream=True, timeout=30)
            response.raise_for_status()
            with open(GEOIP_FILENAME, 'wb') as f:
                f.write(response.content)
            print("✅ [GEOIP] База успешно скачана.")
            return True
        except Exception as e:
            print(f"⚠️ [GEOIP] Сбой загрузки: {e}")
            if i < retries - 1:
                time.sleep(5)
    return False

def get_ip_from_host(host):
    """Резолвинг домена в IP адрес."""
    try:
        clean_host = host.strip()
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", clean_host):
            return clean_host
        return socket.gethostbyname(clean_host)
    except:
        return None

def check_tcp_port(ip, port):
    """Проверка доступности TCP порта."""
    try:
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(TIMEOUT)
            s.connect((ip, int(port)))
            return True
    except:
        return False

def extract_host_port(config):
    """Универсальный экстрактор данных для VLESS, VMess, Trojan, SS."""
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
    """Декодирование Base64 содержимого подписки."""
    try:
        # Пытаемся понять, это Base64 или уже открытый текст
        if "://" not in content[:50]:
            return base64.b64decode(content).decode('utf-8')
    except: pass
    return content

def process_config(config, reader, cached_data):
    """Основная логика фильтрации и проверки конфига."""
    global processed_count, alive_found, dead_found, skipped_cache, dns_fail, wrong_country
    
    config = config.strip()
    if not config or "://" not in config: return None

    # Поиск упоминания BY для отладки
    is_claimed_by = "BY" in config.upper() or "BELARUS" in config.upper()
    
    host, port, proto = extract_host_port(config)
    if not host or not port: return None

    fingerprint = f"{host}:{port}:{proto}"
    
    # 1. DNS Резолвинг
    ip = get_ip_from_host(host)
    if not ip: 
        with stats_lock: 
            processed_count += 1
            dns_fail += 1
        progress = (processed_count / total_configs_to_check) * 100
        if is_claimed_by:
            print(f"🕵️‍♂️ [TRACE_BY] DNS СБОЙ: Не могу найти IP для {host}")
        else:
            print(f"🚫 [{progress:.1f}%] [DNS_FAIL] {host} -> 0")
        return None

    # 2. Определение страны СТРОГО по IP
    try:
        geo_data = reader.get(ip)
        country_code = str(geo_data.get('country', {}).get('iso_code', 'UN')).upper()
    except:
        country_code = "UN"

    # 3. Проверка кэша
    if fingerprint in cached_data:
        if cached_data[fingerprint]["status"] == "dead":
            with stats_lock: 
                processed_count += 1
                skipped_cache += 1
            progress = (processed_count / total_configs_to_check) * 100
            print(f"💾 [{progress:.1f}%] [CACHE_SKIP] {ip}:{port} -> 0")
            return {"status": "skipped"}

    # 4. Фильтр по странам
    if country_code not in TARGET_COUNTRIES:
        with stats_lock: 
            processed_count += 1
            wrong_country += 1
        progress = (processed_count / total_configs_to_check) * 100
        
        if is_claimed_by:
            print(f"🕵️‍♂️ [TRACE_BY] ГЕО СБОЙ: В конфиге BY, а по базе IP ({ip}) это {country_code}")
        else:
            print(f"🌍 [{progress:.1f}%] [WRONG_GEO] {country_code} | {ip}:{port} -> 0")
        return None
    
    # 5. Проверка TCP порта
    is_alive = check_tcp_port(ip, port)
    
    with stats_lock:
        processed_count += 1
        if is_alive: alive_found += 1
        else: dead_found += 1
    
    # Обновляем состояние в памяти
    cached_data[fingerprint] = {
        "status": "alive" if is_alive else "dead",
        "time": datetime.now().isoformat(),
        "ip": ip,
        "country": country_code
    }

    # Логирование в реальном времени
    progress = (processed_count / total_configs_to_check) * 100
    if is_alive:
        print(f"✨ [{progress:.1f}%] [FOUND] {country_code} | {proto} | {ip}:{port}")
    else:
        print(f"❌ [{progress:.1f}%] [DEAD] {country_code} | {proto} | {ip}:{port} -> 0")

    if not is_alive: 
        return None

    # 6. Формирование нового названия
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
    """Запись расширенной статистики в лог активности."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(ACTIVITY_LOG, "a", encoding="utf-8") as f:
            log_line = (f"[{now}] Живых: {found} | Мертвых: {dead} | Кэш: {skipped} | "
                        f"DNS_Fail: {dns} | Wrong_Geo: {geo}\n")
            f.write(log_line)
    except: pass

def main():
    global total_configs_to_check, processed_count, alive_found, dead_found, skipped_cache, dns_fail, wrong_country
    
    print("🚀 --- MEGA WORKER V4.4 [FULL TRACE MODE] ---")
    start_time = time.time()

    # Инициализация ресурсов
    if not download_geoip_with_retry(): return

    reader = maxminddb.open_database(GEOIP_FILENAME)
    cache = load_cache()
    cached_data = cache["data"]
    initial_cache_size = len(cached_data)
    
    try:
        all_raw_configs = []
        
        # Сбор данных из облачных источников
        print(f"📡 --- ФАЗА СБОРА: {len(SOURCES)} ИСТОЧНИКОВ ---")
        for idx, url in enumerate(SOURCES, 1):
            try:
                start_fetch = time.time()
                r = requests.get(url, timeout=15)
                decoded = decode_content(r.text)
                lines = [l.strip() for l in decoded.splitlines() if l.strip()]
                
                # Фильтруем только то, что похоже на прокси ссылки
                valid_links = [l for l in lines if "://" in l]
                
                all_raw_configs.extend(valid_links)
                
                fetch_time = time.time() - start_fetch
                print(f"🔗 [{idx:02}] {url[:60]}... | Найдено: {len(valid_links)} (из {len(lines)} строк) | {fetch_time:.1f}s")
            except Exception as e:
                print(f"❌ [{idx:02}] Ошибка источника {url[:40]}: {str(e)[:50]}")

        # Сбор из личных ссылок
        if os.path.exists(PERSONAL_LINKS_FILE):
            print(f"\n📖 --- ФАЗА СБОРА: ЛИЧНЫЕ ССЫЛКИ ({PERSONAL_LINKS_FILE}) ---")
            with open(PERSONAL_LINKS_FILE, "r", encoding="utf-8") as f:
                personal_lines = f.read().splitlines()
                personal_count = 0
                for line in personal_lines:
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    
                    if line.startswith("http"):
                        try:
                            r = requests.get(line, timeout=15)
                            content = decode_content(r.text)
                            links = [l.strip() for l in content.splitlines() if "://" in l]
                            all_raw_configs.extend(links)
                            personal_count += len(links)
                            print(f"📁 Подписка из файла: {line[:50]}... | Найдено: {len(links)}")
                        except: pass
                    else: 
                        all_raw_configs.append(line)
                        personal_count += 1
                print(f"✅ Итого из личных источников добавлено: {personal_count}")

        raw_count = len(all_raw_configs)
        unique_candidates = list(set(all_raw_configs))
        duplicates_count = raw_count - len(unique_candidates)
        total_configs_to_check = len(unique_candidates)
        
        print(f"\n📦 --- ИТОГИ СБОРА ---")
        print(f"📦 Всего загружено строк-ссылок: {raw_count}")
        print(f"👯 Удалено дубликатов: {duplicates_count}")
        print(f"📊 Изначально в кэше: {initial_cache_size} записей")
        print(f"🔍 К проверке (уникальных): {total_configs_to_check}")
        
        results_list = []
        seen_ids = set()
        
        print(f"\n🛠️  Запуск проверки в {THREADS} потоков...")
        with ThreadPoolExecutor(max_workers=THREADS) as executor:
            future_tasks = [executor.submit(process_config, cfg, reader, cached_data) for cfg in unique_candidates]
            for future in as_completed(future_tasks):
                res = future.result()
                if res and res.get("status") == "success" and res['id'] not in seen_ids:
                    seen_ids.add(res['id'])
                    results_list.append(res)

        # Фаза сортировки и записи
        results_list.sort(key=lambda x: x['country'])
        
        by_configs = [r['data'] for r in results_list if r['country'] == 'BY']
        kz_configs = [r['data'] for r in results_list if r['country'] == 'KZ']
        other_configs = [r['data'] for r in results_list if r['country'] not in ['BY', 'KZ']]
        all_configs = [r['data'] for r in results_list]

        print("\n🏁 --- ФИНАЛЬНЫЙ ОТЧЕТ ПО ЗАПИСИ ---")
        
        def safe_write(filename, data_list):
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write("\n".join(data_list))
                    f.flush()
                    os.fsync(f.fileno())
                print(f"💾 [FILE] {filename:18} | Записано: {len(data_list):4} шт.")
            except Exception as e:
                print(f"❌ [ERROR] Ошибка записи {filename}: {e}")

        safe_write(OUTPUT_FILE, all_configs)
        safe_write(BY_FILE, by_configs)
        safe_write(KZ_FILE, kz_configs)

        # Обновление статуса для UI/Actions
        status_data = {
            "last_run": datetime.now().isoformat(),
            "total_alive": len(all_configs),
            "by": len(by_configs),
            "kz": len(kz_configs),
            "cache_skipped": skipped_cache,
            "dead_total": dead_found,
            "dns_fail": dns_fail,
            "wrong_geo": wrong_country,
            "initial_cache_size": initial_cache_size,
            "duplicates_removed": duplicates_count
        }
        with open(STATUS_FILE, "w") as f:
            json.dump(status_data, f)

        update_activity_log(len(all_configs), skipped_cache, dead_found, dns_fail, wrong_country)
        
        duration = time.time() - start_time
        print(f"\n📊 СУММАРНАЯ СТАТИСТИКА:")
        print(f"✅ Всего живых: {len(all_configs)}")
        print(f"🇧🇾 Беларусь (BY): {len(by_configs)}")
        print(f"🇰🇿 Казахстан (KZ): {len(kz_configs)}")
        print(f"🌍 Другие страны: {len(other_configs)}")
        print(f"------------------------------------")
        print(f"❌ Мертвых (TCP): {dead_found}")
        print(f"💾 Кэш (Скип): {skipped_cache}")
        print(f"🌐 DNS Ошибки: {dns_fail}")
        print(f"🚫 Нецелевые ГЕО: {wrong_country}")
        print(f"🔄 Обработано: {processed_count} из {total_configs_to_check}")
        print(f"⏱️  ВРЕМЯ РАБОТЫ: {duration:.1f} сек.")

    except Exception as e:
        print(f"🚨 [FATAL ERROR] {e}")
    finally:
        save_cache(cache)
        reader.close()

if __name__ == "__main__":
    main()
