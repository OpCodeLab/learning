"""Password hashing (scrypt), TOTP (RFC 6238) and random tokens. Stdlib only."""
import base64
import hashlib
import hmac
import secrets
import struct
import time

_N, _R, _P = 2 ** 15, 8, 1   # ~64 MB, ~0.1 s per hash on the VPS


def hash_password(pw):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=128 * 1024 * 1024)
    return "scrypt$%d$%d$%d$%s$%s" % (_N, _R, _P, salt.hex(), h.hex())


def verify_password(pw, stored):
    try:
        algo, n, r, p, salt, h = stored.split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                              maxmem=128 * 1024 * 1024)
        return hmac.compare_digest(calc.hex(), h)
    except (ValueError, AttributeError):
        return False


# A fixed hash to compare against when the email is unknown (same timing either way).
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def new_totp_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_at(secret, step):
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    h = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000)


def totp_check(secret, code, last_step=0):
    """Return the matching time step (to store, so a code can't be replayed) or None."""
    code = (code or "").strip().replace(" ", "")
    if not (len(code) == 6 and code.isdigit()):
        return None
    now = int(time.time()) // 30
    for step in (now, now - 1, now + 1):
        if step > last_step and hmac.compare_digest(totp_at(secret, step), code):
            return step
    return None


def new_token():
    return secrets.token_urlsafe(32)


def token_hash(token):
    """Only hashes of session and invite tokens are stored: a DB leak opens nothing."""
    return hashlib.sha256(token.encode()).hexdigest()
