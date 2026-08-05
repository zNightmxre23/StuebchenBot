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

def flush_sqlite_db():
    """Erzwingt das Schreiben aller offenen SQLite-Puffer auf die Festplatte."""
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            # Schreibt den WAL-Log in die Hauptdatenbank
            conn.execute("PRAGMA wal_checkpoint(FULL);")
            conn.commit()
            conn.close()
            # Aktualisiert den Zeitstempel der Datei auf dem Dateisystem
            os.utime(DB_PATH, None)
        except Exception as e:
            logging.warning(f"⚠️ SQLite Flush Hinweis: {e}")

def backup_database():
    print("\n--- 📦 Git-Backup Prozess Gestartet ---")
    total_steps = 5

    # Schritt 1: Verbindung prüfen
    show_progress(1, total_steps, "Prüfe GitHub-Verbindung...")
    if not check_git_connection():
        print("\n❌ [FEHLER] Keine Verbindung zum GitHub-Repository möglich!")
        logging.error("❌ Keine Verbindung zum GitHub-Repository möglich.")
        return

    # Schritt 2: DB-Existenz & Flush
    show_progress(2, total_steps, "Sichere SQLite-Datenbank auf Festplatte...")
    if not DB_PATH.exists():
        print(f"\n⚠️ [FEHLER] Datenbank '{DB_PATH.name}' nicht vorhanden.")
        logging.warning(f"⚠️ Datenbank {DB_PATH.name} existiert nicht.")
        return

    flush_sqlite_db()

    try:
        # Schritt 3: Git Add erzwingen
        show_progress(3, total_steps, "Füge 'voice_levels.db' zu Staging hinzu...")
        run_git_command(["git", "add", "-f", "voice_levels.db"])
        
        # Schritt 4: Commit erstellen
        show_progress(4, total_steps, "Erstelle Backup-Commit...")
        commit_msg = f"DB Backup: voice_levels.db ({time.strftime('%Y-%m-%d %H:%M:%S')})"
        
        # Versuche normalen Commit, sonst mit --allow-empty
        try:
            run_git_command(["git", "commit", "-m", commit_msg])
        except subprocess.CalledProcessError:
            run_git_command(["git", "commit", "--allow-empty", "-m", commit_msg])

        # Schritt 5: Push ausführen
        show_progress(5, total_steps, "Lade auf GitHub hoch...")
        run_git_command(["git", "push", "origin", "feature/my-new-updates"])

        print("\n✅ [STATUS] voice_levels.db wurde erfolgreich auf GitHub gepusht! 🚀")
        logging.info("🚀 voice_levels.db erfolgreich auf GitHub gepusht!")

    except subprocess.CalledProcessError as e:
        print(f"\n❌ [FEHLER] Git-Prozess fehlgeschlagen.")
        logging.error(f"❌ Git-Befehl '{' '.join(e.cmd)}' fehlgeschlagen: {e.stderr}")
    except Exception as e:
        print(f"\n⚠️ [FEHLER] Unerwarteter Fehler aufgetreten.")
        logging.error(f"⚠️ Unerwarteter Fehler: {e}")

if __name__ == "__main__":
    backup_database()