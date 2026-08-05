import os
import sys
import time
import logging
import sqlite3
import subprocess
from pathlib import Path

# Ordnerpfade festlegen
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "voice_levels.db"

# Logging konfigurieren
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

def run_git_command(command: list) -> str:
    """Führt einen Git-Befehl im BASE_DIR aus und gibt das Ergebnis zurück."""
    result = subprocess.run(
        command,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()

def backup_database():
    """Führt den Push-Prozess der voice_levels.db zu Git durch."""
    if not DB_PATH.exists():
        logging.warning(f"⚠️ [BACKUP] Datenbank-Datei {DB_PATH.name} existiert noch nicht.")
        return

    try:
        # SQLite Schalter nutzen, um ausstehende Schreibvorgänge sauber im Read-Only Modus abzuschließen
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.close()

        # 1. Datei zum Git Staging hinzufügen
        run_git_command(["git", "add", "voice_levels.db"])

        # 2. Prüfen, ob sich die DB seit dem letzten Commit verändert hat
        status = run_git_command(["git", "status", "--porcelain", "voice_levels.db"])

        if status:
            # 3. Commit erstellen
            commit_msg = f"Auto-backup: voice_levels.db ({time.strftime('%Y-%m-%d %H:%M:%S')})"
            run_git_command(["git", "commit", "-m", commit_msg])

            # 4. Push zum Remote Repository
            run_git_command(["git", "push"])
            logging.info("📦 [GIT BACKUP] DB erfolgreich auf Git hochgeladen!")
        else:
            logging.info("💤 [GIT BACKUP] Keine Änderungen in der DB vorhanden.")

    except subprocess.CalledProcessError as e:
        logging.error(f"❌ [GIT FEHLER] Befehl '{' '.join(e.cmd)}' fehlgeschlagen:")
        logging.error(f"Output: {e.stderr}")
    except Exception as e:
        logging.error(f"⚠️ [FEHLER] Unerwarteter Fehler beim Backup: {e}")

def main():
    logging.info("🚀 [GIT BACKUP] Backup-Skript gestartet (Intervall: 5 Minuten).")
    
    # Endlosschleife mit 5-Minuten-Pause (300 Sekunden)
    while True:
        backup_database()
        time.sleep(300)

if __name__ == "__main__":
    main()