from . import app, DB
import sqlite3

def test_db(db):
    with sqlite3.connect(DB) as con:
        cursor = con.cursor()
        cursor.execute("SELECT * FROM reminders")
        reminders = cursor.fetchall()

        assert len(reminders) == 3

        cursor = con.cursor()
        cursor.execute("SELECT * FROM devices")
        devices = cursor.fetchall()

        assert len(devices) == 2

def test_examples(examples):
    assert len(examples['reminders']) == 3
    assert len(examples['devices']) == 2
    assert len(examples['reminder_objs']) == 3
    assert str(examples['reminder_objs'][0].id) == str(examples['reminders'][0]['id'])
    assert str(examples['reminder_objs'][-1].id) == str(examples['reminders'][-1]['id'])