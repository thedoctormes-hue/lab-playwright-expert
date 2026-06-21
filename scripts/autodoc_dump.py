#!/usr/bin/env python3
import re

import requests


session = requests.Session()
session.headers.update(
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
)


def extract_api_strings(js_content):
    paths = set()
    pat_dq = re.compile(r'"(/api/[^"]{5,150})"')
    pat_sq = re.compile(r"'(/api/[^']{5,150})'")
    pat_bt = re.compile(r"`([^`]*?/api/[^`]{5,150})`")

    for m in pat_dq.finditer(js_content):
        paths.add(m.group(1))
    for m in pat_sq.finditer(js_content):
        paths.add(m.group(1))
    for m in pat_bt.finditer(js_content):
        val = m.group(1)
        val = re.sub(r"\$\{[^}]+\}", "{PARAM}", val)
        paths.add(val)
    return paths


all_chunk_names = [
    "chunk-5QJCMKPC",
    "chunk-B66DIMZY",
    "chunk-N3JZCHXD",
    "chunk-PEUL7JDQ",
    "chunk-CCODNV6U",
    "chunk-YOI2KHL5",
    "chunk-MXTVMIAQ",
    "chunk-QQ4UYSAE",
    "chunk-O3I7W3OU",
    "chunk-DCGINGWC",
    "chunk-KWMK24OK",
    "chunk-7RTFUKEY",
    "chunk-VT6ZJTMR",
    "chunk-7GAMY5XC",
    "chunk-7ULCFDOO",
    "chunk-E3MVBSCW",
    "chunk-TLB7QGW3",
    "chunk-JMARNVUS",
    "chunk-35HYEUOB",
    "chunk-SQ24CFCR",
    "chunk-6W6ZSLHJ",
    "chunk-RKAOGDCW",
    "chunk-FJUURWYC",
    "chunk-VLCC3GAQ",
    "chunk-JFQ7YHLO",
    "chunk-AWOYV4A2",
    "chunk-PFFAROLH",
    "chunk-72SPQECO",
    "chunk-FKT6TRBA",
    "chunk-5YBZVOYK",
    "chunk-37TSTKWJ",
    "chunk-R54VH5Q3",
    "chunk-RMQAHXEN",
    "chunk-CXVJRU2Y",
    "chunk-VGXG6QHA",
    "chunk-VEL2SGPX",
    "chunk-2GEDNSLX",
    "chunk-AUS2443D",
    "chunk-KJQUYSUE",
    "chunk-ZVHVBNX6",
    "chunk-P72PQFL2",
    "chunk-PTOGFEH4",
    "chunk-DCWI3RY2",
    "chunk-XKMKHFKN",
    "chunk-AVH5UUMU",
]

all_paths = set()
loaded = 0
failed = 0

for name in all_chunk_names:
    url = f"https://www.autodoc.ru/{name}.js"
    try:
        r = session.get(url, timeout=5)
        if r.status_code == 200:
            loaded += 1
            paths = extract_api_strings(r.text)
            all_paths.update(paths)
        else:
            failed += 1
    except Exception:
        failed += 1

print(f"Loaded: {loaded}, Failed: {failed}")
print(f"Total unique API paths: {len(all_paths)}")

for p in sorted(all_paths):
    print(f"  {p}")

# Test endpoints
print("\n=== TESTING PRICE ENDPOINTS ===")
base = "https://web.autodoc.ru"
interesting = [
    p
    for p in sorted(all_paths)
    if any(
        k in p
        for k in [
            "price",
            "goods",
            "good",
            "offer",
            "catalog",
            "analogue",
            "stock",
            "availability",
            "brand",
        ]
    )
]

for path in interesting:
    test_path = path.replace("{PARAM}", "34")
    if "?" in test_path:
        url = f"{base}{test_path}&article=OC471&manufacturerId=34"
    else:
        url = f"{base}{test_path}?article=OC471&manufacturerId=34"
    try:
        r = session.get(url, timeout=3)
        status = r.status_code
        body = r.text[:200] if r.text else ""
        if status == 200 and len(body) > 5:
            print(f"[200] {url}")
            print(f"  {body}")
        elif status == 401:
            print(f"[401 AUTH] {url}")
        elif status not in (404, 405):
            print(f"[{status}] {url} -> {body[:80]}")
    except Exception:
        pass
