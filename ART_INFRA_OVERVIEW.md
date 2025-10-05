# Infrastrukturübersicht `<ART_ROOT>`

Diese Datei fasst zusammen, welche Komponenten im Verzeichnis `<ART_ROOT>` betrieben werden, welche individuellen Anpassungen vorgenommen wurden und welche zusätzlichen Werkzeuge das Setup umfasst.

> Platzhalter: `<ART_ROOT>` steht für das vertrauliche Deployment-Verzeichnis dieser Instanz, `<NPM_ROOT>` für den gemeinsamen Reverse-Proxy-Stack.

## 1. Zweck & Gesamtaufbau

- Docker-basierter Stack für **ART – Gesellschaft für angewandte Regeneration und Transformation GmbH & Co. KG**
- Enthält produktive Dienste für Zusammenarbeit und Zeiterfassung sowie Automatisierungen (Backups, User-Provisionierung)
- Wird hinter dem bestehenden Nginx Proxy Manager (separates Compose unter `<NPM_ROOT>`) betrieben und nutzt das externe Docker-Netzwerk `proxy_net`

## 2. Container & Dienste

| Service | Container | Beschreibung | Besonderheiten |
| --- | --- | --- | --- |
| Landingpage | `art-institut-overview` | Statische HTML-Seite aus `<ART_ROOT>/web` | Anpassung mit Branding/Logo + Impressum/Disclaimer |
| Nextcloud | `art-institut-nextcloud` | Kollaborationsplattform (Dateien, Talk, Whiteboard) | Hinterlegen von Trusted Domains, Encryption aktiviert, Sprache/Branding, Talk/Whiteboard Anbindung |
| Nextcloud Cron | `art-institut-nextcloud-cron` | Führt `cron.php` alle 5 Minuten aus | Eigenständiger Container auf Basis von `nextcloud:apache` mit EntryPoint `/cron.sh` |
| Nextcloud DB | `art-institut-nextcloud-db` | MariaDB 10.11 | Zusätzliche Startoptionen (READ-COMMITTED, ROW binlog) |
| Redis | `art-institut-redis` | Redis 7 für NC File Locking | Passwort in `.env`, persistente Volume |
| Kimai | `art-institut-kimai` | Zeiterfassung (Kimai2, Apache-Image) | Läuft hinter Proxy unter Subdomain, Mailer via SMTP konfiguriert |
| Kimai DB | `art-institut-kimai-db` | MariaDB 10.11 | Separate Credentials in `.env` |
| TURN/STUN | `art-institut-turn` | Coturn für Nextcloud Talk | TLS-Zertifikat via Let’s Encrypt, Ports 3478/5349 + Relay-Port-Bereich, nutzt Shared Secret |
| Talk Signaling | `art-institut-signaling` | High Performance Backend (strukturag/nextcloud-spreed-signaling) | Konfiguration über `.env`, TURN-Anbindung, Reverse Proxy `signaling.art-institut.de` |
| Whiteboard WebSocket | `art-institut-whiteboard` | Echtzeit-Server für Nextcloud Whiteboard | Läuft auf Port 3002, JWT-Secret via `.env`, Reverse Proxy `whiteboard-wss.art-institut.de` |

## 3. Domains & Reverse Proxy (Nginx Proxy Manager)

- `cloud.art-institut.de` → Overview-Page (`art-institut-overview`)
- `nextcloud.art-institut.de` → Hauptinstanz Nextcloud (WebSocket/Collabora via Proxy-Host)
- `kimai.art-institut.de` → Kimai Weboberfläche
- `signaling.art-institut.de` → Talk Signaling (Websocket, Let’s Encrypt)
- `whiteboard-wss.art-institut.de` → Whiteboard Websocket-Server
- `turn.art-institut.de` (+ optional `stun.art-institut.de`) → Coturn (Direktport-Zugriff, Zertifikate unter `/etc/letsencrypt/live/turn.art-institut.de`)
- Alle Proxy Hosts erzwingen HTTPS, erlauben WebSocket-Upgrades und nutzen Let’s-Encrypt-Zertifikate

## 4. Konfiguration & individuelle Anpassungen

