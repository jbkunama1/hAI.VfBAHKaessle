
# hAI.VfBAHKaessle – VfB Grötzingen AH Bierkässle


<p align="center">
  <a href="https://github.com/DEIN-USER/hAI.VfBAHKaessle"><img src="https://img.shields.io/github/stars/DEIN-USER/hAI.VfBAHKaessle?style=flat-square" alt="GitHub stars"></a>
  <a href="https://github.com/DEIN-USER/hAI.VfBAHKaessle/actions"><img src="https://img.shields.io/github/actions/workflow/status/DEIN-USER/hAI.VfBAHKaessle/trufflehog.yml?style=flat-square&label=trufflehog" alt="TruffleHog scan"></a>
  <a href="https://github.com/DEIN-USER/hAI.VfBAHKaessle/blob/main/LICENSE"><img src="https://img.shields.io/github/license/DEIN-USER/hAI.VfBAHKaessle?style=flat-square" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/docker-ready-brightgreen?style=flat-square" alt="Docker ready">
</p>

Flask-Webapp mit SQLite-Backend für das AH-Bierkässle des VfB Grötzingen, inklusive Telegram-Bot
und einer kleinen GitHub-Pages-Startseite (`index.html`).

Lizenz: MIT (siehe `LICENSE`).

## Architektur

- **Web-App (Flask)**
  - Benutzerverwaltung (Registrierung, Login/Logout, Passwort-Hashing mit Werkzeug)
  - Biereinträge pro Datum über ein responsives Bootstrap-UI
  - Monatsübersicht pro Spieler (Biere & Euro) plus Gesamtsumme
  - Läuft standardmäßig auf Port **1904**
- **SQLite-Datenbank**
  - Datei: `instance/bierkaessle.sqlite3`
  - Tabellen:
    - `users` (inkl. `telegram_id` zur Verknüpfung mit Telegram)
    - `beers` (Einträge: User, Datum, Anzahl, Zeitstempel)
- **Telegram-Bot** (`telegram_bot.py`)
  - Greift auf dieselbe SQLite-Datenbank zu
  - Kommandos für Biereintrag und Monatsstatus
- **Docker-/Portainer-Stack**
  - Ein Container für Web-App, ein Container für den Bot
  - Gemeinsames Volume für die Datenbank
- **GitHub Pages**
  - Statische Landing-Page `index.html` als Einstieg für das Projekt (Beschreibung, Links)

## GitHub / GitLab Nutzung

1. Repo klonen:
   ```bash
   git clone <DEIN-REPO-URL> hAI.VfBAHKaessle
   cd hAI.VfBAHKaessle
   ```
2. Optional GitHub Pages aktivieren:
   - In den Repo-Einstellungen `Pages`
   - Branch `main` (oder `master`) und Ordner `/root` wählen
   - Die Datei `index.html` dient als Startseite

## Features im Detail

- Registrierung und Login für Spieler
- Biereinträge pro Datum (z. B. immer mittwochs nach dem Training)
- Preis pro Bier konfigurierbar über `BEER_PRICE` (Standard: 1.50 €)
- Monatsübersicht pro Spieler sowie Gesamtübersicht
- Mobil-taugliche UI (Bootstrap 5, dunkles Theme)
- Telegram-Bot zur schnellen Erfassung direkt aus Telegram

## Lokale Installation (ohne Docker)

Voraussetzungen: Python 3.10+

```bash
git clone <DEIN-REPO-URL> hAI.VfBAHKaessle
cd hAI.VfBAHKaessle

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Web-App starten

```bash
export SECRET_KEY="change-me"      # in Produktion durch sicheren Key ersetzen
export BEER_PRICE="1.50"          # Preis pro Bier in Euro
export PORT="1904"                # Port für die Web-App
python app.py
```

Danach im Browser: <http://localhost:1904>

### Telegram-Bot starten

1. Bei `@BotFather` einen Bot anlegen und `TELEGRAM_BOT_TOKEN` notieren.
2. Im Projektordner:

   ```bash
   export TELEGRAM_BOT_TOKEN="DEIN_TELEGRAM_BOT_TOKEN"
   export BEER_PRICE="1.50"
   python telegram_bot.py
   ```

Die Web-App und der Bot verwenden beide die SQLite-Datenbank im Ordner `instance/`.

## Telegram-Flow Schritt für Schritt

**Voraussetzung:** Die Web-App läuft bereits, Spieler haben einen Web-Account (Benutzername).

1. **Web-Account anlegen**
   - Im Browser `http://<host>:1904` öffnen
   - Benutzer registrieren (Benutzername + Passwort)
2. **Telegram-Bot starten**
   - Im Telegram-Client den Bot (z. B. `@dein_ah_bierkaessle_bot`) öffnen
   - `/start` eingeben
3. **Telegram mit Web-Account verknüpfen**
   - Befehl:
     ```
     /link deinusername
     ```
   - Der Bot schreibt die `telegram_id` in die `users`-Tabelle
4. **Biere melden**
   - Beispielbefehle:
     - `/bier` → bucht 1 Bier für **heute**
     - `/bier 3` → bucht 3 Biere für **heute**
   - Der Bot legt Einträge in der Tabelle `beers` an (Datum = heutiges Datum)
5. **Status abrufen**
   - Befehl:
     ```
     /status
     ```
   - Antwort z. B.: `Dein Stand für 2026-07: 8 Bier(e) = 12.00 €.`

Dieser Flow ist bewusst einfach gehalten und für eine kleine AH-Gruppe ausgelegt.

## Docker / Portainer

### Image bauen

```bash
docker build -t haivfbahkaessle:latest .
```

### Stack mit docker-compose

```bash
docker compose up -d
# oder: docker-compose up -d
```

`docker-compose.yml` definiert zwei Services:

```yaml
services:
  bierkaessle_web:
    image: haivfbahkaessle:latest
    # build: .
    container_name: bierkaessle_web
    ports:
      - "1904:1904"
    environment:
      - SECRET_KEY=change-me
      - BEER_PRICE=1.50
    volumes:
      - bierkaessle_data:/app/instance
    restart: unless-stopped

  bierkaessle_bot:
    image: haivfbahkaessle:latest
    # build: .
    container_name: bierkaessle_bot
    environment:
      - TELEGRAM_BOT_TOKEN=DEIN_TELEGRAM_BOT_TOKEN
      - BEER_PRICE=1.50
    volumes:
      - bierkaessle_data:/app/instance
    command: ["python", "telegram_bot.py"]
    restart: unless-stopped
    depends_on:
      - bierkaessle_web

volumes:
  bierkaessle_data:
```

- Web-App: <http://localhost:1904>
- Datenbank: Volume `bierkaessle_data` (enthält `instance/bierkaessle.sqlite3`)

### Einsatz in Portainer

1. In Portainer unter **Stacks → Add stack** gehen.
2. Inhalt der `docker-compose.yml` einfügen.
3. Im Service `bierkaessle_bot` die Umgebungvariable `TELEGRAM_BOT_TOKEN` auf deinen echten Bot-Token setzen.
4. Stack deployen.

## Sicherheit / Betrieb

- In Produktion immer einen starken `SECRET_KEY` verwenden.
- Zugriff auf die Web-App über einen Reverse Proxy (nginx, Traefik, Cloudflare Tunnel) absichern.
- Volume `bierkaessle_data` regelmäßig sichern (Backups).
- Telegram-Bot-Token niemals ins Repo commiten, sondern nur als ENV/Secret hinterlegen.