# TRMNL Art Display

Tägliche Kunst auf dem TRMNL E-Ink Display (800×480) — Ziegen-Kunst (Imagen 4 Ultra), Rijksmuseum-Gemälde und NASA-Weltraumbilder. Mit vereinheitlichtem Admin-Dashboard, Galerie-Verwaltung und On-Demand-Bildgenerator.

## Was macht das?

Ein FastAPI-Service der:

- Täglich per Cron ein Bild der aktiven Quelle pusht (Ziegen-Kunst 06:00, Rijksmuseum 05:00, NASA 14:30 — je nach Quelle)
- Bilder für E-Ink **optimiert**: Rand-Trim → Cover-Fit 800×480 (LANCZOS, seitenverhältnis-treu) → Grading (Autocontrast, Shadow Boost, Schärfung, Sättigung)
- Das optimierte Bild per **Webhook an TRMNL** pusht und unter `/current.png` serviert
- Neue Bilder **on-demand via Imagen 4 Ultra generiert** (Stil-Presets: Pop-Art, Keith Haring, Warhol, Lichtenstein) mit Vorschau-/Freigabe-Workflow
- Galerien **per Content-Hash dedupliziert** (keine doppelten Bilder mehr) und beim Start automatisch repariert (Größe/weiße Ränder)
- Bei Fehlern **automatisch 3× retried** (Self-Healing)

## Architektur

```
┌──────────────┐     ┌──────────────────┐     ┌───────────┐
│ Imagen 4     │────▶│                  │     │           │
│ Ultra API    │     │  trmnl-art       │────▶│  TRMNL    │
│ Rijksmuseum  │────▶│  (apps-01)       │     │  Cloud    │
│ IIIF API     │     │                  │     │           │
│ NASA Images  │────▶│  /current.png    │◀────│  Chrome   │
└──────────────┘     └──────────────────┘     │  Renderer │
                                              └─────┬─────┘
                                              ┌─────▼─────┐
                                              │  TRMNL    │
                                              │  Display  │
                                              │  800x480  │
                                              └───────────┘
```

**Bildpipeline:** Quellbild → Sanity-Decode → Trim gleichmäßiger weißer Ränder (≥8px) → Cover-Fit 800×480 (LANCZOS, übersprungen wenn bereits exakt) → E-Ink Grading → PNG (JPEG-Fallback > 1 MB)

## Authentifizierung

Browser melden sich über eine **Login-Seite** (`/login`) an — per **Passwort** oder **WebAuthn-Passkey** (Touch ID, Windows Hello, Security Key). Nach dem Login gibt es einen signierten Session-Cookie (`trmnl_session`, HMAC-SHA256, 30 Tage, HttpOnly, SameSite=Lax, Secure hinter HTTPS). **HTTP Basic Auth funktioniert weiterhin** auf allen API-Endpoints als curl-/Scripting-Fallback (`ADMIN_USERNAME`, Standard `marc` / `ADMIN_PASSWORD`).

- **Öffentlich (ohne Auth):** `GET /current.png`, `GET /health`, `GET /login`, Passkey-Login-Endpoints
- **Alles andere** (Dashboard, Galerie, Push, Quelle wechseln, Generator, Status) erfordert Session-Cookie **oder** Basic Auth
- **Browser ohne Login** (Accept: `text/html`) werden per `302` auf `/login?next=…` umgeleitet; API-Clients bekommen `401` JSON
- **Rate-Limit:** 5 fehlgeschlagene Passwort-Logins pro Minute und IP → `429`
- **Fail-closed:** Ohne gesetztes `ADMIN_PASSWORD` liefern geschützte Routen `503` mit Hinweis

### Passkeys

