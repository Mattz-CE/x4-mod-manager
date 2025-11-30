"""
X4 Mod Manager - FastAPI Application
Manages mods via symlinks to X4 Foundations extensions folder
"""

import os
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="X4 Mod Manager", version="1.0.0")

# Paths
BASE_DIR = Path(__file__).parent.parent
MODS_DIR = BASE_DIR / "mods"
DEFAULT_EXTENSIONS_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\X4 Foundations\extensions")

# Config file to persist settings
CONFIG_FILE = Path(__file__).parent / "config.json"

# Templates
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def load_config() -> dict:
    """Load configuration from file"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"extensions_dir": str(DEFAULT_EXTENSIONS_DIR)}


def save_config(config: dict):
    """Save configuration to file"""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_extensions_dir() -> Path:
    """Get the configured extensions directory"""
    config = load_config()
    return Path(config.get("extensions_dir", str(DEFAULT_EXTENSIONS_DIR)))


@dataclass
class ModInfo:
    """Mod information extracted from content.xml"""
    id: str
    name: str
    author: str
    version: str
    description: str
    date: str
    enabled: bool
    folder_name: str
    source_path: str
    is_managed: bool  # True if from our mods folder
    is_installed: bool  # True if symlinked/present in extensions
    is_symlink: bool  # True if it's a symlink


def parse_content_xml(content_xml_path: Path) -> Optional[dict]:
    """Parse a content.xml file and extract mod info"""
    try:
        tree = ET.parse(content_xml_path)
        root = tree.getroot()
        return {
            "id": root.get("id", "unknown"),
            "name": root.get("name", "Unknown Mod"),
            "author": root.get("author", "Unknown"),
            "version": root.get("version", "0"),
            "description": root.get("description", ""),
            "date": root.get("date", ""),
            "enabled": root.get("enabled", "1") == "1",
        }
    except Exception as e:
        print(f"Error parsing {content_xml_path}: {e}")
        return None


def get_available_mods() -> list[ModInfo]:
    """Get all mods from the mods folder"""
    mods = []
    if not MODS_DIR.exists():
        return mods
    
    extensions_dir = get_extensions_dir()
    
    for folder in MODS_DIR.iterdir():
        if folder.is_dir():
            content_xml = folder / "content.xml"
            if content_xml.exists():
                info = parse_content_xml(content_xml)
                if info:
                    # Check if installed (symlinked to extensions)
                    ext_path = extensions_dir / folder.name
                    is_installed = ext_path.exists()
                    is_symlink = ext_path.is_symlink() if is_installed else False
                    
                    mods.append(ModInfo(
                        id=info["id"],
                        name=info["name"],
                        author=info["author"],
                        version=info["version"],
                        description=info["description"],
                        date=info["date"],
                        enabled=info["enabled"],
                        folder_name=folder.name,
                        source_path=str(folder),
                        is_managed=True,
                        is_installed=is_installed,
                        is_symlink=is_symlink,
                    ))
    return mods


def get_installed_mods() -> list[ModInfo]:
    """Get all mods from the extensions folder"""
    mods = []
    extensions_dir = get_extensions_dir()
    
    if not extensions_dir.exists():
        return mods
    
    managed_folders = set()
    if MODS_DIR.exists():
        managed_folders = {f.name for f in MODS_DIR.iterdir() if f.is_dir()}
    
    for folder in extensions_dir.iterdir():
        if folder.is_dir():
            content_xml = folder / "content.xml"
            is_symlink = folder.is_symlink()
            
            # Skip if it's a symlink pointing to our mods folder (already counted)
            if is_symlink:
                try:
                    target = folder.resolve()
                    if target.parent == MODS_DIR:
                        continue
                except:
                    pass
            
            # Skip if folder name matches a managed mod (avoid duplicates)
            if folder.name in managed_folders:
                continue
            
            if content_xml.exists():
                info = parse_content_xml(content_xml)
                if info:
                    mods.append(ModInfo(
                        id=info["id"],
                        name=info["name"],
                        author=info["author"],
                        version=info["version"],
                        description=info["description"],
                        date=info["date"],
                        enabled=info["enabled"],
                        folder_name=folder.name,
                        source_path=str(folder),
                        is_managed=False,
                        is_installed=True,
                        is_symlink=is_symlink,
                    ))
    return mods


# ============ API Routes ============

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main page"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "extensions_dir": str(get_extensions_dir()),
        "mods_dir": str(MODS_DIR),
    })


@app.get("/api/mods")
async def list_mods():
    """Get all mods (both managed and installed)"""
    available = get_available_mods()
    installed = get_installed_mods()
    
    return {
        "managed": [asdict(m) for m in available],
        "external": [asdict(m) for m in installed],
        "extensions_dir": str(get_extensions_dir()),
        "mods_dir": str(MODS_DIR),
    }


@app.post("/api/mods/{folder_name}/install")
async def install_mod(folder_name: str):
    """Create symlink from mods folder to extensions folder"""
    mod_path = MODS_DIR / folder_name
    if not mod_path.exists():
        raise HTTPException(404, f"Mod folder '{folder_name}' not found")
    
    extensions_dir = get_extensions_dir()
    if not extensions_dir.exists():
        raise HTTPException(400, f"Extensions directory does not exist: {extensions_dir}")
    
    ext_path = extensions_dir / folder_name
    
    if ext_path.exists():
        if ext_path.is_symlink():
            return {"status": "already_installed", "message": "Mod is already installed"}
        else:
            raise HTTPException(400, "A non-symlink folder with this name already exists in extensions")
    
    try:
        # Create symlink (requires admin on Windows for directory symlinks)
        os.symlink(mod_path, ext_path, target_is_directory=True)
        return {"status": "success", "message": f"Installed {folder_name}"}
    except OSError as e:
        if "privilege" in str(e).lower() or "1314" in str(e):
            raise HTTPException(403, "Administrator privileges required to create symlinks on Windows. Run as admin or enable Developer Mode.")
        raise HTTPException(500, f"Failed to create symlink: {e}")


@app.post("/api/mods/{folder_name}/uninstall")
async def uninstall_mod(folder_name: str):
    """Remove symlink from extensions folder"""
    extensions_dir = get_extensions_dir()
    ext_path = extensions_dir / folder_name
    
    if not ext_path.exists():
        return {"status": "not_installed", "message": "Mod is not installed"}
    
    if not ext_path.is_symlink():
        raise HTTPException(400, "Cannot uninstall: this is not a managed symlink. Remove manually if needed.")
    
    try:
        os.unlink(ext_path)
        return {"status": "success", "message": f"Uninstalled {folder_name}"}
    except OSError as e:
        raise HTTPException(500, f"Failed to remove symlink: {e}")


@app.delete("/api/mods/{folder_name}")
async def delete_mod(folder_name: str):
    """Delete a mod from the mods folder (and uninstall if installed)"""
    import shutil
    
    mod_path = MODS_DIR / folder_name
    if not mod_path.exists():
        raise HTTPException(404, f"Mod folder '{folder_name}' not found")
    
    # First uninstall if installed
    extensions_dir = get_extensions_dir()
    ext_path = extensions_dir / folder_name
    if ext_path.exists() and ext_path.is_symlink():
        os.unlink(ext_path)
    
    # Then delete the mod folder
    try:
        shutil.rmtree(mod_path)
        return {"status": "success", "message": f"Deleted {folder_name}"}
    except Exception as e:
        raise HTTPException(500, f"Failed to delete mod: {e}")


@app.post("/api/settings/extensions-dir")
async def set_extensions_dir(request: Request):
    """Update the extensions directory path"""
    data = await request.json()
    new_path = data.get("path", "").strip()
    
    if not new_path:
        raise HTTPException(400, "Path cannot be empty")
    
    path = Path(new_path)
    if not path.exists():
        raise HTTPException(400, f"Directory does not exist: {new_path}")
    
    config = load_config()
    config["extensions_dir"] = new_path
    save_config(config)
    
    return {"status": "success", "path": new_path}


@app.get("/api/settings")
async def get_settings():
    """Get current settings"""
    return {
        "extensions_dir": str(get_extensions_dir()),
        "mods_dir": str(MODS_DIR),
        "default_extensions_dir": str(DEFAULT_EXTENSIONS_DIR),
        "is_admin": check_admin_privileges(),
        "can_symlink": check_symlink_capability(),
    }


def check_admin_privileges() -> bool:
    """Check if running with administrator privileges"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        # On non-Windows, check if root
        return os.getuid() == 0 if hasattr(os, 'getuid') else False


def check_symlink_capability() -> bool:
    """Check if we can create symlinks (admin or developer mode)"""
    import tempfile
    test_dir = Path(tempfile.gettempdir())
    test_link = test_dir / f"_symlink_test_{os.getpid()}"
    test_target = test_dir / f"_symlink_target_{os.getpid()}"
    
    try:
        test_target.mkdir(exist_ok=True)
        if test_link.exists():
            os.unlink(test_link)
        os.symlink(test_target, test_link, target_is_directory=True)
        os.unlink(test_link)
        test_target.rmdir()
        return True
    except OSError:
        if test_target.exists():
            test_target.rmdir()
        return False


def run():
    """Entry point for uv run"""
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9480)


if __name__ == "__main__":
    run()

