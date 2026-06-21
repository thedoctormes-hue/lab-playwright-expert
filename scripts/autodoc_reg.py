#!/usr/bin/env python3
"""Find registration endpoints in autodoc.ru Angular chunks"""

import re

import requests


session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

all_chunks = [
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

for chunk_name in all_chunks:
    url = f"https://www.autodoc.ru/{chunk_name}.js"
    try:
        r = session.get(url, timeout=3)
        if r.status_code != 200:
            continue
        js = r.text
        if "regist" not in js.lower():
            continue
        print(f"=== {chunk_name} ({len(js)} bytes) ===")

        # Find API paths
        pat = re.compile(r'"(/api/[^"]{5,150})"')
        for m in pat.finditer(js):
            val = m.group(1)
            if "regist" in val.lower() or "activat" in val.lower():
                print(f"  path: {val}")

        pat2 = re.compile(r"'(/api/[^']{5,150})'")
        for m in pat2.finditer(js):
            val = m.group(1)
            if "regist" in val.lower() or "activat" in val.lower():
                print(f"  path: {val}")

        # Find registration-related method calls
        idx = 0
        while True:
            idx = js.lower().find("registration", idx)
            if idx < 0:
                break
            ctx = js[max(0, idx - 50) : idx + 200]
            m = re.search(r"(\w+)\s*\(", ctx[max(0, 50) :])
            if m:
                print(f"  method: {m.group(1)}()")
            idx += 10

        # Find register/activate/verify methods by name
        for term in ["register", "activate", "confirmEmail", "confirmPhone", "sendSms"]:
            idx = js.lower().find(term.lower())
            if idx >= 0:
                ctx = js[max(0, idx - 30) : idx + 150]
                if "/api/" in ctx or "http" in ctx:
                    print(f"  {term}: {ctx[:200]}")

        print()
    except Exception:
        pass