Im Dashboard unter **„Sicherheit"** lassen sich Passkeys registrieren (Label vergeben, Geräte-Ceremony läuft im Browser), auflisten und löschen. Gespeichert werden sie in `data/passkeys.json` (nur Credential-ID, Public Key, Sign-Count, Transports, Label). Registrieren erfordert eine bestehende Anmeldung; der Passkey-Login selbst ist öffentlich (er *ist* der Login). RP-ID ist standardmäßig `bombeck.io` und gilt damit für `trmnl.bombeck.io` **und** `trmnl-art.bombeck.io`.

## API Endpoints

| Endpoint | Methode | Auth | Beschreibung |
|---|---|---|---|
| `/current.png` | GET | — | Aktuelles Bild (das, was TRMNL anzeigt) |
| `/health` | GET | — | Health Check (für Monitoring) |
| `/login` | GET | — | Login-Seite (Passwort + Passkey); leitet eingeloggte Nutzer weiter |
| `/api/auth/login` | POST | — | Passwort-Login → Session-Cookie. Body: `{password}`. Rate-Limit 5/min |
| `/api/auth/logout` | POST | ✓ | Session-Cookie löschen |
| `/api/auth/webauthn/register/options` | POST | ✓ | Passkey-Registrierung starten (Challenge, 5 Min gültig) |
| `/api/auth/webauthn/register/verify` | POST | ✓ | Attestation prüfen, Passkey speichern. Body: `{state, label, transports, credential}` |
| `/api/auth/webauthn/login/options` | POST | — | Passkey-Login starten (Challenge + erlaubte Credentials) |
| `/api/auth/webauthn/login/verify` | POST | — | Assertion prüfen → Session-Cookie. Body: `{state, credential}` |
| `/api/auth/webauthn/credentials` | GET | ✓ | Registrierte Passkeys (Metadaten) |
| `/api/auth/webauthn/credentials/{id}` | DELETE | ✓ | Passkey löschen |
| `/` | GET | ✓ | Vereinheitlichtes Dashboard (Status, Quelle, Tagesimpulse, Generator) |
| `/gallery` | GET | ✓ | Galerie-UI (filtern, zoomen, pushen, löschen) |
| `/api/status` | GET | ✓ | Scheduler-Status, letzte/nächste Runs, Galerie-Zähler |
| `/api/next` | GET | ✓ | Nächstes Bild der aktiven Quelle pushen |
| `/api/push/{goat-art\|rijksmuseum\|nasa}` | GET | ✓ | Sofort-Push einer bestimmten Quelle |
| `/api/source` | GET/POST | ✓ | Aktive Quelle lesen / wechseln (persistiert in `settings.json`, Cron wird umregistriert) |
| `/api/galleries` | GET | ✓ | Alle Galerie-Bilder |
| `/api/galleries/{source}` | GET | ✓ | Bilder einer Quelle |
| `/api/galleries/{source}/{file}` | GET/DELETE | ✓ | Einzelbild abrufen / löschen (Blacklist) |
| `/api/galleries/{source}/{file}/push` | POST | ✓ | Galerie-Bild an TRMNL pushen |
| `/api/generate` | POST | ✓ | Bild via Imagen 4 Ultra generieren → Pending-Queue. Body: `{style_preset, subject, custom_prompt}` |
| `/api/pending` | GET | ✓ | Ausstehende generierte Bilder |
| `/api/pending/{id}.png` | GET | ✓ | E-Ink-Vorschau eines Pending-Bildes |
| `/api/pending/{id}/accept` | POST | ✓ | In Ziegen-Galerie übernehmen. Body: `{push: bool}` |
| `/api/pending/{id}` | DELETE | ✓ | Pending-Bild verwerfen |
| `/api/build-index?pages=10` | GET | ✓ | Rijksmuseum-Index erweitern |

### Generator-Stil-Presets

`pop-art` (Lichtenstein Benday Dots), `keith-haring`, `warhol` (2×2 Silkscreen-Grid), `lichtenstein-romance`. Ohne Motiv wird `a cheerful goat` verwendet; `custom_prompt` ersetzt Stil + Motiv komplett. Alle Prompts enthalten starke Anti-Rand-Anweisungen (full-bleed 16:9). Fehler (429-Quota, Safety-Filter, Timeout) kommen als klare deutsche Meldungen zurück.

