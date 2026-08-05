import os
import sys
import time
import logging
import sqlite3
import subprocess
from pathlib import Path

# Dynamische Pfadermittlung: Nimmt exakt den Ordner, in dem das Skript ausgeführt/gespeichert wird
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "voice_levels.db"

log_dir = BASE_DIR / "logs"
os.makedirs(log_dir, exist_ok=True)
log_file_path = log_dir / "git_backup.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file_path, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

def show_progress(step: int, total: int, label: str):
    """Zeigt eine Ladeleiste im Terminal an."""
    percent = int((step / total) * 100)
    bar_length = 20
    filled = int(bar_length * step // total)
    bar = "█" * filled + "░" * (bar_length - filled)
    sys.stdout.write(f"\r⏳ [{bar}] {percent}% - {label}")
    sys.stdout.flush()
    time.sleep(0.2)

def run_git_command(command: list) -> str:
    """Führt einen Git-Befehl im aktuellen Projektverzeichnis aus."""
    result = subprocess.run(
        command,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()

def check_git_connection() -> bool:
    """Prüft die Verbindung zum GitHub Repository."""
    try:
        run_git_command(["git", "ls-remote", "origin"])
        return True
    except subprocess.CalledProcessError:
        return False

def flush_and_touch_db():
    """Schreibt offene SQLite-Transaktionen raus und aktualisiert den Dateizeitstempel."""
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("PRAGMA wal_checkpoint(FULL);")
            conn.commit()
            conn.close()
        except Exception as e:
            logging.warning(f"⚠️ Hinweis bei SQLite Flush: {e}")
        
        # Aktualisiert den Modifikationszeitstempel der Datei auf dem Dateisystem,
        # damit Git die Änderung in jedem Fall erkennt
        os.utime(DB_PATH, None)

def backup_database():
    print(f"\n--- 📦 Git-Backup Prozess Gestartet ({BASE_DIR.name}) ---")
    total_steps = 5

    # Schritt 1: GitHub Verbindung prüfen
    show_progress(1, total_steps, "Prüfe GitHub-Verbindung...")
    if not check_git_connection():
        print("\n❌ [FEHLER] Keine Verbindung zum GitHub-Repository möglich!")
        logging.error("❌ keine Verbindung zum GitHub-Repository möglich.")
        return

    # Schritt 2: DB prüfen & SQLite flashen
    show_progress(2, total_steps, "Prüfe 'voice_levels.db'...")
    if not DB_PATH.exists():
        print(f"\n⚠️ [FEHLER] 'voice_levels.db' wurde in {BASE_DIR} nicht gefunden!")
        logging.warning(f"⚠️ Datenbank 'voice_levels.db' nicht in {BASE_DIR} gefunden.")
        return

    flush_and_touch_db()

    try:
        # Schritt 3: Datei zum Staging hinzufügen (erzwingen)
        show_progress(3, total_steps, "Staging für 'voice_levels.db'...")
        run_git_command(["git", "add", "-f", "voice_levels.db"])

        # Schritt 4: Commit erzwingen (auch wenn keine Inhaltlichen Änderungen vorliegen)
        show_progress(4, total_steps, "Erstelle Commit...")
        commit_msg = f"Update voice_levels.db: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        
        try:
            run_git_command(["git", "commit", "-m", commit_msg])
        except subprocess.CalledProcessError:
            # Falls Git meint, es gebe nix neues, erzwingen wir den Commit
            run_git_command(["git", "commit", "--allow-empty", "-m", commit_msg])

        # Schritt 5: Auf GitHub pushen
        show_progress(5, total_steps, "Pushe auf GitHub...")
        run_git_command(["git", "push", "origin", "feature/my-new-updates"])

        print("\n✅ [STATUS] 'voice_levels.db' erfolgreich auf GitHub aktualisiert! 🚀")
        logging.info("🚀 'voice_levels.db' erfolgreich auf GitHub gepusht!")

    except subprocess.CalledProcessError as e:
        print(f"\n❌ [FEHLER] Git-Befehl fehlgeschlagen.")
        logging.error(f"❌ Git-Befehl '{' '.join(e.cmd)}' fehlgeschlagen: {e.stderr}")
    except Exception as e:
        print(f"\n⚠️ [FEHLER] Unerwarteter Fehler.")
        logging.error(f"⚠️ Fehler: {e}")

if __name__ == "__main__":
    backup_database()