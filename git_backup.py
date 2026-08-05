import os
import sys
import time
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
    time.sleep(0.3)

def run_git_command(command: list) -> str:
    """Führt einen Git-Befehl im Projektverzeichnis aus."""
    result = subprocess.run(
        command,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()

def check_git_connection() -> bool:
    """Prüft die Verbindung zu GitHub."""
    try:
        run_git_command(["git", "ls-remote", "origin"])
        return True
    except subprocess.CalledProcessError:
        return False

def backup_database():
    print("\n--- 📦 Git-Backup Prozess Gestartet ---")
    total_steps = 5

    # Schritt 1: Verbindung prüfen
    show_progress(1, total_steps, "Prüfe GitHub-Verbindung...")
    if not check_git_connection():
        print("\n❌ [FEHLER] Keine Verbindung zum GitHub-Repository möglich!")
        logging.error("❌ Keine Verbindung zum GitHub-Repository möglich.")
        return

    # Schritt 2: DB-Existenz prüfen
    show_progress(2, total_steps, "Prüfe Datenbank-Datei...")
    if not DB_PATH.exists():
        print(f"\n⚠️ [FEHLER] Datenbank '{DB_PATH.name}' nicht vorhanden.")
        logging.warning(f"⚠️ Datenbank {DB_PATH.name} existiert nicht.")
        return

    try:
        # DB Verbindung kurz entlasten
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.close()

        # Schritt 3: Git Add
        show_progress(3, total_steps, "Füge 'voice_levels.db' zu Staging hinzu...")
        run_git_command(["git", "add", "voice_levels.db"])
        
        # Schritt 4: Commit erzwingen (auch ohne Dateiänderung via --allow-empty)
        show_progress(4, total_steps, "Erstelle Backup-Commit...")
        commit_msg = f"Forced Backup: voice_levels.db ({time.strftime('%Y-%m-%d %H:%M:%S')})"
        run_git_command(["git", "commit", "--allow-empty", "-m", commit_msg])

        # Schritt 5: Push erzwingen
        show_progress(5, total_steps, "Lade auf GitHub hoch...")
        run_git_command(["git", "push", "origin", "feature/my-new-updates"])

        print("\n✅ [STATUS] Backup-Commit erfolgreich auf GitHub erzeugt & hochgeladen! 🚀")
        logging.info("🚀 Backup-Commit für voice_levels.db erfolgreich auf GitHub hochgeladen!")

    except subprocess.CalledProcessError as e:
        print(f"\n❌ [FEHLER] Git-Prozess fehlgeschlagen.")
        logging.error(f"❌ Git-Befehl '{' '.join(e.cmd)}' fehlgeschlagen: {e.stderr}")
    except Exception as e:
        print(f"\n⚠️ [FEHLER] Unerwarteter Fehler aufgetreten.")
        logging.error(f"⚠️ Unerwarteter Fehler: {e}")

if __name__ == "__main__":
    backup_database()