"""Database helpers for MySQL."""

import mysql.connector

from core.config import MYSQL_CONFIG


def get_db():
    return mysql.connector.connect(**MYSQL_CONFIG)


def query_db(query, args=(), one=False):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute(query, args)
    result = cur.fetchone() if one else cur.fetchall()
    cur.close()
    db.close()
    return result


def execute_db(query, args=()):
    db = get_db()
    cur = db.cursor()
    cur.execute(query, args)
    db.commit()
    last_id = cur.lastrowid
    cur.close()
    db.close()
    return last_id
