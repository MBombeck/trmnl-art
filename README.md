# TRMNL Art Display

Tägliche Kunst auf dem TRMNL E-Ink Display — Rijksmuseum-Gemälde morgens, NASA Astronomy Picture of the Day nachmittags.

## Was macht das?

Ein FastAPI-Service der:
- **05:00** ein zufälliges Querformat-Gemälde aus dem Rijksmuseum holt
- **14:30** das NASA Astronomy Picture of the Day holt
- Bilder für E-Ink **optimiert** (Kontrast, Gamma, Dithering) und als PNG serviert
- Das optimierte Bild per **Webhook an TRMNL** pushed
- Bei Fehlern **automatisch 3x retried** (Self-Healing)

## Architektur

```
┌─────────────┐     ┌──────────────────┐     ┌───────────┐
│ Rijksmuseum  │────▶│                  │     │           │
│ IIIF API     │     │  trmnl-art       │────▶│  TRMNL    │
│              │     │  (apps-01)       │     │  Cloud    │
│ NASA APOD    │────▶│                  │     │           │
│ API          │     │  /current.png    │◀────│  Chrome   │
└─────────────┘     └──────────────────┘     │  Renderer │
                                              └─────┬─────┘
                                                    │
                                              ┌─────▼─────┐
                                              │  TRMNL    │
                                              │  Display  │
                                              │  800x480  │
                                              └───────────┘
```

**Bildpipeline:** Quell-JPEG → Resize 800x480 (LANCZOS) → E-Ink Grading (Autocontrast, Gamma, Shadow Boost) → 2-Bit Floyd-Steinberg Dithering (4 Graustufen) → PNG (~60-80 KB)

## API Endpoints

Alle GET — direkt im Browser aufrufbar.

| Endpoint | Beschreibung |
|---|---|
| `/current.png` | Aktuelles Bild (das, was TRMNL anzeigt) |
| `/health` | Health Check (für Monitoring) |
| `/api/next` | Wechselt zur anderen Quelle (NASA↔Rijksmuseum) |
| `/api/push/rijksmuseum` | Sofort neues Rijksmuseum-Bild |
| `/api/push/nasa` | Sofort neues NASA-Bild |
| `/api/status` | Scheduler-Status, letzte Runs, nächste Runs |
| `/api/build-index?pages=10` | Rijksmuseum-Index erweitern |

## Deployment

Läuft auf **apps-01** (159.69.23.98) via Coolify.

- **URL**: https://trmnl-art.bombeck.io
- **Coolify Project**: `xsgk4csw0cs0wwwsccgk8s44`
- **Coolify App**: `jkw80o8scgk8g4g0cs0o44wg`
- **DNS**: A-Record `trmnl-art.bombeck.io` → 159.69.23.98 (Cloudflare, proxied)
- **Volume**: `trmnl-art-data:/app/data` (Index, History, aktuelles Bild)

### Environment Variables

| Variable | Default | Beschreibung |
|---|---|---|
| `TRMNL_WEBHOOK_UUID` | — | Webhook UUID vom TRMNL Private Plugin |
| `NASA_API_KEY` | `DEMO_KEY` | NASA API Key (10 req/h mit DEMO_KEY) |
| `APP_URL` | `http://localhost:8000` | Öffentliche URL der App |
| `RIJKSMUSEUM_HOUR` | `5` | Rijksmuseum Push-Stunde |
| `RIJKSMUSEUM_MINUTE` | `0` | Rijksmuseum Push-Minute |
| `NASA_HOUR` | `14` | NASA Push-Stunde |
| `NASA_MINUTE` | `30` | NASA Push-Minute |
| `TZ` | `Europe/Berlin` | Zeitzone |
| `DATA_DIR` | `/app/data` | Persistentes Datenverzeichnis |
| `PORT` | `8000` | Server-Port |

### Manuelles Deploy

```bash
# Push löst Auto-Deploy via Coolify aus
git push origin main

# Oder manuell via Coolify API
curl -X GET "http://100.124.79.96:8000/api/v1/deploy?uuid=jkw80o8scgk8g4g0cs0o44wg" \
  -H "Authorization: Bearer <COOLIFY_TOKEN>"
```

