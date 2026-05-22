"""
auth.py — User + role management with file-based storage.

Storage:
  data/users.json — {username: {role, password_hash, ...}}
  data/roles.json — {role_name: {permissions: {tabs, actions}, ...}}

Password hashing: PBKDF2-HMAC-SHA256, 600,000 iterations, 16-byte salt.
Format: 'pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>' (self-contained).

Security:
  - Passwords NEVER stored plaintext
  - Bcrypt-equivalent strength via PBKDF2 (NIST 2023 spec)
  - Owner account ('gari') cannot be disabled or deleted
  - Built-in roles (admin/trader/viewer) cannot be deleted

Public API:
  verify_user(username, password)            → user dict or None
  list_users()                                → list[dict]
  create_user(username, password, role, **)   → user dict
  update_user(username, **fields)             → user dict
  delete_user(username)                       → bool
  change_password(username, new_password)     → bool
  set_last_login(username)                    → None

  list_roles()                                → list[dict]
  get_role(role_name)                         → role dict or None
  create_role(name, permissions, **)          → role dict
  update_role(role_name, **fields)            → role dict
  delete_role(role_name)                      → bool

  user_has_permission(username, perm_type, perm)  → bool
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).parent
USERS_PATH = _ROOT / "data" / "users.json"
ROLES_PATH = _ROOT / "data" / "roles.json"

OWNER = "gari"  # cannot be deleted/disabled
PBKDF2_ITERATIONS = 600_000  # NIST 2023 recommendation


# ───── Password hashing ──────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Return PBKDF2-SHA256 hash with random salt. Self-contained, no deps."""
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verify."""
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return secrets.compare_digest(expected, actual)
    except Exception:
        return False


# ───── Storage helpers ───────────────────────────────────────────────────

def _load_users() -> dict:
    try:
        return json.loads(USERS_PATH.read_text())
    except Exception:
        return {"version": 1, "users": {}}


def _save_users(data: dict) -> None:
    USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = USERS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, USERS_PATH)


def _load_roles() -> dict:
    try:
        return json.loads(ROLES_PATH.read_text())
    except Exception:
        return {"version": 1, "roles": {}}


def _save_roles(data: dict) -> None:
    ROLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ROLES_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, ROLES_PATH)


# ───── User CRUD ─────────────────────────────────────────────────────────

def _public_user(u: dict) -> dict:
    """Strip password hash from user record before returning to clients."""
    return {k: v for k, v in u.items() if k != "password_hash"}


def list_users() -> list[dict]:
    data = _load_users()
    return [_public_user(u) for u in data.get("users", {}).values()]


def get_user(username: str) -> dict | None:
    data = _load_users()
    u = data.get("users", {}).get(username)
    return _public_user(u) if u else None


def verify_user(username: str, password: str) -> dict | None:
    """Return public user record on auth success; None on fail."""
    if not username or not password:
        return None
    data = _load_users()
    u = data.get("users", {}).get(username)
    if not u or u.get("disabled"):
        return None
    if not verify_password(password, u.get("password_hash") or ""):
        return None
    return _public_user(u)


def _validate_username(username: str) -> None:
    if not re.match(r"^[a-z][a-z0-9_-]{1,30}$", username or ""):
        raise ValueError("username must be 2-31 chars, lowercase letters/digits/_/-, starting with a letter")


VALID_TAB_PROFILES = ("beginner", "trader", "quant", "all", "custom")


def create_user(username: str, password: str, role: str,
                display_name: str = "", email: str = "",
                disabled: bool = False, tab_profile: str = "trader") -> dict:
    _validate_username(username)
    if not get_role(role):
        raise ValueError(f"role '{role}' does not exist")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    if tab_profile not in VALID_TAB_PROFILES:
        raise ValueError(f"tab_profile must be one of {VALID_TAB_PROFILES}")
    data = _load_users()
    if username in data.get("users", {}):
        raise ValueError(f"user '{username}' already exists")
    new_user = {
        "username":      username,
        "display_name":  display_name or username,
        "email":         email or "",
        "role":          role,
        "tab_profile":   tab_profile,
        "password_hash": hash_password(password),
        "created_at":    datetime.now().isoformat(timespec="seconds"),
        "last_login":    None,
        "disabled":      bool(disabled),
        "is_owner":      False,
        "must_change_password": True,
    }
    data.setdefault("users", {})[username] = new_user
    _save_users(data)
    return _public_user(new_user)


def update_user(username: str, **fields) -> dict:
    """Update mutable fields. Cannot change username or password_hash via this."""
    data = _load_users()
    u = data.get("users", {}).get(username)
    if not u:
        raise ValueError(f"user '{username}' not found")
    if username == OWNER and fields.get("disabled"):
        raise ValueError("owner account cannot be disabled")
    allowed = {"display_name", "email", "role", "disabled", "must_change_password",
               "tab_profile", "tabs_override", "sub_tabs_override", "actions_override"}
    confirm_demote = bool(fields.pop("__confirm_owner_demote__", False))
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "role":
            if not get_role(v):
                raise ValueError(f"role '{v}' does not exist")
            # Block silent demotion of the owner from admin — caller must pass
            # __confirm_owner_demote__: true to acknowledge. Prevents accidental
            # lockout if the UI ever ships a buggy role-select default again.
            if username == OWNER and u.get("role") == "admin" and v != "admin" and not confirm_demote:
                raise ValueError(
                    "Refusing to demote the OWNER account from admin without an "
                    "explicit __confirm_owner_demote__:true flag. This prevents "
                    "accidental lockout."
                )
        if k == "tab_profile" and v not in VALID_TAB_PROFILES:
            raise ValueError(f"tab_profile must be one of {VALID_TAB_PROFILES}")
        if k in ("tabs_override", "sub_tabs_override", "actions_override"):
            # Empty list / None = inherit from role. Non-empty list = custom override.
            if v is None or v == "" or v == []:
                u.pop(k, None)
                continue
            if not isinstance(v, list):
                raise ValueError(f"{k} must be a list of strings (or empty/null to inherit)")
            v = [str(x).strip() for x in v if str(x).strip()]
        u[k] = v
    _save_users(data)
    return _public_user(u)


def delete_user(username: str) -> bool:
    if username == OWNER:
        raise ValueError("owner account cannot be deleted")
    data = _load_users()
    if username not in data.get("users", {}):
        return False
    del data["users"][username]
    _save_users(data)
    return True


def change_password(username: str, new_password: str) -> bool:
    if len(new_password) < 8:
        raise ValueError("password must be at least 8 characters")
    data = _load_users()
    u = data.get("users", {}).get(username)
    if not u:
        return False
    u["password_hash"] = hash_password(new_password)
    u["must_change_password"] = False
    _save_users(data)
    return True


def set_last_login(username: str, ip: str | None = None) -> None:
    data = _load_users()
    u = data.get("users", {}).get(username)
    if u:
        u["last_login"] = datetime.now().isoformat(timespec="seconds")
        if ip:
            u["last_login_ip"] = ip
        _save_users(data)


# ───── Role CRUD ─────────────────────────────────────────────────────────

def list_roles() -> list[dict]:
    data = _load_roles()
    return [{"id": k, **v} for k, v in (data.get("roles") or {}).items()]


def get_role(role_name: str) -> dict | None:
    data = _load_roles()
    r = (data.get("roles") or {}).get(role_name)
    return {"id": role_name, **r} if r else None


def create_role(role_id: str, name: str, description: str = "",
                color: str = "info",
                tabs: list | None = None, actions: list | None = None) -> dict:
    if not re.match(r"^[a-z][a-z0-9_-]{1,30}$", role_id or ""):
        raise ValueError("role id must be 2-31 chars, lowercase letters/digits/_/-, starting with a letter")
    data = _load_roles()
    if role_id in (data.get("roles") or {}):
        raise ValueError(f"role '{role_id}' already exists")
    role = {
        "name":        name or role_id,
        "description": description,
        "color":       color,
        "builtin":     False,
        "permissions": {"tabs": tabs or [], "actions": actions or []},
        "created_at":  datetime.now().isoformat(timespec="seconds"),
    }
    data.setdefault("roles", {})[role_id] = role
    _save_roles(data)
    return {"id": role_id, **role}


def update_role(role_id: str, **fields) -> dict:
    data = _load_roles()
    r = (data.get("roles") or {}).get(role_id)
    if not r:
        raise ValueError(f"role '{role_id}' not found")
    allowed = {"name", "description", "color", "permissions"}
    for k, v in fields.items():
        if k in allowed:
            r[k] = v
    _save_roles(data)
    return {"id": role_id, **r}


def delete_role(role_id: str) -> bool:
    data = _load_roles()
    r = (data.get("roles") or {}).get(role_id)
    if not r:
        return False
    if r.get("builtin"):
        raise ValueError(f"cannot delete built-in role '{role_id}'")
    # Reassign users with this role to viewer
    users_data = _load_users()
    for u in (users_data.get("users") or {}).values():
        if u.get("role") == role_id:
            u["role"] = "viewer"
    _save_users(users_data)
    del data["roles"][role_id]
    _save_roles(data)
    return True


# ───── Permission checks ────────────────────────────────────────────────

def user_has_permission(username: str, perm_type: str, perm: str) -> bool:
    """Check whether the user's role grants `perm` of `perm_type`.

    perm_type: one of 'tabs' | 'sub_tabs' | 'actions'.
    perm:       the specific item (e.g. 'submit_trade', 'elite', 'plan').

    Wildcard '*' in the role's permission list grants everything in that perm_type.
    (CapStudio 2026-05-09 — added 'sub_tabs' alongside 'tabs' and 'actions'.)
    """
    data = _load_users()
    u = data.get("users", {}).get(username)
    if not u or u.get("disabled"):
        return False
    role = get_role(u.get("role") or "viewer")
    if not role:
        return False
    perms = (role.get("permissions") or {}).get(perm_type) or []
    return "*" in perms or perm in perms


def get_user_permissions(username: str) -> dict:
    """Return tabs + sub_tabs + actions arrays for the user.

    Merge order (per key): user override (if non-empty list) > role default.
    A user with `tabs_override: ["scanner","portfolio"]` sees ONLY those two
    tabs regardless of their role. A missing/empty override falls back to
    the role's permissions.
    (CapStudio 2026-05-09 added sub_tabs · 2026-05-22 added per-user overrides.)
    """
    data = _load_users()
    u = data.get("users", {}).get(username)
    empty = {"tabs": [], "sub_tabs": [], "actions": []}
    if not u:
        return empty
    role = get_role(u.get("role") or "viewer")
    role_perms = (role or {}).get("permissions") or {}
    def _pick(key, override_key):
        ov = u.get(override_key)
        if isinstance(ov, list) and len(ov) > 0:
            return list(ov)
        return list(role_perms.get(key) or [])
    return {
        "tabs":     _pick("tabs",     "tabs_override"),
        "sub_tabs": _pick("sub_tabs", "sub_tabs_override"),
        "actions":  _pick("actions",  "actions_override"),
    }


def is_admin(username: str) -> bool:
    data = _load_users()
    u = data.get("users", {}).get(username)
    if not u:
        return False
    return u.get("role") == "admin" or user_has_permission(username, "actions", "*")


# ───── Migration helper (runs once if users.json missing) ───────────────

def ensure_seed() -> None:
    """Create users.json from default seed if missing — preserves existing creds."""
    if USERS_PATH.exists():
        return
    USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    seed = {
        "version": 1,
        "_note": "Migrated from server.py:_USERS hard-coded dict on 2026-05-07.",
        "users": {
            "gari": {
                "username":      "gari",
                "display_name":  "Gari Phaniraj",
                "email":         "garimella.phaniraj@gmail.com",
                "role":          "admin",
                "tab_profile":   "all",
                "password_hash": hash_password("swing2026"),
                "created_at":    datetime.now().isoformat(timespec="seconds"),
                "last_login":    None,
                "disabled":      False,
                "is_owner":      True,
                "must_change_password": True,
            },
            "vinod": {
                "username":      "vinod",
                "display_name":  "Vinod",
                "email":         "",
                "role":          "trader",
                "tab_profile":   "trader",
                "password_hash": hash_password("swing2026"),
                "created_at":    datetime.now().isoformat(timespec="seconds"),
                "last_login":    None,
                "disabled":      False,
                "is_owner":      False,
                "must_change_password": True,
            },
        },
    }
    USERS_PATH.write_text(json.dumps(seed, indent=2))


# Run seeding on import (idempotent)
ensure_seed()
