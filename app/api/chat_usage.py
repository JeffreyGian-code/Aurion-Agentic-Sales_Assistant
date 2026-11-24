"""Daily session budgets, kept separately from the agent's conversation context."""

import json
import secrets
import math
import os
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path

from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

CALL_LIMIT = 7
TURN_TIMEOUT_SECONDS = 100
WINDOW_SECONDS = 24 * 60 * 60
DATABASE_PATH = os.getenv(
    "CHAT_USAGE_DATABASE", str(Path(__file__).resolve().parents[2] / ".chat-usage.sqlite3")
)


def connect():
    return sqlite3.connect(DATABASE_PATH, timeout=2)


def initialize(db):
    db.execute("CREATE TABLE IF NOT EXISTS chat_usage (session_id TEXT PRIMARY KEY, calls INTEGER, resets_at REAL, thread_id TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS conversations (session TEXT PRIMARY KEY, history TEXT DEFAULT '[]', lease TEXT, expires REAL)")
    db.execute("CREATE TABLE IF NOT EXISTS owners (session TEXT PRIMARY KEY, secret TEXT NOT NULL UNIQUE)")
    db.execute("CREATE TABLE IF NOT EXISTS receipts (session TEXT, turn TEXT, message TEXT, reset INTEGER, reply TEXT, PRIMARY KEY(session,turn))")


def budget(db, session_id, consume, reset_context):
    now = time.time()
    row = db.execute("SELECT calls, resets_at, thread_id FROM chat_usage WHERE session_id = ?", (session_id,)).fetchone()
    calls, resets_at, thread_id = row or (0, now + WINDOW_SECONDS, session_id)
    if resets_at <= now:
        calls, resets_at = 0, now + WINDOW_SECONDS
    if consume:
        if calls >= CALL_LIMIT:
            raise HTTPException(
                status_code=429,
                headers={"X-Error-Code": "session-limit", "Retry-After": str(max(1, math.ceil(resets_at-now)))},
                detail="Your session has used all 7 calls. Your budget resets 24 hours after your first call; resetting the conversation does not renew it.",
            )
        if reset_context:
            thread_id = str(uuid.uuid4())
        calls += 1
        db.execute("INSERT OR REPLACE INTO chat_usage VALUES (?, ?, ?, ?)", (session_id, calls, resets_at, thread_id))
    return {"calls": calls, "limit": CALL_LIMIT, "resets_at": resets_at if calls else None, "thread_id": thread_id}

def session_usage(session_id, *, consume=False, reset_context=False):
    with closing(connect()) as db, db:
        initialize(db)
        if consume:
            db.execute("BEGIN IMMEDIATE")
        return budget(db, session_id, consume, reset_context)


def check_owner(db, session, secret):
    row = db.execute("SELECT secret FROM owners WHERE session=?", (session,)).fetchone()
    if not row or not secret or not secrets.compare_digest(row[0].encode(), secret.encode()):
        raise HTTPException(404, "This conversation has expired.", headers={"X-Error-Code": "session-expired"})


def owned_usage(session, secret):
    with closing(connect()) as db:
        initialize(db)
        check_owner(db, session, secret)
        return budget(db, session, False, False)


def begin(session, message, reset, turn, secret):
    with closing(connect()) as db, db:
        initialize(db)
        db.execute("BEGIN IMMEDIATE")
        if session is None and secret:
            owned = db.execute("SELECT session FROM owners WHERE secret=?", (secret,)).fetchone()
            session = owned[0] if owned else None
        if session is None:
            session = secrets.token_urlsafe(32)
            secret = secrets.token_urlsafe(32)
            db.execute("INSERT INTO owners VALUES (?,?)", (session, secret))
            db.execute("INSERT INTO conversations(session) VALUES (?)", (session,))
        check_owner(db, session, secret)
        row = db.execute("SELECT history, expires FROM conversations WHERE session=?", (session,)).fetchone()
        if row is None:
            raise HTTPException(404, "This conversation has expired.", headers={"X-Error-Code": "session-expired"})
        receipt = db.execute("SELECT message,reset,reply FROM receipts WHERE session=? AND turn=?", (session, turn)).fetchone()
        if receipt and (message, int(reset)) != receipt[:2]:
            raise HTTPException(409, "This request ID belongs to a different message.")
        if receipt and receipt[2] is not None:
            return session, None, [], receipt[2], session, secret
        if receipt and db.execute("SELECT turn FROM receipts WHERE session=? ORDER BY rowid DESC LIMIT 1", (session,)).fetchone()[0] != turn:
            raise HTTPException(409, "A newer turn has started. Send your question as a new message.")
        if row[1] and row[1] > time.time():
            raise HTTPException(409, "A reply is already in progress. Try again shortly.")
        usage = budget(db, session, receipt is None, reset)
        lease = uuid.uuid4().hex
        db.execute("UPDATE conversations SET lease=?, expires=? WHERE session=?", (lease, time.time() + TURN_TIMEOUT_SECONDS + 30, session))
        db.execute("INSERT OR IGNORE INTO receipts VALUES (?,?,?,?,NULL)", (session, turn, message, reset))
        return session, lease, [] if reset else json.loads(row[0]), None, usage["thread_id"], secret


def finish(session, lease, turn, history=None, reply=None):
    with closing(connect()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        if history is None:
            db.execute("UPDATE conversations SET lease=NULL,expires=NULL WHERE session=? AND lease=?", (session,lease))
            return
        updated = db.execute("UPDATE conversations SET history=?,lease=NULL,expires=NULL WHERE session=? AND lease=?",
                             (json.dumps(history),session,lease))
        if not updated.rowcount:
            raise HTTPException(409, "The request expired. Please retry.")
        db.execute("UPDATE receipts SET reply=? WHERE session=? AND turn=?", (reply,session,turn))


def check_storage():
    with closing(connect()) as db:
        initialize(db)
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO conversations(session) VALUES (?)", (uuid.uuid4().hex,))
        db.rollback()
