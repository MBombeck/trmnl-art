"""HTML templates for Dashboard and Gallery — museum/gallery aesthetic."""

# Shared CSS and head
_HEAD = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">"""

_SHARED_CSS = """
    :root {
        --bg: #141218;
        --bg-card: #1c1922;
        --bg-card-hover: #241f2c;
        --text: #e8e4ed;
        --text-muted: #8a8494;
        --text-dim: #5e596a;
        --gold: #d4a853;
        --gold-dim: #a6833e;
        --gold-glow: rgba(212, 168, 83, 0.15);
        --goat: #c07830;
        --rijks: #2d5a9e;
        --nasa: #6b3fa0;
        --danger: #c0392b;
        --danger-hover: #e74c3c;
        --success: #27ae60;
        --border: rgba(255,255,255,0.06);
        --radius: 10px;
        --font-display: 'Playfair Display', Georgia, serif;
        --font-body: 'DM Sans', system-ui, sans-serif;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        background: var(--bg);
        color: var(--text);
        font-family: var(--font-body);
        font-size: 15px;
        line-height: 1.5;
        min-height: 100vh;
    }
    a { color: var(--gold); text-decoration: none; }
    a:hover { text-decoration: underline; }

    /* Noise texture overlay */
    body::before {
        content: '';
        position: fixed;
        inset: 0;
        opacity: 0.03;
        background: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
        pointer-events: none;
        z-index: 9999;
    }

    .container {
        max-width: 1280px;
        margin: 0 auto;
        padding: 0 24px;
    }

    /* Navigation */
    .topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 20px 0;
        border-bottom: 1px solid var(--border);
        margin-bottom: 40px;
    }
    .topbar-brand {
        font-family: var(--font-display);
        font-size: 1.5rem;
        color: var(--gold);
        letter-spacing: -0.02em;
    }
    .topbar-nav { display: flex; gap: 24px; align-items: center; }
    .topbar-nav a {
        font-size: 0.875rem;
        font-weight: 500;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        transition: color 0.2s;
    }
    .topbar-nav a:hover, .topbar-nav a.active {
        color: var(--gold);
        text-decoration: none;
    }

    /* Source badges */
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    .badge-goat { background: rgba(192,120,48,0.2); color: #e09050; }
    .badge-rijks { background: rgba(45,90,158,0.2); color: #5a8fd4; }
    .badge-nasa { background: rgba(107,63,160,0.2); color: #9b7fd0; }

    /* Toast notifications */
    .toast-container {
        position: fixed;
        bottom: 24px;
        right: 24px;
        z-index: 10000;
        display: flex;
        flex-direction: column;
        gap: 8px;
    }
    .toast {
        padding: 12px 20px;
        border-radius: var(--radius);
        font-size: 0.85rem;
        font-weight: 500;
        animation: toast-in 0.3s ease-out;
        backdrop-filter: blur(12px);
        border: 1px solid var(--border);
    }
    .toast-success { background: rgba(39,174,96,0.15); color: #4ecb71; }
    .toast-error { background: rgba(192,57,43,0.15); color: #e66; }
    .toast-info { background: rgba(212,168,83,0.15); color: var(--gold); }
    @keyframes toast-in {
        from { opacity: 0; transform: translateY(16px); }
        to { opacity: 1; transform: translateY(0); }
    }

    /* Buttons */
    .btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 10px 18px;
        border: 1px solid var(--border);
        border-radius: var(--radius);
        background: var(--bg-card);
        color: var(--text);
        font-family: var(--font-body);
        font-size: 0.85rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s;
    }
    .btn:hover { background: var(--bg-card-hover); border-color: rgba(255,255,255,0.12); }
    .btn-gold { border-color: var(--gold-dim); color: var(--gold); }
    .btn-gold:hover { background: var(--gold-glow); }
    .btn-danger { border-color: rgba(192,57,43,0.3); color: var(--danger); }
    .btn-danger:hover { background: rgba(192,57,43,0.15); color: var(--danger-hover); }
    .btn-sm { padding: 6px 12px; font-size: 0.78rem; }
    .btn:disabled { opacity: 0.4; cursor: not-allowed; }

    /* Spinner */
    .spinner {
        display: inline-block;
        width: 14px;
        height: 14px;
        border: 2px solid rgba(255,255,255,0.1);
        border-top-color: var(--gold);
        border-radius: 50%;
        animation: spin 0.6s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* Fade in animation */
    @keyframes fade-up {
        from { opacity: 0; transform: translateY(12px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .fade-up {
        animation: fade-up 0.4s ease-out both;
    }
"""

