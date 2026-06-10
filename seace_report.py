"""
Reporte diario de compras publicas - La Libertad
Fuentes:
  1. SEACE   - REST API publica
  2. SUNARP  - HTML scraping (Zona Registral N V - Sede Trujillo)
  3. PNSR    - POST con sesion (Prog. Nacional Saneamiento Rural)
  4. MPFN    - POST con sesion (Ministerio Publico - La Libertad)

Uso:
  python seace_report.py MANANA
  python seace_report.py TARDE
"""

import requests
import sys
import re
from datetime import datetime
from bs4 import BeautifulSoup

TELEGRAM_TOKEN   = "8905726945:AAFjo4JezGkwWUowGeNZlU8lPS0KLGOwGJ8"
TELEGRAM_CHAT_ID = "8718161110"
ANIO = datetime.now().year

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ---------- Telegram --------------------------------------------------------

def send(text: str):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
        timeout=30,
    )

# ---------- 1. SEACE --------------------------------------------------------

def fetch_seace() -> list:
    base = "https://prod6.seace.gob.pe/v1/s8uit-services/buscadorpublico/contrataciones/buscador"
    raw = []
    for kw in ["la libertad", "marcahuamachuco"]:
        r = requests.get(base, params={"anio": ANIO, "palabra_clave": kw,
                                        "orden": 2, "page": 1, "page_size": 25},
                         timeout=30)
        r.raise_for_status()
        raw.extend(r.json().get("data", []))
    seen, unique = set(), []
    for x in raw:
        if x["idContrato"] not in seen:
            seen.add(x["idContrato"]); unique.append(x)
    unique.sort(
        key=lambda x: datetime.strptime(x["fecPublica"], "%d/%m/%Y %H:%M:%S"),
        reverse=True
    )
    return unique[:25]


def fmt_seace(item: dict, n: int) -> str:
    tipos = {1: "Bien", 2: "Servicio", 3: "Obra"}
    tipo  = tipos.get(item.get("idObjetoContrato", 2), "Otro")
    estado = item.get("nomEstadoContrato", "")
    pub   = item.get("fecPublica", "")[:16]
    desc  = (item.get("desObjetoContrato") or "")[:80]
    cod   = item.get("desContratacion", "")
    entidad = item.get("nomEntidad", "")

    if estado.lower() == "culminado":
        cotizar_line = "Estado: CULMINADO"
    else:
        cotizar_line = "Cotizar: SI" if item.get("cotizar") else "Cotizar: NO"
        ini = item.get("fecIniCotizacion", "")[:16]
        fin = item.get("fecFinCotizacion", "")[:16]
        if ini:
            cotizar_line += f" | {ini} - {fin}"

    return (
        f"*[{n}/25]* `{cod}`\n"
        f"{entidad}\n"
        f"{tipo}: {desc}\n"
        f"Pub: {pub} | {cotizar_line}"
    )

# ---------- 2. SUNARP Trujillo ----------------------------------------------

def fetch_sunarp() -> list:
    url = "https://8uit.sunarp.gob.pe/portal/zona-registral/zona-registral-n-v-sede-trujillo"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "html.parser")
    items = []

    # Intenta parsear tarjetas/cards con datos de requerimiento
    for card in soup.find_all(True, class_=re.compile(r"card|item|req|proceso", re.I)):
        text = card.get_text(" ", strip=True)
        if "REQ." not in text and "Fecha de publicaci" not in text:
            continue
        req_m   = re.search(r"REQ\.\s*([\w\d\-]+)", text)
        pub_m   = re.search(r"publicaci[oó]n[:\s]+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", text, re.I)
        ven_m   = re.search(r"vencimiento[:\s]+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", text, re.I)
        title_m = re.search(
            r"((?:BIENES|SERVICIOS|OBRAS|ADQUISICION|CONTRATACION)[^\n\.]{5,100})",
            text, re.I
        )
        items.append({
            "titulo": (title_m.group(1).strip() if title_m else text[:80]),
            "req":    req_m.group(1) if req_m else "",
            "pub":    pub_m.group(1) if pub_m else "",
            "vence":  ven_m.group(1) if ven_m else "",
        })

    # Fallback: barrido del texto completo si no hay tarjetas
    if not items:
        full = soup.get_text(" ", strip=True)
        blocks = re.split(r"(?=(?:BIENES|SERVICIOS|OBRAS)[\s:])", full, flags=re.I)
        for block in blocks[1:]:
            req_m = re.search(r"REQ\.\s*([\w\d\-]+)", block)
            pub_m = re.search(r"publicaci[oó]n[:\s]+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", block, re.I)
            ven_m = re.search(r"vencimiento[:\s]+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", block, re.I)
            items.append({
                "titulo": block[:80].strip(),
                "req":    req_m.group(1) if req_m else "",
                "pub":    pub_m.group(1) if pub_m else "",
                "vence":  ven_m.group(1) if ven_m else "",
            })

    return items[:20]


def fmt_sunarp(item: dict, n: int) -> str:
    return (
        f"*{n}.* {item['titulo'][:80]}\n"
        f"REQ: {item['req']} | Pub: {item['pub']}\n"
        f"Vence: {item['vence']}"
    )

# ---------- 3. PNSR ---------------------------------------------------------