## TRMNL Konfiguration

### Private Plugin (auf trmnl.com)
- **Name**: Daily Art
- **Strategy**: Webhook
- **Remove bleed margin**: Yes
- **Markup**:
```html
<div class="layout layout--col layout--center layout--stretch">
  <img class="image image-dither image--cover" src="{{ image_url }}">
</div>
```

### Device Settings
- **Sleep Mode**: 23:00–04:45 (Batterieschonung)
- **Alte Plugins**: Deaktiviert (Paperboy, This Day in History)

## Bildverarbeitung

Die E-Ink-Pipeline basiert auf der [TRMNL byos_fastapi PhotographicPlugin](https://github.com/usetrmnl/byos_fastapi) Grading Chain:

1. **Resize**: 800x480 mit LANCZOS, Cover-Crop (Bildmitte)
2. **Dunkel-Erkennung**: Mean Brightness < 70 → Gamma-Korrektur (0.45–0.6)
3. **Autocontrast**: Histogramm-Stretching (0.05% Cutoff)
4. **Gamma 1.2**: Midtones aufhellen
5. **Shadow Boost**: Schatten anheben (Pivot 180, Gamma 0.65)
6. **Brightness +10%**: Gesamthelligkeit erhöhen
7. **Finaler Autocontrast**: Nochmal Histogramm normalisieren
8. **Unsharp Mask**: Details vor Dithering schärfen
9. **2-Bit Floyd-Steinberg Dithering**: 4 Graustufen (0x00, 0x55, 0xAA, 0xFF)

### Warum nicht einfach das JPEG an TRMNL schicken?

TRMNL rendert Templates mit **headless Chrome** (~1s Timeout für Bild-Download). Große oder langsame Bilder erscheinen als schwarze Fragmente. Unsere App:
- Verarbeitet Bilder **vor** (800x480, ~80KB statt 200-500KB)
- Serviert sie von **apps-01** (Hetzner, schnell)
- TRMNL Chrome lädt das Bild in **Millisekunden**

## Datenquellen

### Rijksmuseum (LOD API)
- **Index**: 202 Querformat-Gemälde (Rembrandt, Vermeer, Breitner, u.v.m.)
- **API**: Linked Open Data, kein API Key nötig
- **Auflösung**: 3-Schritt LOD Chain (HumanMadeObject → VisualItem → DigitalObject → IIIF)
- **Bilder**: IIIF Image API (`iiif.micr.io`), Download bei 1200px Breite
- **Filter**: Nur Querformat (Aspect Ratio ≥ 1.2)
- **Keine Wiederholungen**: Shown-History in `history.json`

### NASA APOD
- **API**: `api.nasa.gov/planetary/apod`
- **Fallback**: Bei Video-Tagen wird ein zufälliges historisches Bild geholt
- **Keine Wiederholungen**: Gezeigtes Datum wird in History gespeichert

## Dateien

```
app/
├── main.py          # FastAPI App, Endpoints, Startup
├── config.py        # Konfiguration aus Environment
├── processing.py    # E-Ink Bildverarbeitung (Grading + Dithering)
├── scheduler.py     # APScheduler Cron-Jobs, Self-Healing Retries
├── sources.py       # Rijksmuseum + NASA APOD API Integration
└── trmnl.py         # TRMNL Webhook Push
data-seed/
└── rijksmuseum-index.json  # Seed-Index (202 Gemälde)
```

## Persistente Daten (Volume)

| Datei | Inhalt |
|---|---|
| `rijksmuseum-index.json` | Index aller Querformat-Gemälde |
| `history.json` | Bereits gezeigte Bilder (keine Wiederholungen) |
| `current.png` | Aktuell angezeigtes Bild |

## Self-Healing

- Jobs werden bei Fehler **3x retried** (5 Minuten Abstand)
- `misfire_grace_time=3600`: Verpasste Jobs werden bis zu 1h nachgeholt
- Health Endpoint gibt `503` zurück wenn Scheduler nicht läuft oder kein Bild existiert
