#!/usr/bin/env python3
"""Provision a new user in Nextcloud and Kimai.

Usage:
    ./provision_user.py --email user@example.com --first-name Alice --last-name Smith

The script will:
  * derive a username (e.g. a.smith) and ensure uniqueness
  * check whether the user/email already exists in Nextcloud or Kimai
  * create the user in both systems with a shared random password
  * print the generated credentials for manual delivery

Kimai defaults to ROLE_USER; adjust with --kimai-roles if needed.

Netcup mailbox creation is not automated here; see the README notes below.
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

BASE_DIR = Path("/home/art-institut")
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
    kimai_created = create_kimai_user(username, email, password, kimai_roles)

    return ProvisionResult(
        username=username,
        password=password,
        nextcloud_created=nc_created,
        kimai_created=kimai_created,
    )

# ---------------------------------------------------------------------------
# CLI


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

    print("User provisioning complete")
    print("--------------------------------")
    print(f"Username: {result.username}")
    print(f"Password: {result.password}")
    print(f"Nextcloud user created: {'yes' if result.nextcloud_created else 'no (already existed?)'}")
    print(f"Kimai user created: {'yes' if result.kimai_created else 'no (already existed?)'}")
    print()
    print("Next steps:")
    print("  - Share the credentials securely with the user and encourage immediate password change.")
    print("  - Create/assign the corresponding mailbox in Netcup manually (API requires separate credentials).")
    print("  - Add group memberships or roles as required in both systems.")
    print()
    print("Netcup mailboxes:")
    print("  This script does NOT create mailboxes automatically. Use the Netcup CCP or their SOAP/JSON API")
    print("  (https://ccp.netcup.net/run/webservice/serverservice/) with your customer number, API key and password.")
    print("  Consider extending this script once those credentials can be provided securely.")


if __name__ == "__main__":
    main()
