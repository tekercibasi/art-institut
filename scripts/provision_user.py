#!/usr/bin/env python3
"""Provision a new user in Nextcloud, Kimai, and (optionally) Netcup mailserver.

Usage:
    ./provision_user.py --email user@example.com --first-name Alice --last-name Smith

The script will:
  * derive a username (e.g. a.smith) and ensure uniqueness
  * check whether the user/email already exists in Nextcloud or Kimai
  * create the user in both systems with a shared random password
  * optionally create a Netcup mailbox (if NETCUP_* env vars are set and `zeep` is installed)
  * print the generated credentials for manual delivery

Kimai defaults to ROLE_USER; adjust with --kimai-roles if needed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shlex
import string
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from netcup_mail import NetcupMailClient
    HAS_NETCUP = True
except ImportError:
    NetcupMailClient = None  # type: ignore
    HAS_NETCUP = False

BASE_DIR = Path(__file__).resolve().parent.parent
NEXTCLOUD_CONTAINER = "art-institut-nextcloud"
KIMAI_CONTAINER = "art-institut-kimai"

@dataclass
class UserRequest:
    email: str
    first_name: str
    last_name: str
    username: str

@dataclass
class ProvisionResult:
    username: str
    password: str
    nextcloud_created: bool
    kimai_created: bool
    netcup_created: Optional[bool] = None

# ---------------------------------------------------------------------------
# Utility helpers


def run(cmd: Iterable[str], *, check: bool = True, capture: bool = False, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    result = subprocess.run(
        list(cmd),
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        env=env,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(cmd)}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    return result


def random_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def generate_username(first: str, last: str, existing: Iterable[str]) -> str:
    base = f"{slugify(first)[0]}.{slugify(last)}"
    if not base:
        raise ValueError("Unable to derive username from provided names")
    username = base
    counter = 1
    existing_set = set(existing)
    while username in existing_set:
        counter += 1
        username = f"{base}{counter}"
    return username

# ---------------------------------------------------------------------------
# Nextcloud helpers


def _occ_base_cmd() -> List[str]:
    return [
        "docker",
        "exec",
        "-i",
        NEXTCLOUD_CONTAINER,
        "bash",
        "-lc",
        "cd /var/www/html && su -s /bin/sh www-data -c \"{}\"",
    ]


def occ(command: str, *, capture: bool = False, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    base = _occ_base_cmd()
    base[-1] = base[-1].format(command)
    return run(base, capture=capture, env=env)


def list_nextcloud_users() -> Dict[str, str]:
    result = occ("php occ user:list --output=json", capture=True)
    return json.loads(result.stdout)


def nextcloud_user_info(username: str) -> Optional[dict]:
    try:
        result = occ(f"php occ user:info {username} --output=json", capture=True)
        return json.loads(result.stdout)
    except RuntimeError:
        return None


def nextcloud_email_exists(email: str) -> Optional[str]:
    for uid in list_nextcloud_users().keys():
        info = nextcloud_user_info(uid)
        if info and info.get("email", "").lower() == email.lower():
            return uid
    return None


def create_nextcloud_user(username: str, email: str, display_name: str, password: str) -> bool:
    display_q = shlex.quote(display_name)
    email_q = shlex.quote(email)
    user_q = shlex.quote(username)
    pass_q = shlex.quote(password)
    command = (
        f"OC_PASS={pass_q} php occ user:add --password-from-env --display-name {display_q} --email {email_q} {user_q}"
    )
    try:
        occ(command)
        return True
    except RuntimeError as exc:
        if "already exists" in str(exc):
            return False
        raise


def set_nextcloud_language(username: str, language: str = "de", locale: str = "de_DE") -> None:
    user_q = shlex.quote(username)
    try:
        occ(f"php occ user:setting {user_q} settings language {language}")
        occ(f"php occ user:setting {user_q} locale locale {locale}")
    except RuntimeError as exc:
        print(f"Warnung: Konnte Sprache für Nextcloud-Benutzer {username} nicht setzen: {exc}")

# ---------------------------------------------------------------------------
# Kimai helpers


def kimai(cmd: str, *, capture: bool = False, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    base = [
        "docker",
        "exec",
        "-i",
        KIMAI_CONTAINER,
        "bash",
        "-lc",
        cmd,
    ]
    return run(base, capture=capture, env=env)


def list_kimai_users() -> List[Tuple[str, str]]:
    result = kimai("/opt/kimai/bin/console kimai:user:list", capture=True)
    users: List[Tuple[str, str]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("-") or line.startswith("Username"):
            continue
        parts = [part.strip() for part in re.split(r"\s{2,}", line)]
        if len(parts) >= 2:
            users.append((parts[0], parts[1]))
    return users


def kimai_user_exists(username: str) -> bool:
    return any(u == username for u, _ in list_kimai_users())


def kimai_email_exists(email: str) -> bool:
    return any(e.lower() == email.lower() for _, e in list_kimai_users())


def create_kimai_user(username: str, email: str, password: str, roles: List[str]) -> bool:
    role_arg = ",".join(roles)
    user_q = shlex.quote(username)
    email_q = shlex.quote(email)
    role_q = shlex.quote(role_arg)
    pass_q = shlex.quote(password)
    cmd = f"/opt/kimai/bin/console kimai:user:create {user_q} {email_q} {role_q} {pass_q}"
    try:
        kimai(cmd)
        return True
    except RuntimeError as exc:
        if "already exists" in str(exc):
            return False
        raise

# ---------------------------------------------------------------------------
# Provision workflow




def create_mailbox_if_configured(email: str, username: str, password: str, first: str, last: str) -> Optional[dict]:
    if not HAS_NETCUP:
        return None
    if not (NETCUP_CUSTOMER_NUMBER and NETCUP_API_KEY and NETCUP_API_PASSWORD and NETCUP_MAIL_DOMAIN):
        return None
    client = NetcupMailClient(NETCUP_CUSTOMER_NUMBER, NETCUP_API_KEY, NETCUP_API_PASSWORD)
    try:
        client.login()
        mailbox_result = client.create_mailbox(
            domain=NETCUP_MAIL_DOMAIN,
            username=username,
            password=password,
            quota_mb=NETCUP_MAIL_QUOTA_MB,
            firstname=first,
            lastname=last,
        )
        return mailbox_result
    finally:
        client.logout()


def provision_user(email: str, first: str, last: str, kimai_roles: List[str]) -> ProvisionResult:
    if "@" not in email:
        raise ValueError("Email address must contain '@'")

    nc_users = list_nextcloud_users()
    username = generate_username(first, last, nc_users.keys())

    # Ensure unique email across systems
    existing_nc = nextcloud_email_exists(email)
    existing_kimai = kimai_email_exists(email)
    if existing_nc or existing_kimai:
        raise RuntimeError(
            f"Email {email} already exists in Nextcloud (user {existing_nc}) or Kimai"
        )

    if kimai_user_exists(username):
        username = generate_username(first, last, list(nc_users.keys()) + [u for u, _ in list_kimai_users()])

    password = random_password()
    display_name = f"{first} {last}".strip()

    nc_created = create_nextcloud_user(username, email, display_name, password)
    if nc_created:
        set_nextcloud_language(username)
    kimai_created = create_kimai_user(username, email, password, kimai_roles)
    netcup_result = None
    try:
        netcup_result = create_mailbox_if_configured(email, username, password, first, last)
    except Exception as exc:
        print(f"Netcup mailbox creation failed: {exc}")

    result = ProvisionResult(
        username=username,
        password=password,
        nextcloud_created=nc_created,
        kimai_created=kimai_created,
        netcup_created=None,
    )
    if netcup_result is not None:
        result.netcup_created = True
        print('Netcup mailbox created:', netcup_result)
    elif NETCUP_CUSTOMER_NUMBER:
        result.netcup_created = False
        print('Netcup mailbox creation skipped; check NETCUP_* env vars if you want auto-mailboxes.')
    return result

# ---------------------------------------------------------------------------
# CLI


NETCUP_CUSTOMER_NUMBER = os.getenv('NETCUP_CUSTOMER_NUMBER')
NETCUP_API_KEY = os.getenv('NETCUP_API_KEY')
NETCUP_API_PASSWORD = os.getenv('NETCUP_API_PASSWORD')
NETCUP_MAIL_DOMAIN = os.getenv('NETCUP_MAIL_DOMAIN')
NETCUP_MAIL_QUOTA_MB = int(os.getenv('NETCUP_MAIL_QUOTA_MB', '2048'))

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision a user in Nextcloud and Kimai")
    parser.add_argument("--email", required=True, help="User email address")
    parser.add_argument("--first-name", required=True, help="First name")
    parser.add_argument("--last-name", required=True, help="Surname")
    parser.add_argument(
        "--kimai-roles",
        default="ROLE_USER",
        help="Comma-separated Kimai roles (default: ROLE_USER)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    roles = [role.strip() for role in args.kimai_roles.split(",") if role.strip()]
    try:
        result = provision_user(args.email, args.first_name, args.last_name, roles)
    except Exception as exc:
        raise SystemExit(f"ERROR: {exc}")

    print("Benutzeranlage abgeschlossen")
    print("--------------------------------")
    print(f"Benutzername: {result.username}")
    print(f"Initiales Passwort: {result.password}")
    print(f"Nextcloud angelegt: {'ja' if result.nextcloud_created else 'nein (existierte bereits?)'}")
    print(f"Kimai angelegt: {'ja' if result.kimai_created else 'nein (existierte bereits?)'}")
    if result.netcup_created is True:
        print("Netcup-Postfach angelegt: ja (siehe Antwort oben)")
    elif result.netcup_created is False:
        print("Netcup-Postfach angelegt: nein (Fehler siehe oben)")
    print()
    print("Nächste Schritte:")
    print("  - Zugangsdaten sicher an den Benutzer übermitteln und um sofortige Passwortänderung bitten.")
    print("  - Benötigte Gruppen/Rollen in beiden Systemen ergänzen.")
    if result.netcup_created is None:
        print("  - Netcup-Postfach manuell anlegen (NETCUP_* Variablen setzen, um dies zu automatisieren).")
    print()
    print("Vorschlag für Begrüßungsnachricht:")
    print("  Nextcloud: https://nextcloud.art-institut.de")
    print(f"    • Benutzername: {result.username}")
    print(f"    • Initiales Passwort: {result.password}")
    print("    • Nach dem ersten Login bitte unter Einstellungen → Sicherheit das Passwort ändern und ggf. 2FA aktivieren.")
    print("  Kimai: https://kimai.art-institut.de")
    print("    • Anmeldung mit denselben Zugangsdaten. Passwortänderung unter Mein Profil → Passwort.")


if __name__ == "__main__":
    main()
