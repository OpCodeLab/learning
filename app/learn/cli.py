"""Admin command line, run on the VPS:

    sudo opcode-learn create-admin you@example.com   # asks the password, prints the TOTP key
    sudo opcode-learn new-totp you@example.com       # lost phone: new TOTP key
    sudo opcode-learn set-password you@example.com   # forgotten admin password
    sudo opcode-learn list
    sudo opcode-learn test-mail [to@example.com]     # check the email settings (default: the trainer)
Passwords are typed at a hidden prompt, never on the command line.
"""
import argparse
import getpass
import sys
import urllib.parse

from . import config, mailer, security, store


def ask_password():
    while True:
        pw = getpass.getpass("New password (min 14 characters): ")
        if len(pw) < 14:
            print("Too short.")
        elif pw != getpass.getpass("Repeat: "):
            print("Different, try again.")
        else:
            return pw


def show_totp(email, secret):
    uri = "otpauth://totp/%s:%s?secret=%s&issuer=%s" % (
        urllib.parse.quote(config.SITE_NAME), urllib.parse.quote(email), secret, urllib.parse.quote(config.SITE_NAME))
    print("\nAdd this key to your authenticator app (\"enter a setup key\", time-based):")
    print("  account: %s\n  key:     %s" % (email, " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))))
    print("or paste this into an app that accepts otpauth links:\n  %s\n" % uri)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="opcode-learn", description="OpCode Learn admin tool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("create-admin", "new-totp", "set-password"):
        sub.add_parser(name).add_argument("email")
    sub.add_parser("list")
    sub.add_parser("test-mail").add_argument("to", nargs="?")
    a = ap.parse_args(argv)
    store.init()

    if a.cmd == "test-mail":
        from . import web
        if not mailer.enabled():
            sys.exit("Email is off: set LEARN_SMTP_HOST, LEARN_SMTP_USER, LEARN_SMTP_PASSWORD in /etc/opcode-learn/learn.env")
        to = [a.to] if a.to else web.trainer_emails()
        mailer.ASYNC = False
        status = mailer.send(to, "Test from %s" % config.SITE_NAME,
                             "This is a test email from %s (%s).\nIf you read this, email works.\n"
                             % (config.SITE_NAME, config.BASE_URL))
        print("%s via %s:%d as %s -> %s" % (", ".join(to), config.SMTP_HOST, config.SMTP_PORT, config.MAIL_FROM, status))
        return 0 if status == "sent" else 1

    with store.db() as c:
        if a.cmd == "list":
            for u in c.execute("SELECT * FROM users ORDER BY is_admin DESC, email"):
                print("%-6s %-40s %s" % ("admin" if u["is_admin"] else "", u["email"],
                                         "disabled" if u["disabled"] else ""))
            return 0
        u = store.user_by_email(c, a.email)
        if a.cmd == "create-admin":
            if u:
                sys.exit("%s already exists" % a.email)
            pw = ask_password()
            secret = security.new_totp_secret()
            store.create_user(c, a.email, is_admin=True, pw_hash=security.hash_password(pw), totp_secret=secret)
            show_totp(a.email, secret)
            print("Admin created. Sign in at %s/login" % config.BASE_URL)
            return 0
        if not u or not u["is_admin"]:
            sys.exit("no admin with this email")
        if a.cmd == "new-totp":
            secret = security.new_totp_secret()
            c.execute("UPDATE users SET totp_secret = ?, totp_step = 0 WHERE id = ?", (secret, u["id"]))
            c.execute("DELETE FROM sessions WHERE user_id = ?", (u["id"],))
            show_totp(a.email, secret)
            print("Old key no longer works.")
        elif a.cmd == "set-password":
            c.execute("UPDATE users SET pw_hash = ? WHERE id = ?", (security.hash_password(ask_password()), u["id"]))
            c.execute("DELETE FROM sessions WHERE user_id = ?", (u["id"],))
            print("Password changed; all sessions signed out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
