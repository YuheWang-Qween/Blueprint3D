"""
auth.py - Local authentication and login window for the Forgeplan GUI
======================================================================
Stores local accounts (PBKDF2-hashed passwords in users.json next to this
file) and provides the blueprint-styled login window shown before the
main GUI opens.

Part of the Forgeplan pipeline.
"""

import hashlib
import hmac
import json
import os
import secrets
import threading

USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")

_PBKDF2_ITERATIONS = 200_000

_lock = threading.Lock()


def _load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_users(users):
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)
    os.replace(tmp, USERS_FILE)


def _hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _PBKDF2_ITERATIONS
    ).hex()


def register(username, password):
    """Create a local account. Returns (success, error_message)."""
    username = username.strip()
    if not username or not password:
        return False, "Username and password cannot be empty"
    if len(username) > 32:
        return False, "Username is too long (max 32 characters)"
    if len(password) < 6:
        return False, "Password must be at least 6 characters"
    with _lock:
        users = _load_users()
        if username in users:
            return False, "This username is already taken"
        salt = secrets.token_hex(16)
        users[username] = {"salt": salt, "hash": _hash_password(password, salt)}
        _save_users(users)
    return True, ""


def verify(username, password):
    """Check local credentials. Returns (success, error_message)."""
    username = username.strip()
    with _lock:
        users = _load_users()
    record = users.get(username)
    if record is None:
        return False, "Invalid username or password"
    if not hmac.compare_digest(record["hash"], _hash_password(password, record["salt"])):
        return False, "Invalid username or password"
    return True, ""


class LoginWindow:
    """Blueprint-styled login/registration window shown before the main GUI."""

    BLUEPRINT = '#10243E'
    PAPER = '#E8EEF5'
    BRASS = '#F2B441'
    BRASS_ACTIVE = '#F8C96B'
    FADED = '#5B7A9D'
    ERROR = '#E86A5E'
    FIELD = '#1B3552'

    def __init__(self, root, on_success):
        import tkinter as tk

        self.root = root
        self.on_success = on_success
        self.register_mode = False

        root.title("Forgeplan - Login")
        root.geometry("440x580")
        root.configure(bg=self.BLUEPRINT)
        root.resizable(False, False)

        outer = tk.Frame(root, bg=self.BLUEPRINT,
                         highlightbackground=self.FADED, highlightthickness=1)
        outer.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)
        frame = tk.Frame(outer, bg=self.BLUEPRINT,
                         highlightbackground=self.PAPER, highlightthickness=1)
        frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        content = tk.Frame(frame, bg=self.BLUEPRINT)
        content.pack(fill=tk.BOTH, expand=True, padx=36, pady=32)

        tk.Label(content, text="F O R G E P L A N", bg=self.BLUEPRINT, fg=self.PAPER,
                 font=('Helvetica', 20, 'bold')).pack(pady=(6, 2))
        tk.Label(content, text="2D FLOOR PLAN  \u2192  3D MODEL", bg=self.BLUEPRINT,
                 fg=self.FADED, font=('Helvetica', 9)).pack(pady=(0, 16))
        tk.Frame(content, bg=self.FADED, height=1).pack(fill=tk.X, pady=(0, 20))

        self.mode_label = tk.Label(content, text="Sign in to the drafting room",
                                   bg=self.BLUEPRINT, fg=self.PAPER,
                                   font=('Helvetica', 11, 'bold'))
        self.mode_label.pack(anchor='w', pady=(0, 14))

        def field_label(text):
            return tk.Label(content, text=text, bg=self.BLUEPRINT, fg=self.FADED,
                            font=('Helvetica', 9, 'bold'))

        def field_entry(textvariable, show=''):
            return tk.Entry(content, textvariable=textvariable, show=show,
                            bg=self.FIELD, fg=self.PAPER, insertbackground=self.PAPER,
                            relief=tk.FLAT, highlightthickness=1,
                            highlightbackground=self.FADED, highlightcolor=self.BRASS,
                            selectbackground=self.BRASS, selectforeground=self.BLUEPRINT,
                            font=('Helvetica', 11))

        field_label("USERNAME").pack(anchor='w')
        self.username_var = tk.StringVar()
        self.username_entry = field_entry(self.username_var)
        self.username_entry.pack(fill=tk.X, ipady=5, pady=(2, 12))

        field_label("PASSWORD").pack(anchor='w')
        self.password_var = tk.StringVar()
        self.password_entry = field_entry(self.password_var, '\u2022')
        self.password_entry.pack(fill=tk.X, ipady=5, pady=(2, 4))

        # Confirm field only visible in register mode; re-packed before the
        # status label so it keeps its position in the packing order.
        self.confirm_label = field_label("CONFIRM PASSWORD")
        self.confirm_var = tk.StringVar()
        self.confirm_entry = field_entry(self.confirm_var, '\u2022')

        self.status_label = tk.Label(content, text="", bg=self.BLUEPRINT, fg=self.ERROR,
                                     font=('Helvetica', 9))
        self.status_label.pack(anchor='w', pady=(6, 4))

        self.submit_btn = tk.Button(content, text="Sign in", command=self._submit,
                                    bg=self.BRASS, fg=self.BLUEPRINT,
                                    activebackground=self.BRASS_ACTIVE,
                                    activeforeground=self.BLUEPRINT,
                                    relief=tk.FLAT, font=('Helvetica', 10, 'bold'),
                                    cursor='hand2')
        self.submit_btn.pack(fill=tk.X, ipady=6, pady=(4, 10))

        self.switch_btn = tk.Button(content, text="No account yet?  Register",
                                    command=self._toggle_mode, bg=self.BLUEPRINT,
                                    fg=self.FADED, activebackground=self.BLUEPRINT,
                                    activeforeground=self.PAPER, relief=tk.FLAT,
                                    font=('Helvetica', 9, 'underline'), cursor='hand2')
        self.switch_btn.pack()

        # Enter submits; bound on the entries so the binding dies with them
        for field in (self.username_entry, self.password_entry, self.confirm_entry):
            field.bind('<Return>', lambda _event: self._submit())

        self.username_entry.focus_set()

    def _toggle_mode(self):
        self.register_mode = not self.register_mode
        if self.register_mode:
            self.mode_label.config(text="Create a new draftsman account")
            self.submit_btn.config(text="Register")
            self.switch_btn.config(text="Already have an account?  Sign in")
            self.root.geometry("440x660")
            self.confirm_label.pack(before=self.status_label, anchor='w', pady=(8, 0))
            self.confirm_entry.pack(before=self.status_label, fill='x', ipady=5, pady=(2, 4))
        else:
            self.mode_label.config(text="Sign in to the drafting room")
            self.submit_btn.config(text="Sign in")
            self.switch_btn.config(text="No account yet?  Register")
            self.root.geometry("440x580")
            self.confirm_entry.pack_forget()
            self.confirm_label.pack_forget()
            self.confirm_var.set("")
        self.status_label.config(text="")

    def _submit(self):
        username = self.username_var.get()
        password = self.password_var.get()
        if self.register_mode:
            if password != self.confirm_var.get():
                self.status_label.config(text="Passwords do not match")
                return
            ok, err = register(username, password)
        else:
            ok, err = verify(username, password)
        if not ok:
            self.status_label.config(text=err)
            return
        self.on_success(username.strip())