## Deployment

Läuft auf **apps-01** (159.69.23.98) via Coolify.

- **URLs**: https://trmnl-art.bombeck.io und https://trmnl.bombeck.io (gleiche App, zweite Domain)
- **Coolify Project**: `xsgk4csw0cs0wwwsccgk8s44`
- **Coolify App**: `jkw80o8scgk8g4g0cs0o44wg`
- **Volume**: `trmnl-art-data:/app/data` (Galerien, History, Settings, aktuelles Bild)
- **Wichtig**: `trmnl-art.bombeck.io/tagesimpulse/*` wird von einem **separaten Container** via Traefik PathPrefix bedient — diese App registriert dort keine Routen. Das Dashboard bindet die Tagesimpulse-API nur read-only ein.

### Environment Variables

| Variable | Default | Beschreibung |
|---|---|---|
| `ADMIN_USERNAME` | `marc` | Admin-Benutzer (Basic Auth + Session) |
| `ADMIN_PASSWORD` | — | **Pflicht in Produktion** — ohne Passwort sind geschützte Routen 503 (fail-closed) |
| `SESSION_SECRET` | — | Optionaler HMAC-Key für Session-Cookies; ohne ihn wird der Key aus `ADMIN_PASSWORD` abgeleitet (Passwort-Rotation invalidiert dann alle Sessions) |
| `WEBAUTHN_RP_ID` | `bombeck.io` | WebAuthn Relying-Party-ID (muss Suffix der Domain sein) |
| `WEBAUTHN_ORIGINS` | `https://trmnl.bombeck.io,https://trmnl-art.bombeck.io` | Erlaubte Origins für Passkey-Ceremonies (kommasepariert) |
| `TRMNL_WEBHOOK_UUID` | — | Webhook UUID vom TRMNL Private Plugin |
| `GEMINI_API_KEY` | — | Google-API-Key für Imagen (Generator + On-Demand-Ziegen) |
| `IMAGEN_MODEL` | `imagen-4.0-generate-001` | Imagen-Modell (Ultra: `imagen-4.0-ultra-generate-001`) |
| `OPENAI_API_KEY` | — | OpenAI-Key, Fallback-Backend `gpt-image-1` bei leerem Gemini-Guthaben |
| `OPENROUTER_API_KEY` | — | OpenRouter-Key, Backend für Gemini-Bildmodelle ohne Google-Prepaid |
| `OPENROUTER_IMAGE_MODEL` | `google/gemini-3.1-flash-image` | Bildmodell auf OpenRouter (z. B. `google/gemini-3-pro-image`) |
| `IMAGE_BACKEND` | `auto` | Bevorzugtes Backend: `auto` (Imagen → OpenAI → OpenRouter), `imagen`, `openai` oder `openrouter`; bei 429 greift der Rest der Kette |
| `ART_SOURCE` | `goat-art` | Initiale Quelle (nur Fallback — Laufzeit-Quelle steht in `data/settings.json`) |
| `NASA_API_KEY` | `DEMO_KEY` | NASA API Key |
| `APP_URL` | `http://localhost:8000` | Öffentliche URL der App (für TRMNL-Bild-URL) |
| `GOAT_ART_HOUR/MINUTE` | `6` / `0` | Ziegen-Kunst Push-Zeit |
| `RIJKSMUSEUM_HOUR/MINUTE` | `5` / `0` | Rijksmuseum Push-Zeit |
| `NASA_HOUR/MINUTE` | `14` / `30` | NASA Push-Zeit |
| `TAGESIMPULSE_API_URL` | `https://trmnl-art.bombeck.io/tagesimpulse/api/trmnl` | Quelle fürs Dashboard-Panel (leer = Panel aus) |
| `TZ` | `Europe/Berlin` | Zeitzone |
| `DATA_DIR` | `/app/data` | Persistentes Datenverzeichnis |
| `PORT` | `8000` | Server-Port |

