"""Assemble the Colab notebook from cell sources."""
import json, sys, os

VERSION, DATE = 'v2', '2026-10-13'
OUT = sys.argv[1] if len(sys.argv) > 1 else f'Drive_File_Manager_{VERSION}_{DATE}.ipynb'
HERE = os.path.dirname(os.path.abspath(__file__))
core = open(os.path.join(HERE, 'src', 'core.py'), encoding='utf-8').read()

def md(s):   return {'cell_type': 'markdown', 'metadata': {}, 'source': s.strip('\n')}
def code(s): return {'cell_type': 'code', 'metadata': {'cellView': 'form'}, 'execution_count': None, 'outputs': [], 'source': s.strip('\n')}

cells = [
md(f"""
<div align="right"><sub><b>Created by Ram Lakhan Meena, INSPECTOR CBIC</b><br>13-Oct-2026</sub></div>

# 🗂️ Drive File Manager for Google Colab — {VERSION}

Browse your Google Drive with **dropdowns**, **upload** from your computer (into an existing or a **new folder**),
and **download directly to your computer** — including Google Docs / Sheets / Slides.

### ▶️ How to use (top to bottom)
| Step | Cell | What it does |
|---|---|---|
| 1 | **① SETUP** | Connects Drive (approve the popup once). Set your start folder here. |
| 2 | **② PICKER** | Dropdowns to move between folders, select files, create a new folder, search. |
| 3 | **③ UPLOAD** | Pick files from your computer → saved in the picker's folder (or a new sub-folder). |
| 4 | **④ DOWNLOAD** | Downloads what you selected in ② straight to your computer. |
| – | ⑤ – ⑧ | Quick download by name · Colab workspace ⇄ Drive · Folder report · Disconnect. |

> Tip: click **Runtime → Run all** once, or run ① and ② and keep the picker open while you use ③ / ④.

### 📝 Version log
| Version | Date | Changes |
|---|---|---|
| v1 | before 13-Oct-2026 | Original connector: mount, list, copy to `/content`, upload helpers, export by name, zip-folder upload. |
| **v2** | **13-Oct-2026** | Full reorganisation into 8 numbered form cells (code hidden). **New dropdown picker** (Drive / sub-folder dropdowns, multi-select file list, Up / Home / Refresh, search, *open in Drive* link). **Fixed direct download**: Google Docs/Sheets/Slides/Drawings were being downloaded as useless `.gdoc/.gsheet` pointer files — they are now exported to Office or PDF (file ID read from the mount, no more guessing by name; export-link fallback for files > 10 MB). Regular files are checksum-verified, with Drive-API fallback if the mount read fails. Several files / whole folders download as one ZIP (Google files inside are exported too). **New folder** creation (picker button or upload option). Upload with *keep both / overwrite / skip* and optional auto-unzip. Fixed the f-string syntax error that broke exports on older Python. Removed duplicate mount cells. |
"""),
md("## ① Setup"),
code(core),
md("## ② Picker — choose folder & files\nUse the **Drive** and **Open sub-folder** dropdowns to move around. Click files in the list (Ctrl/Shift-click for several). Create a new folder or search from here too."),
code("""
#@title ② PICKER — run, then use the dropdowns { display-mode: "form" }
if 'PICKER' in globals():
    PICKER.show()
else:
    print("⚠️ Run cell ① SETUP first.")
"""),
md("## ③ Upload from your computer → Drive"),
code("""
#@title ③ UPLOAD files from your computer into Drive { display-mode: "form" }
#@markdown Files go into the folder currently open in the picker (cell ②) — or a new folder inside it.
save_into = "Folder open in the picker"  #@param ["Folder open in the picker", "A NEW folder inside it (type the name below)"]
new_folder_name = ""  #@param {type:"string"}
if_file_already_exists = "Keep both - add (1), (2)"  #@param ["Keep both - add (1), (2)", "Overwrite", "Skip"]
unzip_zip_files_after_upload = False  #@param {type:"boolean"}

if 'PICK' not in globals():
    print("⚠️ Run cell ① SETUP first.")
elif save_into.startswith('A NEW') and not new_folder_name.strip():
    print("⚠️ Type the new folder's name in 'new_folder_name' and run again.")
else:
    _dest = create_folder(PICK['folder'], new_folder_name) if save_into.startswith('A NEW') else PICK['folder']
    upload_from_computer(_dest, if_file_already_exists, unzip_zip_files_after_upload)
    PICKER.go(_dest)   # picker now shows the folder with your uploaded files
"""),
md("## ④ Download from Drive → your computer"),
code("""
#@title ④ DOWNLOAD to your computer { display-mode: "form" }
#@markdown Select file(s) / folder(s) in the picker (cell ②) first.
what_to_download = "Items selected in the picker"  #@param ["Items selected in the picker", "Entire folder open in the picker (as ZIP)"]
google_docs_sheets_slides_as = "Office (docx / xlsx / pptx)"  #@param ["Office (docx / xlsx / pptx)", "PDF"]
when_several_items = "One ZIP file"  #@param ["One ZIP file", "Separate files"]

if 'PICK' not in globals():
    print("⚠️ Run cell ① SETUP first.")
else:
    _items = [PICK['folder']] if what_to_download.startswith('Entire') else PICK['selected']
    download_items(_items, 'PDF' if google_docs_sheets_slides_as == 'PDF' else 'Office', when_several_items)
"""),
md("## ⑤ Quick download by file name"),
code("""
#@title ⑤ QUICK DOWNLOAD by name { display-mode: "form" }
#@markdown Type the name (or part of it). Extension is optional. If exactly one file matches it downloads at once; otherwise the matches are loaded into the picker for you to choose.
file_name = ""  #@param {type:"string"}
search_in = "Whole of My Drive"  #@param ["Whole of My Drive", "Folder open in the picker"]
match_type = "Name contains the text"  #@param ["Name contains the text", "Exact name"]
google_files_as = "Office (docx / xlsx / pptx)"  #@param ["Office (docx / xlsx / pptx)", "PDF"]

if not file_name.strip():
    print("⚠️ Type a file name above and run again.")
else:
    _root = MY_DRIVE if search_in.startswith('Whole') else PICK['folder']
    print(f"🔍 Searching '{file_name}' in {rel(_root)} …")
    _res, _cut = search_drive(_root, file_name, exact=match_type == 'Exact name')
    _files = [r for r in _res if os.path.isfile(r)]
    if len(_files) == 1:
        print(f"Found: {rel(_files[0])}")
        download_items(_files, 'PDF' if google_files_as == 'PDF' else 'Office')
    elif not _res:
        print("❌ No match. Check the spelling or try fewer letters.")
    else:
        PICKER.show_results(_res, f"{len(_res)} result(s) for '{file_name}'")
        print(f"Found {len(_res)} matches" + (" (stopped early)" if _cut else "") + " — they are now listed in the picker (cell ②). Select one, then run ④.")
"""),
md("## ⑥ Colab workspace ⇄ Drive\nFor files produced by other code in this runtime (e.g. `/content/report.xlsx`), or to bring Drive files into `/content` for processing."),
code("""
#@title ⑥ COLAB WORKSPACE ⇄ DRIVE { display-mode: "form" }
action = "Copy picker selection → Colab workspace (/content/from_drive)"  #@param ["Copy picker selection → Colab workspace (/content/from_drive)", "Copy a Colab file/folder → folder open in the picker"]
colab_path = "/content/your_file_or_folder"  #@param {type:"string"}
zip_folder_before_copying = False  #@param {type:"boolean"}
google_files_as = "Office (docx / xlsx / pptx)"  #@param ["Office (docx / xlsx / pptx)", "PDF"]

_fmt = 'PDF' if google_files_as == 'PDF' else 'Office'
if action.startswith('Copy picker'):
    os.makedirs(FROM_DRIVE_DIR, exist_ok=True)
    if not PICK['selected']:
        print("⚠️ Select item(s) in the picker first.")
    for _p in PICK['selected']:
        if os.path.isdir(_p):
            _dst = unique_path(os.path.join(FROM_DRIVE_DIR, os.path.basename(_p)))
            shutil.copytree(_p, _dst, ignore=shutil.ignore_patterns(*[f'*{e}' for e in list(NATIVE) + list(NOT_EXPORTABLE)]))
        else:
            _dst = fetch_file(_p, _fmt, FROM_DRIVE_DIR)
        print(f"✅ {rel(_p)}  →  {_dst}")
else:
    _src = colab_path.rstrip('/')
    if not os.path.exists(_src):
        print(f"❌ Not found in Colab: {_src}")
    else:
        if os.path.isdir(_src) and zip_folder_before_copying:
            _src = shutil.make_archive(os.path.join(TMP_DIR, os.path.basename(_src)), 'zip', _src)
        _dst = unique_path(os.path.join(PICK['folder'], os.path.basename(_src)))
        if os.path.isdir(_src):
            shutil.copytree(_src, _dst)
        else:
            shutil.copyfile(_src, _dst)
            print("   checksum", "OK ✅" if md5_file(_src) == md5_file(_dst) else "MISMATCH ⚠️")
        print(f"✅ {_src}  →  {rel(_dst)}")
        PICKER.go(PICK['folder'])
"""),
md("## ⑦ Folder report"),
code("""
#@title ⑦ FOLDER REPORT (tree of the folder open in the picker) { display-mode: "form" }
levels_deep = 2  #@param {type:"slider", min:1, max:6, step:1}
also_download_full_listing_as_csv = False  #@param {type:"boolean"}

import csv
_root = PICK['folder']; _rows = []; _nf = _nd = _tot = 0
print(f"📍 {rel(_root)}")
for _r, _ds, _fs in os.walk(_root):
    _ds.sort(); _depth = os.path.relpath(_r, _root).count(os.sep) + (0 if _r == _root else 1)
    if _r != _root:
        _nd += 1
        if _depth <= levels_deep: print('   ' * (_depth - 1) + f"📁 {os.path.basename(_r)}/")
    for _f in sorted(_fs):
        _p = os.path.join(_r, _f)
        try: _s = os.path.getsize(_p)
        except OSError: _s = 0
        _nf += 1; _tot += _s
        _rows.append([os.path.relpath(_p, _root), NATIVE.get(ext_of(_f), {}).get('type') or NOT_EXPORTABLE.get(ext_of(_f)) or (ext_of(_f)[1:].upper() or 'file'), _s,
                      datetime.datetime.fromtimestamp(os.path.getmtime(_p)).strftime('%Y-%m-%d %H:%M')])
        if _depth < levels_deep: print('   ' * _depth + f"{icon_of(_p)} {_f}  ({human(_s)})")
print(f"\\nTotal: {_nf} files, {_nd} sub-folders, {human(_tot)}")
if also_download_full_listing_as_csv:
    _csv = os.path.join(DL_DIR, f"listing_{os.path.basename(_root)}_{datetime.date.today()}.csv")
    with open(_csv, 'w', newline='', encoding='utf-8-sig') as _fh:
        _w = csv.writer(_fh); _w.writerow(['Path', 'Type', 'Size (bytes)', 'Modified']); _w.writerows(_rows)
    browser_download(_csv)
"""),
md("## ⑧ Finish"),
code("""
#@title ⑧ DISCONNECT DRIVE (optional — run when completely done) { display-mode: "form" }
#@markdown Makes sure every upload is fully written to Drive before the runtime closes.
confirm_disconnect = False  #@param {type:"boolean"}
if confirm_disconnect:
    drive.flush_and_unmount()
    print("✅ All writes flushed. Drive disconnected — run ① again to reconnect.")
else:
    print("Tick 'confirm_disconnect' and run again to disconnect.")
"""),
md("""
## ❓ Troubleshooting
* **Downloaded file opens as garbage / is only a few bytes** — that was the v1 bug with Google Docs/Sheets. v2 exports them; make sure you ran ① in this session.
* **Only one of several files downloaded** — your browser blocked multiple downloads. Allow it for `colab.research.google.com`, or choose *One ZIP file*.
* **A popup asks to sign in** — this is needed only once per session for Google Docs/Sheets/Slides export.
* **New upload not visible on drive.google.com** — Drive syncs in the background; wait a minute or run ⑧.
* **"Run cell ① SETUP first"** — the runtime restarted; run ① and ② again.
"""),
]

nb = {'nbformat': 4, 'nbformat_minor': 0,
      'metadata': {'colab': {'provenance': [], 'toc_visible': True, 'name': os.path.basename(OUT)},
                   'kernelspec': {'name': 'python3', 'display_name': 'Python 3'}, 'language_info': {'name': 'python'}},
      'cells': cells}
for c in nb['cells']:
    s = c['source']; lines = s.split('\n')
    c['source'] = [l + '\n' for l in lines[:-1]] + [lines[-1]]
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
print('wrote', OUT, len(cells), 'cells')
