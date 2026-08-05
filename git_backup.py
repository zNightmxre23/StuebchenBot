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

def run_git_command(command: list) -> str:
    result = subprocess.run(
        command,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()

def backup_database():
    if not DB_PATH.exists():
        logging.warning(f"⚠️ [BACKUP] Datenbank {DB_PATH.name} nicht gefunden.")
        return

    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.close()

        run_git_command(["git", "add", "voice_levels.db"])
        status = run_git_command(["git", "status", "--porcelain", "voice_levels.db"])

        if status:
            commit_msg = f"Auto-backup on shutdown: voice_levels.db ({time.strftime('%Y-%m-%d %H:%M:%S')})"
            run_git_command(["git", "commit", "-m", commit_msg])
            run_git_command(["git", "push", "origin", "feature/my-new-updates"])
            logging.info("📦 [GIT BACKUP] DB erfolgreich auf GitHub hochgeladen!")
        else:
            logging.info("💤 [GIT BACKUP] Keine Änderungen zum Sichern vorhanden.")

    except subprocess.CalledProcessError as e:
        logging.error(f"❌ [GIT FEHLER] Befehl '{' '.join(e.cmd)}' fehlgeschlagen:")
        logging.error(f"Output: {e.stderr}")
    except Exception as e:
        logging.error(f"⚠️ [FEHLER] Unerwarteter Fehler: {e}")

if __name__ == "__main__":
    backup_database()