## Persistente Daten (Volume)

| Datei/Ordner | Inhalt |
|---|---|
| `current.png` | Aktuell angezeigtes Bild |
| `settings.json` | Aktive Kunstquelle (Single Source of Truth für den Scheduler) |
| `gallery-hashes.json` | SHA-256-Index pro Galerie (Content-Dedupe) |
| `migration-log.json` | Zusammenfassung der letzten Start-Migration |
| `goat-gallery/`, `rijksmuseum-gallery/`, `nasa-gallery/` | Galerien (PNG + Metadaten-Sidecar-JSON) |
| `pending/` | Generierte, noch nicht freigegebene Bilder |
| `history.json`, `goat-history.json` | Bereits gezeigte Bilder (keine Wiederholungen) |
| `deleted-images.json` | Blacklist gelöschter Bilder (kommen nie zurück) |
| `passkeys.json` | Registrierte WebAuthn-Passkeys (ID, Public Key, Sign-Count, Label) |
| `rijksmuseum-index.json` | Index aller Querformat-Gemälde |

Alle JSON-Writes erfolgen **atomar** (tmp-Datei + `os.replace`).

## Start-Migration (idempotent)

Bei jedem Start läuft eine Galerie-Bereinigung:

1. **Dedupe**: Dateien pro Galerie per SHA-256 gruppiert; pro Gruppe bleibt die älteste Datei (semantische Namen werden gegenüber `*_YYYYMMDD`-Kopien bevorzugt), Rest + Sidecars werden gelöscht.
2. **Reparatur**: Bilder ≠ 800×480 oder mit gleichmäßigen weißen Rändern (≥8px) werden getrimmt + cover-gefittet und unter gleichem Namen neu gespeichert.
3. Hash-Index wird neu aufgebaut, Zusammenfassung landet in `migration-log.json` (im Dashboard/Galerie als Banner sichtbar).

## Self-Healing

- Jobs werden bei Fehler **3× retried** (5 Minuten Abstand)
- `misfire_grace_time=3600`: Verpasste Jobs werden bis zu 1h nachgeholt
- Health Endpoint gibt `503` zurück wenn Scheduler nicht läuft oder kein Bild existiert

## Entwicklung

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest -q          # Tests
DATA_DIR=/tmp/trmnl-art ADMIN_PASSWORD=dev .venv/bin/uvicorn app.main:app --port 8000
```

## Dateien

```
app/
├── main.py          # FastAPI App, Endpoints, Lifespan (Seed + Migration + Scheduler)
├── config.py        # Konfiguration aus Environment
├── security.py      # Session-Cookies (HMAC) + HTTP Basic Fallback (fail-closed)
├── auth.py          # Login-Seite, Passwort-Login, Logout, WebAuthn-Passkeys
├── state.py         # Aktive Quelle in data/settings.json
├── processing.py    # Pipeline: Trim, Cover-Fit, E-Ink Grading
├── gallery.py       # Galerien, Hash-Dedupe, Start-Migration, Blacklist
├── generator.py     # Imagen 4 Ultra Generator + Pending-Workflow
├── scheduler.py     # APScheduler Cron-Jobs, Reschedule bei Quellwechsel
├── goat_art.py      # Ziegen-Kunst-Quelle (Galerie + On-Demand)
├── sources.py       # Rijksmuseum + NASA Integration
├── templates.py     # Server-gerenderte UI (escaped, deutsch)
├── trmnl.py         # TRMNL Webhook Push
└── util.py          # Atomare Writes, Hashing, Slugs
generate_batch.py    # Batch-Generator (nutzt Trim + Cover-Fit)
tests/               # pytest (Dedupe, Migration, Trim, Auth, Generator, Scheduler)
data-seed/           # Seed-Index + Ziegen-Galerie (beim ersten Start kopiert)
```