_TOAST_JS = """
function toast(msg, type='info') {
    let c = document.getElementById('toasts');
    if (!c) { c = document.createElement('div'); c.id='toasts'; c.className='toast-container'; document.body.appendChild(c); }
    const t = document.createElement('div');
    t.className = 'toast toast-' + type;
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => { t.style.opacity='0'; t.style.transform='translateY(8px)'; t.style.transition='all 0.3s'; setTimeout(() => t.remove(), 300); }, 3500);
}

async function apiCall(url, method='GET', body=null) {
    try {
        const opts = { method };
        if (body) { opts.headers = {'Content-Type':'application/json'}; opts.body = JSON.stringify(body); }
        const r = await fetch(url, opts);
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || data.error || r.statusText);
        return data;
    } catch(e) {
        toast(e.message, 'error');
        throw e;
    }
}
"""


def render_dashboard(status: dict, gallery_counts: dict) -> str:
    """Render the dashboard HTML page."""
    import time as _time
    cache_bust = int(_time.time())
    jobs = status.get("jobs", {})

    def job_card(source: str, label: str, css_class: str) -> str:
        job = jobs.get(source, {})
        last_success = job.get("last_success", "")
        last_error = job.get("last_error", "")
        next_run = job.get("next_run", "")
        retries = job.get("retries", 0)

        success_time = last_success[:16].replace("T", " ") if last_success else "Never"
        next_time = next_run[:16].replace("T", " ") if next_run else "Not scheduled"
        error_html = f'<div class="job-error">{last_error}</div>' if last_error else ""
        retry_html = f'<span class="retry-badge">{retries} retries</span>' if retries > 0 else ""

        return f"""
        <div class="job-card fade-up">
            <div class="job-header">
                <span class="badge badge-{css_class}">{label}</span>
                {retry_html}
            </div>
            <div class="job-stats">
                <div class="job-stat">
                    <span class="job-stat-label">Last success</span>
                    <span class="job-stat-value">{success_time}</span>
                </div>
                <div class="job-stat">
                    <span class="job-stat-label">Next run</span>
                    <span class="job-stat-value">{next_time}</span>
                </div>
                <div class="job-stat">
                    <span class="job-stat-label">Gallery</span>
                    <span class="job-stat-value">{gallery_counts.get(source, 0)} images</span>
                </div>
            </div>
            {error_html}
            <button class="btn btn-gold btn-sm" onclick="pushSource('{source}')">
                Push Now
            </button>
        </div>"""

    current_source = status.get("art_source", "goat-art")
    scheduler_running = status.get("scheduler_running", False)
    img_exists = status.get("current_image_exists", False)
    img_size = status.get("current_image_size_kb", 0)

    return f"""<!DOCTYPE html>
<html lang="en"><head>
{_HEAD}
<title>TRMNL Art — Dashboard</title>
<style>
{_SHARED_CSS}

    .hero {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 32px;
        margin-bottom: 48px;
        align-items: start;
    }}
    @media (max-width: 800px) {{ .hero {{ grid-template-columns: 1fr; }} }}

    .preview-card {{
        background: var(--bg-card);
        border-radius: var(--radius);
        border: 1px solid var(--border);
        overflow: hidden;
    }}
    .preview-img {{
        width: 100%;
        aspect-ratio: 800/480;
        object-fit: cover;
        display: block;
        background: #0a090c;
    }}
    .preview-meta {{
        padding: 16px 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.82rem;
        color: var(--text-muted);
    }}

    .controls {{
        display: flex;
        flex-direction: column;
        gap: 20px;
    }}
    .control-section {{
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 20px;
    }}
    .control-section h3 {{
        font-family: var(--font-display);
        font-size: 1rem;
        color: var(--gold);
        margin-bottom: 14px;
        font-weight: 400;
    }}

    .status-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
    }}
    .status-item {{
        display: flex;
        flex-direction: column;
        gap: 2px;
    }}
    .status-label {{ font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.06em; }}
    .status-value {{ font-size: 0.9rem; font-weight: 500; }}
    .status-dot {{
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 6px;
    }}
    .status-dot.on {{ background: var(--success); box-shadow: 0 0 6px rgba(39,174,96,0.5); }}
    .status-dot.off {{ background: var(--danger); }}

    .source-selector {{
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
    }}
    .source-btn {{
        flex: 1;
        min-width: 100px;
        padding: 10px 14px;
        border: 1px solid var(--border);
        border-radius: var(--radius);
        background: var(--bg);
        color: var(--text-muted);
        font-family: var(--font-body);
        font-size: 0.82rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s;
        text-align: center;
    }}
    .source-btn:hover {{ border-color: rgba(255,255,255,0.15); color: var(--text); }}
    .source-btn.active {{
        border-color: var(--gold-dim);
        color: var(--gold);
        background: var(--gold-glow);
    }}

    .action-row {{
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
    }}

    /* Job cards */
    .section-title {{
        font-family: var(--font-display);
        font-size: 1.3rem;
        color: var(--text);
        margin-bottom: 20px;
        font-weight: 400;
    }}
    .jobs-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 16px;
        margin-bottom: 48px;
    }}
    .job-card {{
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 20px;
    }}
    .job-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 16px;
    }}
    .job-stats {{
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-bottom: 16px;
    }}
    .job-stat {{
        display: flex;
        justify-content: space-between;
        font-size: 0.82rem;
    }}
    .job-stat-label {{ color: var(--text-dim); }}
    .job-stat-value {{ color: var(--text-muted); font-weight: 500; }}
    .job-error {{
        padding: 8px 12px;
        border-radius: 6px;
        background: rgba(192,57,43,0.1);
        color: #e66;
        font-size: 0.78rem;
        margin-bottom: 12px;
        word-break: break-word;
    }}
    .retry-badge {{
        font-size: 0.7rem;
        padding: 2px 8px;
        border-radius: 10px;
        background: rgba(231,76,60,0.15);
        color: #e66;
    }}

    footer {{
        text-align: center;
        padding: 40px 0;
        color: var(--text-dim);
        font-size: 0.78rem;
        border-top: 1px solid var(--border);
    }}
</style>
</head><body>
<div class="container">
    <nav class="topbar">
        <div class="topbar-brand">TRMNL Art</div>
        <div class="topbar-nav">
            <a href="/" class="active">Dashboard</a>
            <a href="/gallery">Gallery</a>
        </div>
    </nav>

    <div class="hero">
        <div class="preview-card fade-up">
            {"<img src='/current.png?" + str(cache_bust) + "' class='preview-img' alt='Current display'>" if img_exists else "<div class='preview-img' style='display:flex;align-items:center;justify-content:center;color:var(--text-dim)'>No image</div>"}
            <div class="preview-meta">
                <span>Currently on display</span>
                <span>{img_size:.0f} KB</span>
            </div>
        </div>

        <div class="controls">
            <div class="control-section fade-up" style="animation-delay:0.05s">
                <h3>Status</h3>
                <div class="status-grid">
                    <div class="status-item">
                        <span class="status-label">Scheduler</span>
                        <span class="status-value"><span class="status-dot {"on" if scheduler_running else "off"}"></span>{"Running" if scheduler_running else "Stopped"}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Source</span>
                        <span class="status-value" id="current-source">{current_source}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Image</span>
                        <span class="status-value">{"Ready" if img_exists else "None"}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Total Gallery</span>
                        <span class="status-value">{gallery_counts.get("total", 0)} images</span>
                    </div>
                </div>
            </div>

            <div class="control-section fade-up" style="animation-delay:0.1s">
                <h3>Art Source</h3>
                <div class="source-selector">
                    <button class="source-btn {"active" if current_source == "goat-art" else ""}" onclick="setSource('goat-art')">Goat Art</button>
                    <button class="source-btn {"active" if current_source == "rijksmuseum" else ""}" onclick="setSource('rijksmuseum')">Rijksmuseum</button>
                    <button class="source-btn {"active" if current_source == "nasa" else ""}" onclick="setSource('nasa')">NASA APOD</button>
                </div>
            </div>

            <div class="control-section fade-up" style="animation-delay:0.15s">
                <h3>Actions</h3>
                <div class="action-row">
                    <button class="btn btn-gold" onclick="pushNext()">Next Image</button>
                    <button class="btn" onclick="buildIndex()">Build Index</button>
                    <button class="btn" onclick="refreshStatus()">Refresh</button>
                </div>
            </div>
        </div>
    </div>

    <h2 class="section-title">Scheduled Jobs</h2>
    <div class="jobs-grid">
        {job_card("goat-art", "Goat Art", "goat")}
        {job_card("rijksmuseum", "Rijksmuseum", "rijks")}
        {job_card("nasa", "NASA APOD", "nasa")}
    </div>

    <footer>TRMNL Art Display &middot; Device 22766</footer>
</div>

<script>
{_TOAST_JS}

async function pushSource(source) {{
    const btn = event.currentTarget;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Pushing...';
    try {{
        const data = await apiCall('/api/push/' + source);
        toast(data.message || 'Pushed!', 'success');
        setTimeout(() => location.reload(), 1500);
    }} catch(e) {{}}
    btn.disabled = false;
    btn.textContent = 'Push Now';
}}

async function pushNext() {{
    const btn = event.currentTarget;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Loading...';
    try {{
        const data = await apiCall('/api/next');
        toast(data.message || 'Next image pushed!', 'success');
        setTimeout(() => location.reload(), 1500);
    }} catch(e) {{}}
    btn.disabled = false;
    btn.textContent = 'Next Image';
}}

async function setSource(source) {{
    try {{
        await apiCall('/api/source', 'POST', {{source}});
        toast('Source changed to ' + source, 'success');
        document.querySelectorAll('.source-btn').forEach(b => b.classList.remove('active'));
        event.currentTarget.classList.add('active');
        document.getElementById('current-source').textContent = source;
    }} catch(e) {{}}
}}

async function buildIndex() {{
    const btn = event.currentTarget;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Building...';
    toast('Building Rijksmuseum index (this takes a while)...', 'info');
    try {{
        const data = await apiCall('/api/build-index?pages=5');
        toast('Index built: ' + (data.total_paintings || '?') + ' paintings', 'success');
    }} catch(e) {{}}
    btn.disabled = false;
    btn.textContent = 'Build Index';
}}

async function refreshStatus() {{
    try {{
        await apiCall('/api/status');
        location.reload();
    }} catch(e) {{}}
}}
</script>
</body></html>"""


