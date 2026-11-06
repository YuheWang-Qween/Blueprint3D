"""Persistent accounts, opaque sessions and owner-scoped model jobs."""
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'studio.sqlite3'
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, hash TEXT NOT NULL, iterations INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, params TEXT NOT NULL, result TEXT, error TEXT);
            ''')
            db.execute("UPDATE jobs SET status='error', error='服务重启中断了任务，请重新生成。' WHERE status IN ('queued','running')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    @staticmethod
    def hash(password, salt, iterations):
        return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),iterations).hex()

    def register(self, username, password):
        salt=secrets.token_hex(16)
        uid=secrets.token_hex(16)
        digest=self.hash(password,salt,600_000)
        with self.connect() as db:
            try:
                db.execute('INSERT INTO users VALUES (?,?,?,?,?)',(uid,username,salt,digest,600_000))
            except sqlite3.IntegrityError:
                raise ValueError('这个用户名已注册，请直接登录。')
        return {'id':uid,'username':username}

    def verify(self, username, password):
        with self.connect() as db:
            row=db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
        salt=row['salt'] if row else '00'*16
        digest=self.hash(password,salt,row['iterations'] if row else 600_000)
        if not row or not hmac.compare_digest(digest,row['hash']):
            return None
        return {'id':row['id'],'username':row['username']}

    def session(self,user):
        token=secrets.token_urlsafe(40)
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user['id'],time.time()+604800))
        return token

    def user(self,token):
        if not token or len(token)>200:
            return None
        with self.connect() as db:
            row=db.execute('SELECT u.id,u.username FROM sessions s JOIN users u ON s.user_id=u.id WHERE s.token=? AND s.expires>?',
                           (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return dict(row) if row else None

    def logout(self,token):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256((token or '').encode()).hexdigest(),))

    def job(self,jid,user_id):
        with self.connect() as db:
            row=db.execute('SELECT * FROM jobs WHERE id=? AND user_id=?',(jid,user_id)).fetchone()
        return self.decode(row) if row else None

    @staticmethod
    def decode(row):
        data=dict(row)
        data.pop('user_id',None)
        for key in ['params','result']:
            data[key]=json.loads(data[key]) if data[key] else None
        return data

    def jobs(self,user_id):
        with self.connect() as db:
            rows=db.execute('SELECT * FROM jobs WHERE user_id=? ORDER BY created DESC LIMIT 40',(user_id,)).fetchall()
        return [self.decode(r) for r in rows]

    def add_job(self,jid,user_id,name,params):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            pending=db.execute("SELECT user_id FROM jobs WHERE status IN ('queued','running')").fetchall()
            if len(pending)>=8 or sum(r['user_id']==user_id for r in pending)>=2:
                raise ValueError('已有任务正在处理，请等待完成后再生成。')
            db.execute('INSERT INTO jobs (id,user_id,name,status,created,params) VALUES (?,?,?,?,?,?)',
                       (jid,user_id,name,'queued',time.time(),json.dumps(params)))

    def update_job(self,jid,status,result=None,error=None):
        with self.connect() as db:
            db.execute('UPDATE jobs SET status=?,result=?,error=? WHERE id=?',(status,json.dumps(result) if result else None,error,jid))
