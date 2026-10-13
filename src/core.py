#@title ① SETUP — run this first (connects Google Drive and loads the tool) { display-mode: "form" }
#@markdown **Folder the picker should open in** (inside *My Drive*; created if missing):
START_FOLDER = "File for Working in"  #@param {type:"string"}

import sys, os, io, re, json, time, shutil, hashlib, zipfile, datetime, fnmatch

if 'google.colab' not in sys.modules:
    raise RuntimeError("This notebook only works inside Google Colab (colab.research.google.com).")

from google.colab import drive, auth, files as colab_files
from IPython.display import display, HTML
import ipywidgets as W

# ───────────────────────── paths ─────────────────────────
MOUNT_POINT    = '/content/drive'
MY_DRIVE       = os.path.join(MOUNT_POINT, 'MyDrive')
SHARED_DRIVES  = os.path.join(MOUNT_POINT, 'Shareddrives')
WORK_DIR       = '/content/_drive_tool'
DL_DIR         = os.path.join(WORK_DIR, 'downloads')     # files staged here before the browser download
TMP_DIR        = os.path.join(WORK_DIR, 'tmp')
FROM_DRIVE_DIR = '/content/from_drive'                   # "copy to Colab workspace" target

if not os.path.isdir(MY_DRIVE):
    drive.mount(MOUNT_POINT)
for _d in (DL_DIR, TMP_DIR):
    os.makedirs(_d, exist_ok=True)