def fetch_pnsr() -> list:
    base = "https://aplicacionespnsr.vivienda.gob.pe/spsPNSR"
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        s.get(base + "/consulta", timeout=30)
    except Exception:
        pass
    r = s.post(
        base + "/Consulta/jsonListadoProcesos",
        params={"dpto": "La Libertad", "estado": "Vigente"},
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=30,
    )
    try:
        data = r.json()
        return data if isinstance(data, list) else data.get("data", [])
    except Exception:
        return []


def fmt_pnsr(item: dict, n: int) -> str:
    exp  = item.get("expediente", item.get("nroExpediente", ""))
    desc = (item.get("descripcion", item.get("objeto", "")) or "")[:80]
    pub  = str(item.get("fechaPublicacion", item.get("fecPublicacion", "")))[:16]
    ven  = str(item.get("fechaVencimiento", item.get("fecVencimiento", "")))[:16]
    return f"*{n}.* {exp}\n{desc}\nPub: {pub} | Vence: {ven}"

# ---------- 4. MPFN ---------------------------------------------------------

def fetch_mpfn() -> list:
    base = "https://portal.mpfn.gob.pe/contrataciones"
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        s.get(base + "/arrendamiento", timeout=30)
    except Exception:
        pass
    r = s.post(
        base + "/lista-avisos-json",
        data={"departamento": "13", "tipoProceso": ""},
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=30,
    )
    try:
        data = r.json()
        return data if isinstance(data, list) else data.get("data", [])
    except Exception:
        return []


def fmt_mpfn(item: dict, n: int) -> str:
    entidad = (item.get("distrito", item.get("entidad", "MPFN")) or "")[:50]
    tipo    = item.get("tipoProceso", "")[:30]
    desc    = (item.get("descripcion", item.get("objeto", "")) or "")[:80]
    pub     = str(item.get("fechaPublicacion", ""))[:16]
    ven     = str(item.get("fechaVencimiento", ""))[:16]
    return f"*{n}.* {entidad}\n{tipo}: {desc}\nPub: {pub} | Vence: {ven}"

# ---------- Reporte principal -----------------------------------------------

def main(turno: str = "MANANA"):
    turno    = turno.upper()
    next_rep = "6:30 PM" if turno == "MANANA" else "8:00 AM"
    fecha    = datetime.now().strftime("%d/%m/%Y")
    hora     = datetime.now().strftime("%H:%M")

    print(f"[{hora}] Iniciando reporte {turno}...")

    # Cabecera
    send(
        f"*REPORTE COMPRAS PUBLICAS - {turno}*\n"
        f"Region: LA LIBERTAD\n"
        f"Fecha: {fecha} | Hora: {hora}\n"
        f"Fuentes: SEACE | SUNARP | PNSR | MPFN\n"
        f"{'='*20}"
    )

    # 1. SEACE
    print("  [1/4] SEACE...")
    try:
        seace = fetch_seace()
        send(f"*--- SEACE: {len(seace)} procesos recientes ---*")
        for start in range(0, len(seace), 5):
            batch = seace[start:start+5]
            send("\n\n".join(fmt_seace(x, start+i+1) for i, x in enumerate(batch)))
        cotizar_n = sum(1 for x in seace if x.get("cotizar"))
        send(f"SEACE: {len(seace)} procesos | Pueden cotizar: {cotizar_n}")
    except Exception as e:
        send(f"[SEACE] Error: {e}")
        print(f"    ERROR: {e}")

    # 2. SUNARP
    print("  [2/4] SUNARP...")
    try:
        sunarp = fetch_sunarp()
        if sunarp:
            send(
                f"*--- SUNARP Trujillo: {len(sunarp)} requerimientos activos ---*\n\n"
                + "\n\n".join(fmt_sunarp(x, i+1) for i, x in enumerate(sunarp[:10]))
            )
        else:
            send("*--- SUNARP Trujillo ---*\nSin requerimientos activos")
    except Exception as e:
        send(f"[SUNARP] Error: {e}")
        print(f"    ERROR: {e}")

    # 3. PNSR
    print("  [3/4] PNSR...")
    try:
        pnsr = fetch_pnsr()
        if pnsr:
            send(
                f"*--- PNSR La Libertad: {len(pnsr)} contrataciones vigentes ---*\n\n"
                + "\n\n".join(fmt_pnsr(x, i+1) for i, x in enumerate(pnsr[:10]))
            )
        else:
            send("*--- PNSR La Libertad ---*\nSin contrataciones vigentes")
    except Exception as e:
        send(f"[PNSR] Error: {e}")
        print(f"    ERROR: {e}")

    # 4. MPFN
    print("  [4/4] MPFN...")
    try:
        mpfn = fetch_mpfn()
        if mpfn:
            send(
                f"*--- MPFN La Libertad: {len(mpfn)} convocatorias activas ---*\n\n"
                + "\n\n".join(fmt_mpfn(x, i+1) for i, x in enumerate(mpfn[:10]))
            )
        else:
            send("*--- MPFN La Libertad ---*\nSin convocatorias activas")
    except Exception as e:
        send(f"[MPFN] Error: {e}")
        print(f"    ERROR: {e}")

    # Pie
    send(
        f"{'='*20}\n"
        f"Reporte completo: SEACE + SUNARP + PNSR + MPFN\n"
        f"Proximo reporte: {next_rep}"
    )
    print(f"[OK] Reporte {turno} enviado.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "MANANA")
