# hAI.VfBAHKaessle – VfB Grötzingen AH Bierkässle

[![Buy me a coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/highfish)

[![VfB Grötzingen AH](https://img.shields.io/badge/VfB-Grötzingen%20AH-blue)](https://github.com/jbkunama1/hAI.VfBAHKaessle)

[![GitHub stars](https://img.shields.io/github/stars/jbkunama1/hAI.VfBAHKaessle)](https://github.com/jbkunama1/hAI.VfBAHKaessle)
[![TruffleHog scan](https://img.shields.io/badge/security-TruffleHog-blue)](https://github.com/jbkunama1/hAI.VfBAHKaessle/actions)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](https://github.com/jbkunama1/hAI.VfBAHKaessle/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://github.com/jbkunama1/hAI.VfBAHKaessle)
[![Docker ready](https://img.shields.io/badge/docker-ready-blue)](https://github.com/jbkunama1/hAI.VfBAHKaessle)

Flask-Webapp mit SQLite-Backend für das AH-Bierkässle des VfB Grötzingen, inklusive Telegram-Bot und einer kleinen GitHub-Pages-Startseite (`index.html`). Lizenz: MIT (siehe `LICENSE`).

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
    - `password_reset_requests` (interne Passwort-Vergessen-Anfragen für den Admin)
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
   git clone hAI.VfBAHKaessle
   cd hAI.VfBAHKaessle
   ```
2. Optional GitHub Pages aktivieren:
   - In den Repo-Einstellungen `Pages`
   - Branch `main` (oder `master`) und Ordner `/root` wählen
   - Die Datei `index.html` dient als Startseite

## Features im Detail

- Registrierung und Login für Spieler
- **Hilfetext bei der Registrierung**: Es ist keine E-Mail-Adresse nötig – Nutzer wählen einen Klarnamen oder passenden Spitznamen als Benutzername sowie ein frei wählbares Passwort
- Biereinträge pro Datum (z. B. immer mittwochs nach dem Training)
- Preis pro Bier konfigurierbar über `BEER_PRICE` (Standard: 1.50 €)
- **Pro Eintrag ein Bezahlt-Status mit Zahlart (Bar/PayPal)**
  - Spieler sehen bei ihren Einträgen sofort, was noch offen und was schon bezahlt ist
  - Admins können den Status für alle Spieler setzen oder korrigieren
- Monatsübersicht pro Spieler sowie Gesamtübersicht
- **„Passwort vergessen?“-Funktion**: Statt Mail-Versand wird eine interne Anfrage an den Admin erzeugt, die dieser im Admin-Panel sieht und mit einem neu gesetzten Passwort beantwortet
- Mobil-taugliche UI (Bootstrap 5, dunkles Theme)
- Telegram-Bot zur schnellen Erfassung direkt aus Telegram

## Lokale Installation (ohne Docker)

Voraussetzungen: Python 3.10+

```bash
git clone hAI.VfBAHKaessle
cd hAI.VfBAHKaessle
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Web-App starten

```bash
export SECRET_KEY="change-me"      # in Produktion durch sicheren Key ersetzen
export BEER_PRICE="1.50"           # Preis pro Bier in Euro
export ADMIN_USERNAMES="admin"     # kommagetrennte Liste der Admin-Benutzernamen
export PORT="1904"                 # Port für die Web-App
python app.py
```

Danach im Browser: `http://localhost:1904`

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
   - Im Browser `http://<server>:1904` öffnen
   - Benutzer registrieren (Benutzername + Passwort – keine E-Mail-Adresse nötig)
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

### Image von GHCR beziehen

Das Image wird automatisch über den GitHub-Workflow `.github/workflows/docker-build-push.yml` gebaut und nach **GHCR** (`ghcr.io/jbkunama1/hai.vfbahkaessle`) gepusht:

- **Push auf `main`** → baut & pusht `latest` + Commit-SHA-Tag
- **Git-Tag `v*`** (z. B. `v1.2.0`) → baut & pusht zusätzlich SemVer-Tags (`1.2.0`, `1.2`)
- **Manuell** über GitHub → **Actions** → *Docker Build & Push (GHCR)* → **Run workflow**

Lokal nur noch das fertige Image ziehen:

```bash
docker pull ghcr.io/jbkunama1/hai.vfbahkaessle:latest
```

> **Hinweis (privat/Portainer):** Für öffentliche Repos ist das Paket public und ohne Login pullbar. Bei privaten Paketen einmalig `docker login ghcr.io` (bzw. Registry-Credentials im Portainer hinterlegen).

### Stack mit docker-compose

```bash
docker compose pull && docker compose up -d   # neues Image ziehen + starten
```

`docker-compose.yml` definiert zwei Services:

```yaml
services:
  bierkaessle_web:
    image: ghcr.io/jbkunama1/hai.vfbahkaessle:latest
    container_name: bierkaessle_web
    ports:
      - "1904:1904"
    environment:
      - SECRET_KEY=change-me
      - BEER_PRICE=1.50
      - ADMIN_USERNAMES=admin
    volumes:
      - bierkaessle_data:/app/instance
    restart: unless-stopped

  bierkaessle_bot:
    image: ghcr.io/jbkunama1/hai.vfbahkaessle:latest
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

- Web-App: erreichbar auf Port 1904
- Datenbank: Volume `bierkaessle_data` (enthält `instance/bierkaessle.sqlite3`)

### Einsatz in Portainer

1. In Portainer unter **Stacks → Add stack** gehen.
2. Inhalt der `docker-compose.yml` einfügen.
3. Im Service `bierkaessle_bot` die Umgebungsvariable `TELEGRAM_BOT_TOKEN` auf deinen echten Bot-Token setzen.
4. Stack deployen.
5. Für Updates: Stack erneut bereitstellen bzw. `docker compose pull && docker compose up -d` (das Image kommt dann frisch von GHCR).

## Sicherheit / Betrieb

- In Produktion immer einen starken `SECRET_KEY` verwenden.
- Zugriff auf die Web-App über einen Reverse Proxy (nginx, Traefik, Cloudflare Tunnel) absichern.
- Volume `bierkaessle_data` regelmäßig sichern (Backups).
- Telegram-Bot-Token niemals ins Repo commiten, sondern nur als ENV/Secret hinterlegen.
- Passwort-Reset läuft bewusst **ohne E-Mail-Versand** – Anfragen werden intern gespeichert und ausschließlich vom Admin im Panel bearbeitet.

## Admin-Funktionen

Für Admins (erster registrierter User oder über `ADMIN_USERNAMES` konfiguriert) steht ein eigener Bereich zur Verfügung:

- Überblick über alle Nutzer (Biere, Euro, letztes Datum, Rolle)
- **Der Account `admin` selbst erscheint nicht in der normalen Nutzerübersicht** – er ist ausschließlich im Admin-Panel sichtbar, da er nur zur Verwaltung dient
- **Passwort-Vergessen-Anfragen**: Nutzer, die „Passwort vergessen?“ nutzen, erzeugen eine interne Anfrage, die im Admin-Panel mit einem Badge (Anzahl offener Anfragen) angezeigt wird. Der Admin trägt dort direkt ein neues Passwort ein und setzt es für den betroffenen Account
- Liste der letzten Einträge aller Spieler (global)
- Einträge bearbeiten (Datum und Anzahl ändern)
- Einträge löschen (z. B. bei Fehlbuchungen)
- Einträge als bezahlt markieren, inkl. Zahlart (Bar/PayPal)
- CSV-Export aller Einträge eines Monats: `username, date, amount`

Zugriff auf das Admin-Panel erfolgt über den Link **„Admin“** in der Navigation (nur sichtbar für Admin-Accounts).
