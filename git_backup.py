import os
import sys
import time
import shutil
import logging
import sqlite3
import subprocess
from pathlib import Path

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

def prepare_db_for_commit():
    """Erzwingt das Rausschreiben der SQLite-Datenbank und erzeugt eine frische Datei."""
    if not DB_PATH.exists():
        return False

    try:
        # SQLite Anweisungen zum Leeren des Write-Ahead-Logs
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA wal_checkpoint(FULL);")
        conn.commit()
        conn.close()

        # Erstelle eine physische Kopie und überschreibe die Datei, um Git-Änderung zu erzwingen
        temp_path = BASE_DIR / "voice_levels_temp.db"
        shutil.copy2(DB_PATH, temp_path)
        shutil.move(temp_path, DB_PATH)
        return True
    except Exception as e:
        logging.warning(f"⚠️ Hinweis beim DB-Flush: {e}")
        return True

def backup_database():
    print(f"\n--- 📦 Git-Backup Prozess Gestartet ---")
    total_steps = 5

    # Schritt 1: Verbindung prüfen
    show_progress(1, total_steps, "Prüfe GitHub-Verbindung...")
    if not check_git_connection():
        print("\n❌ [FEHLER] Keine Verbindung zum GitHub-Repository möglich!")
        logging.error("❌ keine Verbindung zum GitHub-Repository möglich.")
        return

    # Schritt 2: DB aufbereiten
    show_progress(2, total_steps, "Bereite Datenbank für Push vor...")
    if not prepare_db_for_commit():
        print(f"\n⚠️ [FEHLER] 'voice_levels.db' nicht in {BASE_DIR} gefunden!")
        logging.warning(f"⚠️ Datenbank nicht in {BASE_DIR} gefunden.")
        return

    try:
        # Schritt 3: Staging erzwingen (-f ignoriert evtl. Einschränkungen in .gitignore)
        show_progress(3, total_steps, "Füge 'voice_levels.db' zum Staging hinzu...")
        run_git_command(["git", "add", "-f", "voice_levels.db"])

        # Schritt 4: Commit erstellen
        show_progress(4, total_steps, "Erstelle Backup-Commit...")
        commit_msg = f"Backup DB Update: voice_levels.db ({time.strftime('%Y-%m-%d %H:%M:%S')})"
        
        # Versuche normalen Commit
        try:
            run_git_command(["git", "commit", "-m", commit_msg])
        except subprocess.CalledProcessError:
            # Falls sich absolut kein Byte geändert hat
            run_git_command(["git", "commit", "--allow-empty", "-m", commit_msg])

        # Schritt 5: Auf GitHub pushen
        show_progress(5, total_steps, "Pushe Datei auf GitHub...")
        run_git_command(["git", "push", "origin", "feature/my-new-updates"])

        print("\n✅ [STATUS] 'voice_levels.db' wurde erfolgreich hochgeladen! 🚀")
        logging.info("🚀 'voice_levels.db' erfolgreich auf GitHub gepusht!")

    except subprocess.CalledProcessError as e:
        print(f"\n❌ [FEHLER] Git-Befehl fehlgeschlagen.")
        logging.error(f"❌ Git-Befehl '{' '.join(e.cmd)}' fehlgeschlagen: {e.stderr}")
    except Exception as e:
        print(f"\n⚠️ [FEHLER] Unerwarteter Fehler.")
        logging.error(f"⚠️ Fehler: {e}")

if __name__ == "__main__":
    backup_database()