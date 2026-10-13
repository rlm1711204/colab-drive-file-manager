# 🗂️ Drive File Manager for Google Colab

<p align="right"><sub>Created by Ram Lakhan Meena, INSPECTOR CBIC · 13-Oct-2026</sub></p>

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/rlm1711204/colab-drive-file-manager/blob/main/Drive_File_Manager_v2_2026-10-13.ipynb)

A Colab notebook to manage Google Drive files with dropdowns — no code editing needed.

| Cell | What it does |
|---|---|
| ① Setup | Connects Drive, loads the tool, sets the start folder |
| ② Picker | Drive / sub-folder dropdowns, multi-select file list, ⬆ Up / 🏠 Home / 🔄 Refresh, ➕ new folder, 🔍 search, *open in Drive* link |
| ③ Upload | Computer → Drive, into the open folder or a **new folder**; keep both / overwrite / skip; optional auto-unzip |
| ④ Download | Drive → computer, **direct**. Google Docs/Sheets/Slides exported to Office or PDF; several items or whole folders as one ZIP |
| ⑤ Quick download | By file name (exact or contains, `*` `?` wildcards) |
| ⑥ Workspace ⇄ Drive | Copy between `/content` and Drive |
| ⑦ Folder report | Tree view + CSV listing |
| ⑧ Disconnect | Flush writes and unmount |

## What v2 fixed
Google-native files appear on the mounted Drive only as `.gdoc` / `.gsheet` / `.gslides` pointer files, so downloading them gave an unusable file. v2 reads the real file ID from the mount and exports through the Drive API (with an export-link fallback for files over 10 MB). Regular files are checksum-verified and fall back to the Drive API if a mount read fails.

## Maintaining
`src/core.py` is the setup cell; `build.py` assembles the notebook: `python build.py`.
