from __future__ import annotations

import base64
import gzip
import json
import types
import socket
import os
import re
import sys
import threading
import time
import traceback
import math
import subprocess
import tempfile
import tkinter as tk
import hashlib
import shutil
from pathlib import Path
from tkinter import messagebox
from urllib import error as urllib_error
from urllib import request as urllib_request
from cryptography.fernet import Fernet


HOST = "127.0.0.1"
PORT = 8765
BOOT_TIMEOUT_SEC = 45.0
SPLASH_FRAME_MS = 16
SPLASH_READY_POLL_SEC = 0.18
SPLASH_DOT_PERIOD_SEC = 0.33
SPLASH_ARC_DEG_PER_SEC = 230.0
SPLASH_ORBIT_DEG_PER_SEC = 165.0
MIN_SPLASH_SEC = 4.0
REQUIRE_LICENSE = os.environ.get("ZEUS_REQUIRE_LICENSE", "0").strip() == "1"
PROTECTED_ZEUS_BLOB = "zeus_integ2.pzb"
APP_SECRET_A = "ZEUS_CORE_LAYER_A_v3"
APP_SECRET_B = "QDASH_LOCK_B_2026"
UPDATE_CONFIG_FILE = "zeus_update_config.json"
VERSION_FILE = "zeus_version.json"
UPDATE_TIMEOUT_SEC = 8
UPDATE_TMP_PREFIX = "zeus_update_"
EMBED_UI_ENV = "ZEUS_EMBED_UI"
EMBED_WAIT_SEC = 180
DATA_DIR_ENV = "ZEUS_DATA_DIR"
DATA_ROOT_DIRNAME = "ZeusInteg"
DATA_SUBDIRNAME = "data"
DATA_MIGRATION_MARKER = ".zeus_data_migrated_v1"
DATA_MIGRATION_ENTRIES = (
    ".env",
    ".bt_cache_v12b",
    "ta_audit",
    ".price_cache.pkl",
    "zeus_audit_log.json",
    "zeus_signals.json",
    "screener_results.json",
    "positions.json",
    "zeus_regime.json",
    "zeus_unified.html",
    "zeus_out_dashboard.html",
    "zeus_out_backtest.html",
    "zeus_out_analyzer.html",
    "zeus_out_trading.html",
    "backtest_smartscore.html",
    "zeus_backtest_report.html",
    "market_dashboard.html",
)

_boot_error: str | None = None
_boot_done = threading.Event()
_user_data_dir_cache: Path | None = None


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
    return _base_dir()


def _default_user_data_dir() -> Path:
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / DATA_ROOT_DIRNAME / DATA_SUBDIRNAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / DATA_ROOT_DIRNAME / DATA_SUBDIRNAME
    xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg_data_home:
        return Path(xdg_data_home) / DATA_ROOT_DIRNAME / DATA_SUBDIRNAME
    return Path.home() / ".local" / "share" / DATA_ROOT_DIRNAME / DATA_SUBDIRNAME


def _migrate_legacy_data_if_needed(dst_dir: Path) -> None:
    marker = dst_dir / DATA_MIGRATION_MARKER
    if marker.exists():
        return
    src_dir = _base_dir()
    if src_dir == dst_dir:
        try:
            marker.write_text("same_dir\n", encoding="utf-8")
        except Exception:
            pass
        return

    for name in DATA_MIGRATION_ENTRIES:
        src = src_dir / name
        dst = dst_dir / name
        if not src.exists() or dst.exists():
            continue
        try:
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        except Exception:
            pass

    try:
        marker.write_text(f"migrated_at={time.time()}\nfrom={src_dir}\n", encoding="utf-8")
    except Exception:
        pass


def _user_data_dir() -> Path:
    global _user_data_dir_cache
    if _user_data_dir_cache is not None:
        return _user_data_dir_cache

    env_path = os.environ.get(DATA_DIR_ENV, "").strip()
    target = Path(env_path).expanduser() if env_path else _default_user_data_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception:
        target = _base_dir()
        try:
            target.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    _migrate_legacy_data_if_needed(target)
    _user_data_dir_cache = target
    return target


