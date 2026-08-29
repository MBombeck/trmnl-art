# TRMNL Art Display — Dashboard & Gallery Redesign

## Date: 2026-04-08
## Status: Approved (user gave full autonomy)

## Problem

1. No web dashboard — API endpoints must be called manually via browser/curl
2. Gallery only shows goat-art, not Rijksmuseum or NASA images
3. No way to delete unwanted gallery images
4. Displayed images from Rijksmuseum/NASA are not persisted in any gallery
5. No navigation between views

## Requirements (from user)

1. **Dashboard** at root `/` — manage all API controls (health, next, push sources, status, build-index)
2. **Gallery** — browse all images with source filter dropdown (Goat Art, Rijksmuseum, NASA, All)
3. **Delete** — remove individual images from any gallery
4. **Image Persistence** — every image pushed to TRMNL gets saved to its source gallery
5. **Source Selection** — choose which source to use from the dashboard
6. **Navigation** — links between Dashboard and Gallery
7. **No auth** — user will add separately
8. **Beautiful frontend** — polished, responsive design

## Architecture

### Backend Changes

#### New Galleries
- `DATA_DIR/rijksmuseum-gallery/` — persists every Rijksmuseum image displayed
- `DATA_DIR/nasa-gallery/` — persists every NASA APOD image displayed
- `DATA_DIR/goat-gallery/` — already exists, no change

Each image saved as `{source_id}.png` with a companion `{source_id}.json` metadata file:
```json
{
  "title": "Starry Night with Goat",
  "source": "goat-art",
  "pushed_at": "2026-04-08T08:00:18",
  "filename": "van_gogh_starry_night.png"
}
```

#### New/Modified API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Dashboard HTML |
| GET | `/gallery` | Gallery HTML (with source filter) |
| GET | `/api/galleries` | List all gallery images grouped by source |
| GET | `/api/galleries/{source}` | List images for one source |
| GET | `/api/galleries/{source}/{filename}` | Serve single gallery image |
| DELETE | `/api/galleries/{source}/{filename}` | Delete single gallery image |
| GET | `/api/source` | Get current art source |
| POST | `/api/source` | Switch art source (body: `{"source": "goat-art"}`) |

Existing endpoints unchanged: `/health`, `/api/status`, `/api/next`, `/api/push/*`, `/api/build-index`, `/current.png`

Legacy `/gallery` and `/gallery/{filename}` routes redirect to new paths.

#### Image Persistence on Push
Modify `scheduler._run_job()` to save every successfully processed image to its source gallery directory with metadata JSON.

### Frontend Design

#### Dashboard (`/`)
- Header with app title + link to Gallery
- Status card: current image preview, source, last push time, scheduler status
- Source selector: radio/buttons for goat-art, rijksmuseum, nasa
- Action buttons: Push Now (per source), Next Image, Build Index
- Job status cards: last run, last success, errors, retries for each source
- Health indicator

#### Gallery (`/gallery?source=all`)
- Header with link back to Dashboard
- Dropdown filter: All, Goat Art, Rijksmuseum, NASA
- Responsive grid of image cards
- Each card: image thumbnail, title, source badge, date, delete button
- Click to zoom (existing behavior)
- Image count per source

### Color Scheme
Dark theme (existing `#1a1a2e` base), accent gold `#f0c040`, source-specific badges:
- Goat Art: warm amber
- Rijksmuseum: royal blue
- NASA: deep purple

## File Structure Changes

```
app/
  main.py          — add dashboard route, gallery API routes, delete endpoint
  gallery.py       — NEW: gallery management (list, save, delete, metadata)
  templates.py     — NEW: HTML templates for dashboard + gallery (inline, no Jinja)
  scheduler.py     — modify _run_job to persist images
  config.py        — add gallery dir constants
  (all other files unchanged)
```

## Testing Strategy

- Unit tests for gallery CRUD operations
- Integration tests for API endpoints
- Frontend visual verification via WebFetch

## Implementation Order

1. Backend: gallery.py (CRUD operations)
2. Backend: config.py updates
3. Backend: scheduler.py (image persistence)
4. Backend: main.py (new routes)
5. Frontend: templates.py (dashboard + gallery HTML/CSS/JS)
6. Tests
7. Git push + deploy verification