### Nextcloud
- `config.php`/ENV Variablen: Trusted Domains (`nextcloud.art-institut.de`, `nc.art-institut.de`), Overwrite Host/Protocol, Forwarded IP Handling
- Sprache/Locale per Provisionierungsskript standardmäßig auf Deutsch (`set_nextcloud_language`)
- Talk: TURN-Server (`coturn`), Signaling-Server (`strukturag`), Cron-Modus aktiviert, Redis-Locking aktiviert
- Whiteboard: WebSocket-Backend `wss://whiteboard-wss.art-institut.de`, JWT-Secret aus `.env`
- Server-side Encryption aktiviert, Master-Key Sicherung via Backup-Skript
- Ergänzte Apps: Talk, Whiteboard, CADViewer (Konfiguration gemäß README), SMTP eingerichtet

### Kimai
- Mailer via Netcup SMTP (`no-reply@art-institut.de`, Port 465, SSL/TLS)
- Reverse-Proxy Betrieb (Subdomain), Logging über Docker Volumes (keine Schreibrechte in Container)
- Provisionierungsskript legt Kimai-User parallel zu Nextcloud an (Default-Rolle `ROLE_USER`, optional override)

### Automatisierung & Skripte
- `<ART_ROOT>/scripts/backup.py`: Komplettbackup (Datenbanken, Volumes, Repo, Nextcloud Master-Key) inkl. Rotationslogik (15 min, 30 min, täglich, 5-tägig, 30-tägig). Cronjob alle 15 Minuten, Log unter `<ART_ROOT>/backups/backup.log`
- `<ART_ROOT>/scripts/provision_user.py`: CLI zur Benutzeranlage in Nextcloud & Kimai (Username-Autogenerierung, Passwort, Sprache, SMTP-Mailtext auf Deutsch). Optional Netcup-Mailbox via SOAP-API (`netcup_mail.py`) bei gesetzten Credentials
- `<ART_ROOT>/scripts/netcup_mail.py`: SOAP-Client für Netcup CCP API (Mailbox anlegen/löschen) – nutzt ENV `NETCUP_*`

### Infrastruktur & Sicherheit
- `.env` enthält alle Secrets (DB-Passwörter, Redis-Passwort, TURN-Secret, Signaling Keys, Whiteboard JWT). Datei wird nicht versioniert
- Docker Volumes für alle persistenten Daten (Datenbanken, NC Data, Redis). Turn nutzt Host-Zertifikate (Mount via `.env` Pfade)
- Cron-Container reduziert Host-Crontab-Anforderungen, wenn Docker nach Reboot startet
- Backup-Archiv legt Nextcloud Masterkey ab – Voraussetzung für serverseitige Verschlüsselung

## 5. Unterschiede zur „Out-of-the-Box“-Auslieferung

- Add-on Dienste (Talk Signaling, TURN, Whiteboard Websocket) wurden zusätzlich eingerichtet
- Cron-Betrieb per dediziertem Container statt simplen Webcron/App-Modus
- Erweiterte Automatisierung (Backup/Provisionierung) inkl. Rotationsstrategie und Netcup-Anbindung
- Docker Compose erweitert um Redis, Cron, Signaling, Whiteboard, TURN; `.env`-Struktur angepasst
- Nextcloud Apps vorkonfiguriert (CADViewer, Whiteboard, Talk), Standardsprache und Willkommensmail für deutschsprachige Nutzer
- Kimai mit SMTP, Reverse-Proxy Anpassungen sowie automatisierter Benutzeranlage
- Dokumentation/README aktualisiert (deutscher Kontext, Pfad-Anonymisierung, Betriebsanweisungen)

## 6. Betrieb & Monitoring

- Neustart-Strategie: Alle Container `restart: unless-stopped` → automatischer Start nach Server-Reboot
- Health-Checks:
  - `docker compose ps` in `<ART_ROOT>`
  - Logs: `docker logs art-institut-signaling`, `art-institut-whiteboard`, `art-institut-turn`
- Backup-Prüfung: `scripts/backup.py check`
- Benutzeranlage via Provisionierungsskript (Ausgabe enthält alle Informationen für Onboarding-E-Mail)

## 7. Weiterführende Aufgaben / TODOs (Stand: 2025-09)

- Let’s Encrypt für `whiteboard-wss.art-institut.de`, sobald DNS final propagiert ist (NPM Retry)
- Regelmäßige Prüfung der Nextcloud Admin Warnungen / Talk Performance
- Optional: Hochverfügbarkeit für Signaling/Whiteboard (Redis-Backend, mehrere Instanzen)