def _append_startup_log(text: str) -> None:
    try:
        log_path = _user_data_dir() / "zeus_startup.log"
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {text}\n")
    except Exception:
        pass


def _update_debug(text: str) -> None:
    if os.environ.get("ZEUS_UPDATE_DEBUG", "0").strip() == "1":
        _append_startup_log("auto_update_debug: " + text)


def _read_json_file(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8-sig")
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def _resolve_optional_resource(name: str) -> Path | None:
    candidates = [
        _base_dir() / name,
        _base_dir() / "_internal" / name,
        _resource_dir() / name,
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _read_local_version() -> str:
    p = _resolve_optional_resource(VERSION_FILE)
    if not p:
        return "0.0.0"
    obj = _read_json_file(p)
    v = str(obj.get("version", "")).strip()
    return v if v else "0.0.0"


def _load_update_config() -> dict:
    defaults = {
        "enabled": True,
        "manifest_url": "",
        "channel": "stable",
        "check_timeout_sec": UPDATE_TIMEOUT_SEC,
    }
    p = _resolve_optional_resource(UPDATE_CONFIG_FILE)
    if not p:
        return defaults
    obj = _read_json_file(p)
    merged = dict(defaults)
    merged.update(obj)
    return merged


def _version_key(text: str) -> tuple[int, int, int, int]:
    nums = [int(x) for x in re.findall(r"\d+", text or "")]
    while len(nums) < 4:
        nums.append(0)
    return (nums[0], nums[1], nums[2], nums[3])


def _is_newer_version(remote: str, local: str) -> bool:
    return _version_key(remote) > _version_key(local)


def _to_positive_int(value: object, fallback: int) -> int:
    try:
        n = int(value)  # type: ignore[arg-type]
        if n > 0:
            return n
    except Exception:
        pass
    return fallback


def _normalize_url_list(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        u = str(raw or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _github_release_url_variants(url: str, version: str) -> list[str]:
    """
    Build tolerant candidate URLs for GitHub release assets.

    This handles common operator mistakes:
    - tag style mismatch (v1.0.7 vs zeus_update_1.0.7)
    - filename style mismatch (..._win64.zip vs ..._v1.0.7_win64.zip)
    """
    m = re.match(
        r"^(https://github\.com/[^/]+/[^/]+/releases/download/)([^/]+)/([^/?#]+)(.*)$",
        url.strip(),
    )
    if not m:
        return []
    prefix, tag, filename, suffix = m.groups()
    safe_version = re.sub(r"[^A-Za-z0-9._-]", "_", version or "").strip("._-")

    tag_candidates = [tag]
    if safe_version:
        tag_candidates.extend(
            [
                f"v{safe_version}",
                f"zeus_update_{safe_version}",
                safe_version,
            ]
        )

    file_candidates = [filename]
    m_base = re.match(r"^(.*)_win64\.zip$", filename)
    if m_base and safe_version:
        stem = m_base.group(1)
        file_candidates.append(f"{stem}_v{safe_version}_win64.zip")
    m_ver = re.match(r"^(.*)_v[0-9A-Za-z._-]+_win64\.zip$", filename)
    if m_ver:
        stem = m_ver.group(1)
        file_candidates.append(f"{stem}_win64.zip")
        if safe_version:
            file_candidates.append(f"{stem}_v{safe_version}_win64.zip")

    combos: list[str] = []
    for tg in tag_candidates:
        for fn in file_candidates:
            combos.append(f"{prefix}{tg}/{fn}{suffix}")
    return _normalize_url_list(combos)


def _collect_update_zip_urls(manifest: dict, remote_version: str) -> list[str]:
    base: list[str] = []
    raw_zip_urls = manifest.get("zip_urls")
    if isinstance(raw_zip_urls, list):
        for item in raw_zip_urls:
            if isinstance(item, str):
                base.append(item)
    raw_zip_url = manifest.get("zip_url")
    if isinstance(raw_zip_url, str):
        base.append(raw_zip_url)

    urls = _normalize_url_list(base)
    expanded: list[str] = []
    for u in urls:
        expanded.append(u)
        expanded.extend(_github_release_url_variants(u, remote_version))
    return _normalize_url_list(expanded)


def _fetch_update_manifest(url: str, timeout_sec: int) -> dict:
    req = urllib_request.Request(url, headers={"User-Agent": "ZeusIntegAutoUpdater/1.0"})
    with urllib_request.urlopen(req, timeout=timeout_sec) as res:  # nosec B310
        body = res.read().decode("utf-8-sig", errors="replace")
    obj = json.loads(body)
    if not isinstance(obj, dict):
        raise ValueError("update manifest is not an object")
    return obj


def _download_update_zip(url: str, version: str, timeout_sec: int) -> Path:
    safe_version = re.sub(r"[^A-Za-z0-9._-]", "_", version or "unknown")
    dst = Path(tempfile.gettempdir()) / f"{UPDATE_TMP_PREFIX}{safe_version}_{int(time.time())}.zip"
    req = urllib_request.Request(url, headers={"User-Agent": "ZeusIntegAutoUpdater/1.0"})
    with urllib_request.urlopen(req, timeout=timeout_sec) as res, dst.open("wb") as f:  # nosec B310
        while True:
            chunk = res.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)
    return dst


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _write_update_script() -> Path:
    script = """param(
    [string]$ZipPath,
    [string]$AppDir,
    [string]$ExeName,
    [int]$ParentPid,
    [string]$Version
)
$ErrorActionPreference = "Stop"
$log = Join-Path $AppDir "zeus_updater.log"
function WriteLog([string]$msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $log -Value ("[" + $ts + "] " + $msg)
}
try {
    WriteLog ("start update to " + $Version)
    Start-Sleep -Milliseconds 700
    if ($ParentPid -gt 0) {
        try { Wait-Process -Id $ParentPid -Timeout 180 -ErrorAction SilentlyContinue } catch {}
    }
    $stage = Join-Path ([System.IO.Path]::GetTempPath()) ("zeus_stage_" + [guid]::NewGuid().ToString("N"))
    $extract = Join-Path $stage "extract"
    New-Item -ItemType Directory -Force -Path $extract | Out-Null
    Expand-Archive -Path $ZipPath -DestinationPath $extract -Force
    $dirs = Get-ChildItem -Path $extract -Directory
    if ($dirs.Count -eq 1) { $payload = $dirs[0].FullName } else { $payload = $extract }
    Copy-Item -Path (Join-Path $payload '*') -Destination $AppDir -Recurse -Force
    WriteLog "copied new files"
    Remove-Item -Path $ZipPath -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $stage -Recurse -Force -ErrorAction SilentlyContinue
    $exePath = Join-Path $AppDir $ExeName
    if (Test-Path $exePath) {
        Start-Process -FilePath $exePath -WorkingDirectory $AppDir | Out-Null
        WriteLog ("restart " + $exePath)
    } else {
        WriteLog ("exe missing after update: " + $exePath)
    }
} catch {
    WriteLog ("update failed: " + $_.Exception.Message)
}
"""
    dst = Path(tempfile.gettempdir()) / f"zeus_apply_update_{int(time.time())}.ps1"
    dst.write_text(script, encoding="utf-8")
    return dst


def _schedule_update_installer(zip_path: Path, remote_version: str) -> None:
    exe_name = Path(sys.executable).name if getattr(sys, "frozen", False) else "ZeusIntegProtectedV1.exe"
    script_path = _write_update_script()
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-ZipPath",
        str(zip_path),
        "-AppDir",
        str(_base_dir()),
        "-ExeName",
        exe_name,
        "-ParentPid",
        str(os.getpid()),
        "-Version",
        remote_version,
    ]
    flags = 0
    if os.name == "nt":
        flags |= getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(cmd, close_fds=True, creationflags=flags)  # noqa: S603


def _maybe_auto_update() -> bool:
    _update_debug("check start")
    if not getattr(sys, "frozen", False):
        _update_debug("skip: not frozen")
        return False

    if os.environ.get("ZEUS_SKIP_AUTO_UPDATE", "0").strip() == "1":
        _update_debug("skip: ZEUS_SKIP_AUTO_UPDATE=1")
        return False

    cfg = _load_update_config()
    if not bool(cfg.get("enabled", True)):
        _update_debug("skip: config disabled")
        return False

    manifest_url = str(cfg.get("manifest_url", "")).strip()
    if not manifest_url:
        _update_debug("skip: manifest_url empty")
        return False

    timeout_sec = _to_positive_int(cfg.get("check_timeout_sec", UPDATE_TIMEOUT_SEC), UPDATE_TIMEOUT_SEC)
    local_version = _read_local_version()
    _update_debug(f"local_version={local_version}")
    try:
        manifest = _fetch_update_manifest(manifest_url, timeout_sec)
    except Exception as e:
        _append_startup_log(f"auto_update_manifest_error: {e}")
        _update_debug("manifest fetch failed")
        return False

    remote_version = str(manifest.get("version", "")).strip()
    if not remote_version:
        _update_debug("skip: remote version missing")
        return False

    channel = str(cfg.get("channel", "stable")).strip().lower()
    manifest_channel = str(manifest.get("channel", channel)).strip().lower()
    if channel and manifest_channel and channel != manifest_channel:
        _update_debug(f"skip: channel mismatch cfg={channel} manifest={manifest_channel}")
        return False

    if not _is_newer_version(remote_version, local_version):
        _update_debug(f"skip: not newer remote={remote_version} local={local_version}")
        return False

    zip_urls = _collect_update_zip_urls(manifest, remote_version)
    if not zip_urls:
        _append_startup_log("auto_update_manifest_missing_zip_url")
        _update_debug("skip: zip_url missing")
        return False

    zip_path: Path | None = None
    downloaded_from = ""
    download_errors: list[str] = []
    for candidate in zip_urls:
        _update_debug(f"download try: {candidate}")
        try:
            zip_path = _download_update_zip(candidate, remote_version, timeout_sec)
            downloaded_from = candidate
            break
        except (OSError, urllib_error.URLError, urllib_error.HTTPError, TimeoutError, ValueError) as e:
            download_errors.append(f"{candidate} -> {e}")
            continue

    if zip_path is None:
        joined = " | ".join(download_errors[:3])
        if len(download_errors) > 3:
            joined += f" | ... (+{len(download_errors) - 3} more)"
        if not joined:
            joined = "unknown download error"
        _append_startup_log(f"auto_update_download_error: {joined}")
        _update_debug("download failed for all candidate URLs")
        return False
    _update_debug(f"download ok: {downloaded_from}")

    expected_sha = str(manifest.get("sha256", "")).strip().lower()
    if expected_sha:
        actual_sha = _sha256_file(zip_path).lower()
        if actual_sha != expected_sha:
            _append_startup_log(
                f"auto_update_hash_mismatch expected={expected_sha} actual={actual_sha} url={downloaded_from}"
            )
            try:
                zip_path.unlink(missing_ok=True)
            except Exception:
                pass
            _update_debug("skip: sha mismatch")
            return False

    try:
        _schedule_update_installer(zip_path, remote_version)
    except Exception as e:
        _append_startup_log(f"auto_update_schedule_error: {e}")
        _update_debug("schedule failed")
        return False

    _append_startup_log(f"auto_update_scheduled from={local_version} to={remote_version}")
    _update_debug("scheduled")
    return True


def _derive_runtime_key() -> bytes:
    seed = (APP_SECRET_A + "|" + APP_SECRET_B).encode("utf-8")
    digest = hashlib.sha256(seed).digest()
    return base64.urlsafe_b64encode(digest)


def _resolve_protected_blob_path() -> Path:
    candidates = [
        _resource_dir() / PROTECTED_ZEUS_BLOB,
        _base_dir() / PROTECTED_ZEUS_BLOB,
        _base_dir() / "_internal" / PROTECTED_ZEUS_BLOB,
    ]
    for p in candidates:
        if p.exists():
            return p
    joined = ", ".join(str(x) for x in candidates)
    raise FileNotFoundError(f"protected core blob missing. tried: {joined}")


def _load_protected_zeus_module() -> types.ModuleType:
    blob_path = _resolve_protected_blob_path()

    payload = json.loads(blob_path.read_text(encoding="utf-8"))
    token = base64.b64decode(payload.get("blob_b64", "").encode("ascii"))
    decrypted = Fernet(_derive_runtime_key()).decrypt(token)
    source_bytes = gzip.decompress(decrypted)
    source = source_bytes.decode("utf-8")

    module = types.ModuleType("zeus_integ2")
    module.__file__ = str(_user_data_dir() / "zeus_integ2.py")
    module.__package__ = ""
    module.__spec__ = None
    sys.modules["zeus_integ2"] = module
    code = compile(source, module.__file__, "exec")
    exec(code, module.__dict__)
    return module


def _is_port_ready(host: str, port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.25)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def _wait_server_ready(timeout_sec: float = EMBED_WAIT_SEC) -> bool:
    end = time.time() + timeout_sec
    while time.time() < end:
        if _is_port_ready(HOST, PORT):
            return True
        if _boot_done.is_set() and _boot_error:
            return False
        time.sleep(0.12)
    return _is_port_ready(HOST, PORT)


def _open_external_browser(url: str) -> bool:
    try:
        import webbrowser

        if webbrowser.open(url, new=0):
            return True
    except Exception:
        pass
    try:
        if os.name == "nt":
            os.startfile(url)  # type: ignore[attr-defined]
            return True
    except Exception:
        pass
    return False


def _launch_embedded_dashboard() -> bool:
    url = f"http://{HOST}:{PORT}"
    loading_html = (
        "<html><head><meta charset='utf-8'><style>"
        "body{margin:0;background:#0a1022;color:#dce7ff;font-family:Segoe UI,Arial,sans-serif;display:flex;"
        "align-items:center;justify-content:center;height:100vh}"
        ".box{padding:24px 28px;border:1px solid #22345f;border-radius:14px;background:#0d1630;max-width:520px}"
        ".t{font-size:20px;font-weight:700;margin-bottom:10px}"
        ".s{font-size:14px;color:#9fb3de;line-height:1.5}"
        "</style></head><body><div class='box'><div class='t'>ZEUS Quant Dashboard</div>"
        "<div class='s'>Server is starting. The dashboard will open automatically when ready.</div>"
        "</div></body></html>"
    )
    try:
        import webview  # type: ignore[import-not-found]
    except Exception as e:
        _append_startup_log(f"embedded_ui_import_error: {e}")
        return False

    try:
        win = webview.create_window(
            "ZEUS Quant Dashboard",
            html=loading_html,
            width=1480,
            height=930,
            min_size=(1100, 720),
            confirm_close=True,
            background_color="#0a1022",
        )

        def _attach_dashboard() -> None:
            if _wait_server_ready(timeout_sec=EMBED_WAIT_SEC):
                try:
                    win.load_url(url)
                except Exception as e:
                    _append_startup_log(f"embedded_ui_load_url_error: {e}")
            else:
                _append_startup_log("embedded_ui_timeout: server not ready")
                try:
                    win.load_html(
                        "<html><body style='font-family:Segoe UI;background:#0a1022;color:#dce7ff;'>"
                        "<div style='padding:24px'>Server startup is taking longer than expected.<br>"
                        "Please close and run Zeus again.</div></body></html>"
                    )
                except Exception:
                    pass

        webview.start(_attach_dashboard, debug=False, private_mode=False)
        return True
    except Exception as e:
        _append_startup_log(f"embedded_ui_runtime_error: {e}")
        return False


def _run_zeus() -> None:
    global _boot_error
    try:
        os.environ.setdefault(DATA_DIR_ENV, str(_user_data_dir()))
        zeus_integ2 = _load_protected_zeus_module()

        sys.argv = [sys.argv[0], "--server", "--live"]
        zeus_integ2.main()
    except Exception:
        _boot_error = traceback.format_exc()
        _append_startup_log(_boot_error)
        _boot_done.set()


def _license_reason_to_text(reason: str) -> str:
    mapping = {
        "public_key_missing": "Public key file is missing.",
        "license_missing": "License file is missing.",
        "license_parse_error": "License file is not valid JSON.",
        "license_format_error": "License file format is invalid.",
        "public_key_invalid": "Public key format is invalid.",
        "license_signature_decode_error": "License signature encoding is invalid.",
        "license_signature_invalid": "License signature verification failed.",
        "license_signature_error": "License signature check failed.",
        "license_app_mismatch": "License is for a different app.",
        "license_expiry_invalid": "License expiry date format is invalid.",
        "license_expired": "License has expired.",
        "license_machine_mismatch": "License is bound to a different machine.",
    }
    return mapping.get(reason, f"License validation failed: {reason}")


def _check_license_gate() -> bool:
    try:
        from zi_license import validate_local_license
    except Exception as e:
        msg = f"License module load failed: {e}"
        sys.__stdout__.write(msg + "\n")
        return False

    ok, reason, details = validate_local_license()
    if ok:
        return True

    fp = details.get("machine_fingerprint", "")
    lp = details.get("license_path", "license.dat")
    reason_txt = _license_reason_to_text(reason)
    full_msg = (
        f"{reason_txt}\n\n"
        f"Expected license file:\n{lp}\n\n"
        f"Machine fingerprint:\n{fp}\n\n"
        "Send this fingerprint to the issuer for license issuance."
    )
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("ZEUS License Required", full_msg)
        root.destroy()
    except Exception:
        pass
    sys.__stdout__.write("\n[license]\n" + full_msg + "\n")
    sys.__stdout__.flush()
    return False


def _configure_tk_runtime_paths() -> None:
    tcl_candidates = [
        _resource_dir() / "_tcl_data",
        _base_dir() / "_internal" / "_tcl_data",
        _base_dir() / "_tcl_data",
    ]
    tk_candidates = [
        _resource_dir() / "_tk_data",
        _base_dir() / "_internal" / "_tk_data",
        _base_dir() / "_tk_data",
    ]

    for p in tcl_candidates:
        if p.exists():
            os.environ["TCL_LIBRARY"] = str(p)
            break
    for p in tk_candidates:
        if p.exists():
            os.environ["TK_LIBRARY"] = str(p)
            break


def _show_splash() -> None:
    start_t = time.perf_counter()
    _configure_tk_runtime_paths()
    root = tk.Tk()
    root.title("ZEUS")
    root.geometry("520x300")
    root.configure(bg="#0a1022")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    # Center window
    root.update_idletasks()
    w, h = 520, 300
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")
    try:
        ico = Path(__file__).with_name("zeus_logo.ico")
        if ico.exists():
            root.iconbitmap(str(ico))
    except Exception:
        pass

    canvas = tk.Canvas(root, width=w, height=h, bg="#0a1022", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    canvas.create_rectangle(0, 0, w, h, fill="#0a1022", outline="")
    # Distinctive Zeus mark (hex core + trident lines + orbit node)
    logo_cx, logo_cy = w // 2, 78
    hex_r = 30
    hex_pts = []
    for i in range(6):
        a = math.radians(60 * i - 30)
        hex_pts.extend([logo_cx + hex_r * math.cos(a), logo_cy + hex_r * math.sin(a)])
    canvas.create_polygon(hex_pts, outline="#58b6ff", width=2, fill="")
    canvas.create_oval(logo_cx - 14, logo_cy - 14, logo_cx + 14, logo_cy + 14, fill="#0b1f47", outline="#2d6fd7", width=1)
    canvas.create_line(logo_cx, logo_cy - 18, logo_cx, logo_cy + 17, fill="#88d5ff", width=2)
    canvas.create_line(logo_cx - 12, logo_cy - 2, logo_cx, logo_cy - 18, fill="#88d5ff", width=2)
    canvas.create_line(logo_cx + 12, logo_cy - 2, logo_cx, logo_cy - 18, fill="#88d5ff", width=2)
    logo_orbit = canvas.create_oval(logo_cx + 30, logo_cy - 4, logo_cx + 38, logo_cy + 4, fill="#9ad1ff", outline="")

    canvas.create_text(
        w // 2,
        132,
        text="ZEUS INTEGRATED",
        fill="#dce7ff",
        font=("Segoe UI Semibold", 23),
    )
    canvas.create_text(
        w // 2,
        162,
        text="Quant Dashboard",
        fill="#8fa3d6",
        font=("Segoe UI", 10),
    )

    ring = canvas.create_oval(204, 182, 316, 294, outline="#1f2f60", width=6)
    arc = canvas.create_arc(
        204,
        182,
        316,
        294,
        start=0,
        extent=100,
        style="arc",
        outline="#55b3ff",
        width=6,
    )
    dot = canvas.create_oval(252, 230, 268, 246, fill="#9ad1ff", outline="")
    msg = canvas.create_text(
        w // 2,
        286,
        text="Initializing engine",
        fill="#9fb3de",
        font=("Segoe UI", 10),
    )

    state = {
        "arc_deg": 0.0,
        "orbit_deg": 0.0,
        "dots": 0,
        "last_frame_t": start_t,
        "next_dot_t": start_t + SPLASH_DOT_PERIOD_SEC,
        "next_probe_t": start_t,
        "server_ready": False,
    }

    def _tick() -> None:
        now_t = time.perf_counter()
        elapsed = now_t - start_t
        if now_t >= float(state["next_probe_t"]):
            state["server_ready"] = _is_port_ready(HOST, PORT)
            state["next_probe_t"] = now_t + SPLASH_READY_POLL_SEC
        server_ready = bool(state["server_ready"])

        # Always keep splash visible for a minimum duration.
        if server_ready and elapsed >= MIN_SPLASH_SEC:
            root.destroy()
            return

        if _boot_done.is_set() and _boot_error:
            if elapsed >= MIN_SPLASH_SEC:
                canvas.itemconfig(msg, text="Startup failed. Check console log.")
                root.after(1400, root.destroy)
                return

        if elapsed > BOOT_TIMEOUT_SEC:
            canvas.itemconfig(msg, text="Still starting... dashboard window will appear soon.")
            root.after(1200, root.destroy)
            return

        dt = now_t - float(state["last_frame_t"])
        if dt < 0.0:
            dt = 0.0
        if dt > 0.08:
            dt = 0.08
        state["last_frame_t"] = now_t

        state["arc_deg"] = (float(state["arc_deg"]) + SPLASH_ARC_DEG_PER_SEC * dt) % 360.0
        state["orbit_deg"] = (float(state["orbit_deg"]) + SPLASH_ORBIT_DEG_PER_SEC * dt) % 360.0

        if now_t >= float(state["next_dot_t"]):
            state["dots"] = (int(state["dots"]) + 1) % 4
            state["next_dot_t"] = now_t + SPLASH_DOT_PERIOD_SEC

        orbit_r = 34.0 + 1.4 * math.sin(now_t * 3.6)
        la = math.radians(float(state["orbit_deg"]))
        lx = logo_cx + orbit_r * math.cos(la)
        ly = logo_cy + orbit_r * math.sin(la)
        canvas.itemconfig(arc, start=float(state["arc_deg"]))
        canvas.coords(logo_orbit, lx - 4, ly - 4, lx + 4, ly + 4)
        if server_ready:
            canvas.itemconfig(msg, text="Preparing dashboard" + "." * int(state["dots"]))
        else:
            canvas.itemconfig(msg, text="Initializing engine" + "." * int(state["dots"]))
        canvas.itemconfig(ring, outline="#1f2f60")
        canvas.itemconfig(dot, fill="#9ad1ff")
        root.after(SPLASH_FRAME_MS, _tick)

    root.after(SPLASH_FRAME_MS, _tick)
    root.mainloop()


if __name__ == "__main__":
    if _maybe_auto_update():
        sys.exit(0)
    if REQUIRE_LICENSE and (not _check_license_gate()):
        sys.exit(3)

    embed_ui = os.environ.get(EMBED_UI_ENV, "1").strip() == "1"
    if embed_ui:
        os.environ[EMBED_UI_ENV] = "1"

    worker = threading.Thread(target=_run_zeus, name="zeus-main", daemon=False)
    worker.start()
    try:
        _show_splash()
    except Exception:
        _append_startup_log("splash_error\n" + traceback.format_exc())
        time.sleep(MIN_SPLASH_SEC)

    if embed_ui:
        if _launch_embedded_dashboard():
            os._exit(0)
        _append_startup_log("embedded_ui_fallback_to_external_browser")
        _open_external_browser(f"http://{HOST}:{PORT}")

    worker.join()