# ───────────────────── Google-native files ─────────────────────
# On the mounted Drive, Google Docs/Sheets/Slides are only tiny ".gdoc/.gsheet/.gslides" pointer files.
# Copying or downloading those pointers gives a useless file — they must be EXPORTED through the Drive API.
_PDF  = 'application/pdf'
NATIVE = {
    '.gdoc':    {'type': 'Google Doc',     'Office': ('docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'), 'PDF': ('pdf', _PDF)},
    '.gsheet':  {'type': 'Google Sheet',   'Office': ('xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),      'PDF': ('pdf', _PDF)},
    '.gslides': {'type': 'Google Slides',  'Office': ('pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation'), 'PDF': ('pdf', _PDF)},
    '.gdraw':   {'type': 'Google Drawing', 'Office': ('png',  'image/png'),                                                               'PDF': ('pdf', _PDF)},
}
NOT_EXPORTABLE = {'.gform': 'Google Form', '.gsite': 'Google Site', '.gmap': 'Google My Map',
                  '.gtable': 'Google Table', '.gjam': 'Jamboard', '.gscript': 'Apps Script', '.glink': 'Drive link'}

_ICONS = {'.pdf': '📕', '.xlsx': '📊', '.xls': '📊', '.xlsm': '📊', '.csv': '📊', '.gsheet': '📊',
          '.doc': '📝', '.docx': '📝', '.gdoc': '📝', '.txt': '📝', '.ppt': '📽️', '.pptx': '📽️', '.gslides': '📽️',
          '.jpg': '🖼️', '.jpeg': '🖼️', '.png': '🖼️', '.gif': '🖼️', '.zip': '🗜️', '.rar': '🗜️', '.7z': '🗜️',
          '.ipynb': '📓', '.py': '🐍', '.mp4': '🎬', '.mp3': '🎵', '.json': '🔧', '.db': '🗄️', '.sqlite': '🗄️'}

def ext_of(p):        return os.path.splitext(p)[1].lower()
def is_native(p):     return ext_of(p) in NATIVE or ext_of(p) in NOT_EXPORTABLE
def icon_of(p):       return '📁' if os.path.isdir(p) else _ICONS.get(ext_of(p), '📄')

def human(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f"{n:.0f} {unit}" if unit == 'B' else f"{n:.1f} {unit}"
        n /= 1024

def md5_file(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def unique_path(p):
    """'a.pdf' -> 'a (1).pdf' -> 'a (2).pdf' … if the name is already taken."""
    if not os.path.exists(p):
        return p
    base, ext = os.path.splitext(p)
    if os.path.isdir(p):
        base, ext = p, ''
    i = 1
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"

def safe_name(name):
    name = re.sub(r'[\x00-\x1f/\\]', '-', (name or '').strip())
    if name in ('', '.', '..'):
        raise ValueError("Please type a valid name.")
    return name

def rel(p):
    """Short display path: 'My Drive › A › B'."""
    p = os.path.normpath(p)
    if p.startswith(MY_DRIVE):
        tail = os.path.relpath(p, MY_DRIVE)
        return 'My Drive' + ('' if tail == '.' else ' › ' + tail.replace(os.sep, ' › '))
    if p.startswith(SHARED_DRIVES):
        return 'Shared drives › ' + os.path.relpath(p, SHARED_DRIVES).replace(os.sep, ' › ')
    return p

def folder_size(p):
    total = 0
    for r, _, fs in os.walk(p):
        for f in fs:
            try: total += os.path.getsize(os.path.join(r, f))
            except OSError: pass
    return total

# ───────────────────────── Drive API (only used for Google-native files & fallbacks) ─────────────────────────
_SVC = None
def drive_api():
    global _SVC
    if _SVC is None:
        print("🔐 One-time Google sign-in (needed to export Google Docs/Sheets/Slides). Approve the popup if it appears…")
        auth.authenticate_user()
        from googleapiclient.discovery import build
        _SVC = build('drive', 'v3', cache_discovery=False)
    return _SVC

def drive_id(path):
    """File ID straight from the mounted file (Colab stores it as an extended attribute) — no name guessing."""
    try:
        return os.getxattr(path, 'user.drive.id').decode().strip() or None
    except Exception:
        pass
    try:  # some pointer files contain JSON like {"doc_id": "..."}
        if os.path.isfile(path) and os.path.getsize(path) < 8192:
            with open(path, encoding='utf-8', errors='ignore') as f:
                d = json.load(f)
            v = d.get('doc_id') or d.get('resource_id', '')
            return v.split(':')[-1] or None
    except Exception:
        pass
    return None

def folder_link(path):
    fid = drive_id(path)
    return f"https://drive.google.com/drive/folders/{fid}" if fid else None

def resolve_id(path):
    fid = drive_id(path)
    if fid:
        return fid
    name = os.path.basename(path)
    if is_native(path):
        name = os.path.splitext(name)[0]
    q_name = name.replace('\\', '\\\\').replace("'", "\\'")
    q = f"name = '{q_name}' and trashed = false"
    parent = drive_id(os.path.dirname(path))
    if parent:
        q += f" and '{parent}' in parents"
    found = drive_api().files().list(q=q, fields='files(id,name,mimeType)', pageSize=10,
                                     supportsAllDrives=True, includeItemsFromAllDrives=True).execute().get('files', [])
    if is_native(path):
        found = [f for f in found if f['mimeType'].startswith('application/vnd.google-apps')] or found
    if not found:
        raise FileNotFoundError(f"Drive could not find '{name}'.")
    if len(found) > 1:
        print(f"   ⚠️ {len(found)} files are called '{name}'; using the first one.")
    return found[0]['id']

def _stream_to_file(request, out_path):
    from googleapiclient.http import MediaIoBaseDownload
    with io.FileIO(out_path, 'wb') as fh:
        dl, done = MediaIoBaseDownload(fh, request, chunksize=8 << 20), False
        while not done:
            _, done = dl.next_chunk()

def export_native(path, fmt, out_dir):
    """Export a Google Doc/Sheet/Slides/Drawing to Office or PDF. fmt = 'Office' | 'PDF'."""
    ext = ext_of(path)
    if ext in NOT_EXPORTABLE:
        raise ValueError(f"{NOT_EXPORTABLE[ext]} files cannot be downloaded — open them in Drive instead.")
    out_ext, mime = NATIVE[ext][fmt]
    fid = resolve_id(path)
    out = unique_path(os.path.join(out_dir, f"{os.path.splitext(os.path.basename(path))[0]}.{out_ext}"))
    svc = drive_api()
    from googleapiclient.errors import HttpError
    try:
        _stream_to_file(svc.files().export_media(fileId=fid, mimeType=mime), out)
    except HttpError as e:
        if os.path.exists(out): os.remove(out)
        if 'exportSizeLimitExceeded' not in str(e) and getattr(e, 'resp', None) is not None and e.resp.status != 403:
            raise
        # Large files (> 10 MB export limit): use the export link instead
        url = svc.files().get(fileId=fid, fields='exportLinks', supportsAllDrives=True).execute().get('exportLinks', {}).get(mime)
        if not url:
            raise
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        creds, _ = google.auth.default()
        r = AuthorizedSession(creds).get(url, stream=True)
        r.raise_for_status()
        with open(out, 'wb') as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return out

def copy_regular(src, out_dir):
    """Copy a normal Drive file out of the mount (checksum-verified); fall back to the Drive API if the mount read fails."""
    dst = unique_path(os.path.join(out_dir, os.path.basename(src)))
    try:
        shutil.copyfile(src, dst)
        if md5_file(src) != md5_file(dst):
            raise IOError('checksum mismatch')
    except Exception as e:
        print(f"   ↪ Mount copy failed ({e}); fetching through the Drive API instead…")
        if os.path.exists(dst): os.remove(dst)
        _stream_to_file(drive_api().files().get_media(fileId=resolve_id(src), supportsAllDrives=True), dst)
    return dst

def fetch_file(path, fmt, out_dir):
    return export_native(path, fmt, out_dir) if is_native(path) else copy_regular(path, out_dir)

def zip_items(paths, zip_path, fmt):
    """ZIP files and folders. Google-native files inside are exported (not zipped as useless pointers)."""
    skipped, count = [], 0
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        def add(full, arc):
            nonlocal count
            if ext_of(full) in NOT_EXPORTABLE:
                skipped.append(arc); return
            if is_native(full):
                tmp = export_native(full, fmt, TMP_DIR)
                arc = os.path.splitext(arc)[0] + os.path.splitext(tmp)[1]
                zf.write(tmp, arc); os.remove(tmp)
            else:
                try:
                    zf.write(full, arc)
                except OSError:
                    tmp = copy_regular(full, TMP_DIR); zf.write(tmp, arc); os.remove(tmp)
            count += 1
            print(f"   + {arc}")
        for p in paths:
            if os.path.isdir(p):
                base = os.path.dirname(os.path.normpath(p))
                for r, ds, fs in os.walk(p):
                    ds.sort()
                    if not fs and not ds:
                        zf.writestr(os.path.relpath(r, base) + '/', '')
                    for f in sorted(fs):
                        add(os.path.join(r, f), os.path.relpath(os.path.join(r, f), base))
            else:
                add(p, os.path.basename(p))
    if skipped:
        print(f"   ⚠️ Skipped {len(skipped)} item(s) that Google does not allow to download (Forms, Sites…): {', '.join(skipped[:5])}")
    return zip_path, count

def _clean_old_downloads(minutes=15):
    now = time.time()
    for f in os.listdir(DL_DIR):
        p = os.path.join(DL_DIR, f)
        try:
            if now - os.path.getmtime(p) > minutes * 60:
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        except OSError:
            pass

def browser_download(local_path):
    size = os.path.getsize(local_path)
    print(f"⬇️  Sending to your browser: {os.path.basename(local_path)}  ({human(size)})")
    if size > 1.5 * 1024 ** 3:
        print("   ⚠️ Very large file — the browser download may be slow or fail; downloading from drive.google.com is safer.")
    colab_files.download(local_path)

def download_items(paths, fmt='Office', several='One ZIP file'):
    """THE fixed direct download: Drive → (export / verified copy) → your computer."""
    paths = [p for p in paths if p]
    if not paths:
        print("⚠️ Nothing selected. In the picker (cell ②) click file(s) — Ctrl/Shift-click for several — then run this cell again.")
        return []
    _clean_old_downloads()
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    run_dir = unique_path(os.path.join(DL_DIR, stamp)); os.makedirs(run_dir)
    out = []
    if len(paths) == 1 and not os.path.isdir(paths[0]):
        out.append(fetch_file(paths[0], fmt, run_dir))
    elif len(paths) == 1:
        z = os.path.join(run_dir, f"{os.path.basename(os.path.normpath(paths[0]))}.zip")
        print(f"🗜️ Zipping folder '{os.path.basename(paths[0])}'…")
        out.append(zip_items(paths, unique_path(z), fmt)[0])
    elif several.startswith('One ZIP'):
        print(f"🗜️ Zipping {len(paths)} items…")
        out.append(zip_items(paths, os.path.join(run_dir, f"Drive_download_{stamp}.zip"), fmt)[0])
    else:
        for p in paths:
            if os.path.isdir(p):
                out.append(zip_items([p], unique_path(os.path.join(run_dir, os.path.basename(p) + '.zip')), fmt)[0])
            elif ext_of(p) in NOT_EXPORTABLE:
                print(f"   ⚠️ Skipped {os.path.basename(p)} ({NOT_EXPORTABLE[ext_of(p)]} cannot be downloaded)")
            else:
                out.append(fetch_file(p, fmt, run_dir))
    for i, f in enumerate(out):
        browser_download(f)
        if i < len(out) - 1:
            time.sleep(1.5)   # gives the browser time between downloads
    if len(out) > 1:
        print("ℹ️ If only one file arrived, allow 'multiple downloads' for colab.research.google.com in your browser.")
    print("✅ Done. Check your browser's Downloads folder.")
    return out

# ───────────────────────── upload & folders ─────────────────────────
def create_folder(parent, name):
    path = os.path.join(parent, safe_name(name))
    if os.path.isdir(path):
        print(f"ℹ️ Folder already exists, using it: {rel(path)}")
    else:
        os.makedirs(path)
        print(f"📁 Created folder: {rel(path)}")
    return path

def save_bytes(dest_dir, name, data, policy):
    """policy: 'Keep both' | 'Overwrite' | 'Skip'."""
    dst = os.path.join(dest_dir, safe_name(name))
    if os.path.exists(dst):
        if policy.startswith('Skip'):
            print(f"   ⏭️ Skipped (already exists): {name}"); return None
        if policy.startswith('Keep both'):
            dst = unique_path(dst)
    with open(dst, 'wb') as f:
        f.write(data)
    ok = hashlib.md5(data).hexdigest() == md5_file(dst)
    print(f"   {'✅' if ok else '⚠️ CHECKSUM MISMATCH'} {os.path.basename(dst)}  ({human(len(data))})")
    return dst

def unzip_into(zip_file, dest_dir, policy):
    target = os.path.join(dest_dir, os.path.splitext(os.path.basename(zip_file))[0])
    if os.path.exists(target) and policy.startswith('Keep both'):
        target = unique_path(target)
    elif os.path.exists(target) and policy.startswith('Skip'):
        print(f"   ⏭️ Folder '{os.path.basename(target)}' already exists — not unzipped."); return None
    with zipfile.ZipFile(zip_file) as zf:
        members = [m for m in zf.namelist() if not m.startswith('__MACOSX/') and not os.path.basename(m).startswith('._')]
        zf.extractall(target, members)      # extractall strips '..' and absolute paths
    print(f"   📦 Unzipped {len(members)} item(s) → {rel(target)}")
    return target

def upload_from_computer(dest_dir, policy='Keep both', unzip=False):
    os.makedirs(dest_dir, exist_ok=True)
    print(f"📤 Uploading into: {rel(dest_dir)}\n   Click 'Choose Files' below (you can select several).")
    cwd = os.getcwd(); os.chdir(TMP_DIR)          # stray copies Colab writes go to the temp folder
    try:
        picked = colab_files.upload()
    finally:
        os.chdir(cwd)
    saved = []
    for name, data in picked.items():
        dst = save_bytes(dest_dir, name, data, policy)
        if dst:
            saved.append(dst)
            if unzip and ext_of(dst) == '.zip':
                if unzip_into(dst, dest_dir, policy):
                    os.remove(dst)
        try: os.remove(os.path.join(TMP_DIR, name))
        except OSError: pass
    print(f"✅ {len(saved)} file(s) saved to Drive. (Drive syncs in the background — they appear on drive.google.com within a minute.)" if saved else "No files uploaded.")
    return saved

def search_drive(root, text, exact=False, limit=300, seconds=90):
    text = text.strip(); t = text.lower(); res, t0 = [], time.time()
    wild = any(c in text for c in '*?')
    for r, ds, fs in os.walk(root):
        ds.sort()
        for n in ds + fs:
            nl = n.lower()
            hit = fnmatch.fnmatch(nl, t) if wild else (nl == t or (is_native(n) and os.path.splitext(nl)[0] == t)) if exact else (t in nl)
            if hit:
                res.append(os.path.join(r, n))
                if len(res) >= limit: return res, True
        if time.time() - t0 > seconds:
            return res, True
    return res, False

# ───────────────────────── the picker (dropdowns) ─────────────────────────
PICK = {'folder': None, 'selected': []}

def _roots():
    roots = [('My Drive', MY_DRIVE)]
    if os.path.isdir(SHARED_DRIVES):
        roots += [(f'Shared drive: {d}', os.path.join(SHARED_DRIVES, d)) for d in sorted(os.listdir(SHARED_DRIVES))]
    return roots

def _label(p, base=None):
    name = (rel(p) if base == MOUNT_POINT else os.path.relpath(p, base)) if base else os.path.basename(p)
    if os.path.isdir(p):
        return f"📁 {name}/"
    try: size = human(os.path.getsize(p))
    except OSError: size = '?'
    e = ext_of(p)
    if e in NATIVE:         return f"{icon_of(p)} {name}   — {NATIVE[e]['type']} (exported on download)"
    if e in NOT_EXPORTABLE: return f"🚫 {name}   — {NOT_EXPORTABLE[e]} (cannot be downloaded)"
    return f"{icon_of(p)} {name}   — {size}"

class DrivePicker:
    def __init__(self, start):
        L = W.Layout
        self._busy = False
        self.root_dd   = W.Dropdown(options=_roots(), description='Drive:', layout=L(width='340px'))
        self.up_btn    = W.Button(description='⬆ Up', layout=L(width='70px'))
        self.home_btn  = W.Button(description='🏠 Start folder', layout=L(width='130px'))
        self.ref_btn   = W.Button(description='🔄 Refresh', layout=L(width='100px'))
        self.crumb     = W.HTML()
        self.sub_dd    = W.Dropdown(description='📂 Open sub-folder:', style={'description_width': 'initial'}, layout=L(width='560px'))
        self.items     = W.SelectMultiple(options=[], rows=14, layout=L(width='98%'))
        self.all_btn   = W.Button(description='Select all', layout=L(width='100px'))
        self.none_btn  = W.Button(description='Clear', layout=L(width='70px'))
        self.info      = W.HTML()
        self.new_txt   = W.Text(placeholder='e.g. Scrutiny Reports Oct-2026', description='New folder:', layout=L(width='420px'))
        self.new_btn   = W.Button(description='➕ Create & open', button_style='success', layout=L(width='140px'))
        self.find_txt  = W.Text(placeholder='part of a name, e.g. GSTR3B  (wildcards * ? allowed)', description='Search:', layout=L(width='420px'))
        self.find_where= W.Dropdown(options=['in this folder', 'in whole Drive'], layout=L(width='140px'))
        self.find_btn  = W.Button(description='🔍 Search', button_style='info', layout=L(width='100px'))
        self.back_btn  = W.Button(description='↩ Back to folder', button_style='warning', layout=L(width='140px', display='none'))
        self.msg       = W.Output(layout=L(max_height='160px', overflow='auto'))

        self.root_dd.observe(self._on_root, names='value')
        self.sub_dd.observe(self._on_sub, names='value')
        self.items.observe(self._on_items, names='value')
        self.up_btn.on_click(lambda _: self._safe(self.go, os.path.dirname(PICK['folder'])))
        self.home_btn.on_click(lambda _: self._safe(self.go, self.start))
        self.ref_btn.on_click(lambda _: self._safe(self.go, PICK['folder']))
        self.back_btn.on_click(lambda _: self._safe(self.go, PICK['folder']))
        self.all_btn.on_click(lambda _: setattr(self.items, 'value', tuple(v for _, v in self.items.options)))
        self.none_btn.on_click(lambda _: setattr(self.items, 'value', ()))
        self.new_btn.on_click(lambda _: self._safe(self._new_folder))
        self.find_btn.on_click(lambda _: self._safe(self._search))

        self.start = start
        self.go(start)

    # helpers
    def _safe(self, fn, *a):
        with self.msg:
            try: fn(*a)
            except Exception as e: print(f"❌ {type(e).__name__}: {e}")

    def _root_of(self, p):
        best = MY_DRIVE
        for _, r in self.root_dd.options:
            if p.startswith(r) and len(r) >= len(best): best = r
        return best

    def go(self, path):
        path = os.path.normpath(path)
        if not path.startswith(MOUNT_POINT) or os.path.normpath(path) in (MOUNT_POINT, SHARED_DRIVES):
            path = self._root_of(PICK['folder'] or MY_DRIVE)
        if not os.path.isdir(path):
            raise FileNotFoundError(f"Folder not found: {path}")
        self._busy = True
        try:
            PICK['folder'], PICK['selected'] = path, []
            with os.scandir(path) as it:
                entries = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
            dirs = [e.path for e in entries if e.is_dir()]
            self.sub_dd.options = [(f'— choose ({len(dirs)} sub-folder{"s" if len(dirs) != 1 else ""}) —', '')] + [(f'📁 {os.path.basename(d)}', d) for d in dirs]
            self.sub_dd.value = ''
            self.items.options = [(_label(e.path), e.path) for e in entries]
            self.items.value = ()
            self.root_dd.value = self._root_of(path)
            link = folder_link(path)
            self.crumb.value = (f"<div style='font-size:15px;margin:4px 0'><b>📍 {rel(path)}</b>"
                                + (f" &nbsp;<a href='{link}' target='_blank'>open in Drive ↗</a>" if link else '') + "</div>")
            self.back_btn.layout.display = 'none'
            self.up_btn.disabled = path == self._root_of(path)
            self._update_info()
        finally:
            self._busy = False

    def show_results(self, results, title):
        self._busy = True
        try:
            base = PICK['folder'] if all(r.startswith(PICK['folder'] + os.sep) for r in results) else MOUNT_POINT
            self.items.options = [(_label(r, base), r) for r in results]
            self.items.value = ()
            PICK['selected'] = []
            self.crumb.value = f"<div style='font-size:15px;margin:4px 0'><b>🔍 {title}</b> — select, then run cell ④</div>"
            self.back_btn.layout.display = ''
            self._update_info()
        finally:
            self._busy = False

    def _update_info(self):
        sel = PICK['selected']
        if not sel:
            self.info.value = f"<i>{len(self.items.options)} item(s). Click to select · Ctrl/Shift-click for several.</i>"
            return
        size = sum(os.path.getsize(p) for p in sel if os.path.isfile(p) and not is_native(p))
        nd = sum(os.path.isdir(p) for p in sel)
        self.info.value = (f"<b style='color:#1a7f37'>✔ {len(sel)} selected</b> ({human(size)}"
                           + (f" + {nd} folder(s)" if nd else '') + ") — now run cell ④ to download")

    # events
    def _on_root(self, ch):
        if not self._busy: self._safe(self.go, ch['new'])
    def _on_sub(self, ch):
        if not self._busy and ch['new']: self._safe(self.go, ch['new'])
    def _on_items(self, ch):
        if not self._busy:
            PICK['selected'] = list(ch['new']); self._update_info()

    def _new_folder(self):
        p = create_folder(PICK['folder'], self.new_txt.value)
        self.new_txt.value = ''
        self.go(p)

    def _search(self):
        text = self.find_txt.value.strip()
        if not text:
            print("Type part of a file name first."); return
        root = PICK['folder'] if self.find_where.value == 'in this folder' else self._root_of(PICK['folder'])
        print(f"Searching '{text}' in {rel(root)} …")
        res, cut = search_drive(root, text)
        print(f"Found {len(res)} match(es)" + (" (stopped early — refine the search)" if cut else '') + '.')
        self.show_results(res, f"{len(res)} result(s) for '{text}'")

    @property
    def ui(self):
        header = HTML("""<div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div style="font-size:18px;font-weight:600">🗂️ Drive File Manager — picker</div>
            <div style="text-align:right;font-size:11px;color:#666">Created by Ram Lakhan Meena, INSPECTOR CBIC<br>13-Oct-2026 · v2</div></div>""")
        box = W.VBox([
            W.HBox([self.root_dd, self.up_btn, self.home_btn, self.ref_btn]),
            self.crumb, self.sub_dd,
            W.HTML("<b>Files &amp; folders here</b> (select what you want to download):"),
            self.items, W.HBox([self.all_btn, self.none_btn, self.back_btn, self.info]),
            W.HTML("<hr style='margin:6px 0'>"),
            W.HBox([self.new_txt, self.new_btn]),
            W.HBox([self.find_txt, self.find_where, self.find_btn]),
            self.msg])
        return header, box

    def show(self):
        h, b = self.ui
        display(h, b)

start_path = os.path.join(MY_DRIVE, START_FOLDER.strip()) if START_FOLDER.strip() else MY_DRIVE
os.makedirs(start_path, exist_ok=True)
PICKER = DrivePicker(start_path)

display(HTML(f"<div style='padding:8px 12px;border-left:4px solid #1a7f37;background:#f0fff4;color:#111'>"
             f"✅ <b>Ready.</b> Drive connected. Start folder: <b>{rel(start_path)}</b>.<br>"
             f"Next → run cell <b>②</b> to open the picker.</div>"))
