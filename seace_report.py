import requests, sys
from datetime import datetime

SEACE_BASE = "https://prod6.seace.gob.pe/v1/s8uit-services/buscadorpublico/contrataciones/buscador"
TELEGRAM_TOKEN = "8905726945:AAFjo4JezGkwWUowGeNZlU8lPS0KLGOwGJ8"
TELEGRAM_CHAT_ID = "8718161110"

def fetch_seace(keyword, size=25):
    r = requests.get(SEACE_BASE, params={"anio": datetime.now().year, "palabra_clave": keyword, "orden": 2, "page": 1, "page_size": size}, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])

def send_telegram(text):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=30)

def parse_date(s):
    return datetime.strptime(s, "%d/%m/%Y %H:%M:%S")

def fmt(item, n):
    tipo = {1:"Bien",2:"Servicio",3:"Obra"}.get(item.get("idObjetoContrato",2),"Otro")
    st = item.get("nomEstadoContrato","")
    cotizar = "CULMINADO" if st.lower()=="culminado" else ("SI" if item.get("cotizar") else "NO")
    ini = item.get("fecIniCotizacion","")[:16]
    fin = item.get("fecFinCotizacion","")[:16]
    rango = f"Cotizar: {ini} -> {fin}\n" if ini and st.lower()!="culminado" else ""
    desc = (item.get("desObjetoContrato") or "")[:80]
    return f"*{n}/25* {item.get('desContratacion','')}\n{item.get('nomEntidad','')}\n{tipo}: {desc}\nPub: {item.get('fecPublica','')[:16]}\n{rango}Cotizar: {cotizar}"

def main(turno="MANANA"):
    turno = turno.upper()
    label = "MANANA" if turno == "MANANA" else "TARDE"
    next_r = "6:30 PM" if label == "MANANA" else "8:00 AM"
    d1 = fetch_seace("la libertad")
    d2 = fetch_seace("marcahuamachuco")
    seen, unique = set(), []
    for x in d1 + d2:
        if x["idContrato"] not in seen:
            seen.add(x["idContrato"]); unique.append(x)
    unique.sort(key=lambda x: parse_date(x["fecPublica"]), reverse=True)
    top = unique[:25]
    fecha = datetime.now().strftime("%d/%m/%Y")
    send_telegram(f"REPORTE SEACE - {label}\nRegion: LA LIBERTAD\nFecha: {fecha}\n━━━━━━━━━━━━━━━━━━━━")
    for i in range(0,25,5):
        send_telegram("\n\n".join(fmt(top[i+j], i+j+1) for j in range(min(5,len(top)-i))))
    c = sum(1 for x in top if x.get("cotizar"))
    send_telegram(f"━━━━━━━━━━━━━━━━━━━━\nTotal: 25 procesos | Cotizar: {c}\nVer: prod6.seace.gob.pe\nProximo: {next_r}")
    print(f"OK {label} - {c} cotizables")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv)>1 else "MANANA")