def render_gallery(images: list[dict], counts: dict, source_filter: str = "all") -> str:
    """Render the gallery HTML page."""
    def image_card(img: dict, idx: int) -> str:
        src = img["source"]
        badge_class = {"goat-art": "goat", "rijksmuseum": "rijks", "nasa": "nasa"}.get(src, "goat")
        pushed = img.get("pushed_at", "")[:10] if img.get("pushed_at") else ""

        return f"""
        <div class="gallery-card fade-up" style="animation-delay:{min(idx * 0.03, 0.6):.2f}s" data-source="{src}">
            <div class="card-img-wrap">
                <img src="{img['url']}" loading="lazy" alt="{img['title']}" onclick="zoomImage(this)">
                <button class="card-delete" onclick="deleteImage('{src}', '{img['filename']}', this)" title="Delete">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14"/></svg>
                </button>
            </div>
            <div class="card-info">
                <span class="card-title">{img['title']}</span>
                <div class="card-meta">
                    <span class="badge badge-{badge_class}">{src}</span>
                    <span class="card-size">{img['size_kb']:.0f} KB{(' &middot; ' + pushed) if pushed else ''}</span>
                </div>
            </div>
        </div>"""

    cards = "".join(image_card(img, i) for i, img in enumerate(images))
    total = counts.get("total", 0)

    return f"""<!DOCTYPE html>
<html lang="en"><head>
{_HEAD}
<title>TRMNL Art — Gallery ({total} images)</title>
<style>
{_SHARED_CSS}

    .gallery-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 28px;
        flex-wrap: wrap;
        gap: 16px;
    }}
    .gallery-title {{
        font-family: var(--font-display);
        font-size: 1.6rem;
        font-weight: 400;
    }}
    .gallery-title span {{ color: var(--text-muted); font-size: 1rem; margin-left: 8px; }}

    .filter-bar {{
        display: flex;
        gap: 8px;
        align-items: center;
    }}
    .filter-select {{
        padding: 8px 14px;
        border: 1px solid var(--border);
        border-radius: var(--radius);
        background: var(--bg-card);
        color: var(--text);
        font-family: var(--font-body);
        font-size: 0.85rem;
        cursor: pointer;
        appearance: none;
        -webkit-appearance: none;
        background-image: url("data:image/svg+xml,%3Csvg width='12' height='8' viewBox='0 0 12 8' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%238a8494' stroke-width='1.5' fill='none'/%3E%3C/svg%3E");
        background-repeat: no-repeat;
        background-position: right 12px center;
        padding-right: 34px;
    }}
    .filter-select:focus {{ outline: none; border-color: var(--gold-dim); }}

    .source-counts {{
        display: flex;
        gap: 16px;
        font-size: 0.8rem;
        color: var(--text-dim);
    }}
    .source-counts span {{ display: flex; align-items: center; gap: 4px; }}

    /* Gallery grid */
    .gallery-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
        gap: 20px;
    }}
    @media (max-width: 500px) {{ .gallery-grid {{ grid-template-columns: 1fr; }} }}

    .gallery-card {{
        background: var(--bg-card);
        border-radius: var(--radius);
        border: 1px solid var(--border);
        overflow: hidden;
        transition: transform 0.2s, border-color 0.2s;
    }}
    .gallery-card:hover {{
        transform: translateY(-2px);
        border-color: rgba(255,255,255,0.1);
    }}

    .card-img-wrap {{
        position: relative;
        overflow: hidden;
    }}
    .card-img-wrap img {{
        width: 100%;
        aspect-ratio: 800/480;
        object-fit: cover;
        display: block;
        cursor: pointer;
        transition: transform 0.3s;
    }}
    .card-img-wrap:hover img {{ transform: scale(1.02); }}

    .card-delete {{
        position: absolute;
        top: 10px;
        right: 10px;
        width: 32px;
        height: 32px;
        border-radius: 50%;
        border: none;
        background: rgba(0,0,0,0.6);
        color: var(--text-muted);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        opacity: 0;
        transition: all 0.2s;
        backdrop-filter: blur(4px);
    }}
    .card-img-wrap:hover .card-delete {{ opacity: 1; }}
    .card-delete:hover {{ background: var(--danger); color: #fff; }}

    .card-info {{
        padding: 12px 16px;
    }}
    .card-title {{
        display: block;
        font-size: 0.88rem;
        font-weight: 500;
        margin-bottom: 6px;
        line-height: 1.3;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }}
    .card-meta {{
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}
    .card-size {{
        font-size: 0.75rem;
        color: var(--text-dim);
    }}

    /* Zoom overlay */
    .zoom-overlay {{
        position: fixed;
        inset: 0;
        background: rgba(0,0,0,0.92);
        z-index: 5000;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: zoom-out;
        animation: fade-in 0.2s ease-out;
    }}
    .zoom-overlay img {{
        max-width: 95vw;
        max-height: 95vh;
        object-fit: contain;
        border-radius: 4px;
    }}
    @keyframes fade-in {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}

    .empty-state {{
        text-align: center;
        padding: 80px 20px;
        color: var(--text-dim);
    }}
    .empty-state h3 {{
        font-family: var(--font-display);
        font-size: 1.3rem;
        color: var(--text-muted);
        margin-bottom: 8px;
        font-weight: 400;
    }}

    footer {{
        text-align: center;
        padding: 40px 0;
        color: var(--text-dim);
        font-size: 0.78rem;
        border-top: 1px solid var(--border);
        margin-top: 48px;
    }}
</style>
</head><body>
<div class="container">
    <nav class="topbar">
        <div class="topbar-brand">TRMNL Art</div>
        <div class="topbar-nav">
            <a href="/">Dashboard</a>
            <a href="/gallery" class="active">Gallery</a>
        </div>
    </nav>

    <div class="gallery-header">
        <div>
            <h1 class="gallery-title">Gallery <span id="img-count">{total} images</span></h1>
            <div class="source-counts">
                <span><span class="badge badge-goat" style="font-size:0.65rem">Goat</span> {counts.get("goat-art", 0)}</span>
                <span><span class="badge badge-rijks" style="font-size:0.65rem">Rijks</span> {counts.get("rijksmuseum", 0)}</span>
                <span><span class="badge badge-nasa" style="font-size:0.65rem">NASA</span> {counts.get("nasa", 0)}</span>
            </div>
        </div>
        <div class="filter-bar">
            <select class="filter-select" id="source-filter" onchange="filterGallery(this.value)">
                <option value="all" {"selected" if source_filter == "all" else ""}>All Sources</option>
                <option value="goat-art" {"selected" if source_filter == "goat-art" else ""}>Goat Art</option>
                <option value="rijksmuseum" {"selected" if source_filter == "rijksmuseum" else ""}>Rijksmuseum</option>
                <option value="nasa" {"selected" if source_filter == "nasa" else ""}>NASA APOD</option>
            </select>
        </div>
    </div>

    <div class="gallery-grid" id="gallery">
        {cards if cards else '<div class="empty-state"><h3>No images yet</h3><p>Push an image from the <a href="/">Dashboard</a> to start building your gallery.</p></div>'}
    </div>

    <footer>TRMNL Art Display &middot; {total} images across {sum(1 for s in ("goat-art","rijksmuseum","nasa") if counts.get(s,0) > 0)} sources</footer>
</div>

<script>
{_TOAST_JS}

function filterGallery(source) {{
    const cards = document.querySelectorAll('.gallery-card');
    let visible = 0;
    cards.forEach(card => {{
        if (source === 'all' || card.dataset.source === source) {{
            card.style.display = '';
            visible++;
        }} else {{
            card.style.display = 'none';
        }}
    }});
    document.getElementById('img-count').textContent = visible + ' images';
    // Update URL without reload
    const url = new URL(window.location);
    if (source === 'all') url.searchParams.delete('source');
    else url.searchParams.set('source', source);
    history.replaceState(null, '', url);
}}

async function deleteImage(source, filename, btn) {{
    if (!confirm('Delete this image from the gallery?')) return;
    const card = btn.closest('.gallery-card');
    try {{
        await apiCall('/api/galleries/' + source + '/' + filename, 'DELETE');
        card.style.transform = 'scale(0.95)';
        card.style.opacity = '0';
        card.style.transition = 'all 0.3s';
        setTimeout(() => {{
            card.remove();
            // Update count
            const remaining = document.querySelectorAll('.gallery-card:not([style*="display: none"])').length;
            document.getElementById('img-count').textContent = remaining + ' images';
        }}, 300);
        toast('Image deleted', 'success');
    }} catch(e) {{}}
}}

function zoomImage(img) {{
    const overlay = document.createElement('div');
    overlay.className = 'zoom-overlay';
    overlay.innerHTML = '<img src="' + img.src + '">';
    overlay.onclick = () => overlay.remove();
    document.addEventListener('keydown', function esc(e) {{
        if (e.key === 'Escape') {{ overlay.remove(); document.removeEventListener('keydown', esc); }}
    }});
    document.body.appendChild(overlay);
}}

// Apply initial filter from URL
const params = new URLSearchParams(window.location.search);
const initSource = params.get('source');
if (initSource && initSource !== 'all') {{
    document.getElementById('source-filter').value = initSource;
    filterGallery(initSource);
}}
</script>
</body></html>"""
