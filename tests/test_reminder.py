from copy import deepcopy
import uuid
from datetime import datetime, timedelta, time
import pytest
from unittest.mock import patch, MagicMock

# from . import app

def get_reminder(app):
    with app.app_context():
        from rock_server.projects.irregular_reminders.Reminder import Reminder
        return Reminder


# # Helper function to create a base reminder dictionary
# def create_reminder_dict():
#     return {
#         "id": TEST_UUID,
#         "version": 1,
#         "device_id": TEST_DEVICE_ID,
#         "title": "Test Reminder",
#         "message": "This is a test reminder",
#         "work_hours": ["09:00", "17:00"],
#         "work_days": [True, True, True, True, True, False, False],
#         "min_time": (datetime.now() + timedelta(hours=1)).isoformat(),
#         "max_time": (datetime.now() + timedelta(days=7)).isoformat(),
#         "dist": "uniform",
#         "dist_params": {},
#         "repeat": True,
#         "spacing_min": "1h",
#         "spacing_max": "24h"
#     }

class TestReminder:
    def test_serialization(self, app, examples, db):
        """Test serialization and deserialization of the reminder"""
        Reminder = get_reminder(app)
        data = examples['reminder_objs'][1].serialize()

        reminder = Reminder.from_db(data.values())

        # Check that all fields are present in the serialized output
        for field in db.execute("PRAGMA table_info(reminders)").fetchall():
            assert field[1] in data

        # Check that the ID is preserved
        assert str(reminder.id) == str(examples['reminder_objs'][1].id)
        assert reminder.version == examples['reminder_objs'][1].version
        assert str(reminder.device_id) == str(examples['reminder_objs'][1].device_id)
        assert reminder.title == examples['reminder_objs'][1].title
        assert reminder.message == examples['reminder_objs'][1].message
        assert reminder.work_hours_start == examples['reminder_objs'][1].work_hours_start
        assert reminder.work_hours_end == examples['reminder_objs'][1].work_hours_end
        assert reminder.work_days == examples['reminder_objs'][1].work_days
        assert reminder.min_time == examples['reminder_objs'][1].min_time
        assert reminder.max_time == examples['reminder_objs'][1].max_time
        assert reminder.dist == examples['reminder_objs'][1].dist
        assert reminder.dist_params == examples['reminder_objs'][1].dist_params
        assert reminder.repeat == examples['reminder_objs'][1].repeat
        assert reminder.spacing_min == examples['reminder_objs'][1].spacing_min
        assert reminder.spacing_max == examples['reminder_objs'][1].spacing_max
        assert reminder.alive == examples['reminder_objs'][1].alive
        assert reminder.last_trigger_time == examples['reminder_objs'][1].last_trigger_time
        assert reminder.next_trigger_time == examples['reminder_objs'][1].next_trigger_time
        assert reminder == examples['reminder_objs'][1]

        assert type(reminder.work_hours_start) == type(examples['reminder_objs'][1].work_hours_start), f"Expected {type(examples['reminder_objs'][1].work_hours_start)}, got {type(reminder.work_hours_start)}"
        assert type(reminder.work_hours_end) == type(examples['reminder_objs'][1].work_hours_end), f"Expected {type(examples['reminder_objs'][1].work_hours_end)}, got {type(reminder.work_hours_end)}"

    def test_create_reminder_with_minimal_fields(self, app, examples):
        """Test creating a reminder with only required fields"""
        Reminder = get_reminder(app)
        data = {
            "id": uuid.uuid4(),
            "version": 1,
            "device_id": examples['devices'][0]['device_id'],
            "title": "Minimal Reminder",
            "message": "Minimal test",
            "dist": "uniform",
            "min_time": (datetime.now() + timedelta(hours=1)).isoformat(),
            "max_time": (datetime.now() + timedelta(days=7)).isoformat(),
        }
        reminder = Reminder(**data)
        assert reminder.title == "Minimal Reminder"
        assert reminder.dist == Reminder.Distribution.UNIFORM
        assert reminder.repeat is False  # Default value

    def test_work_hours_validation(self, app, examples):
        """Test work_hours validation"""
        Reminder = get_reminder(app)
        data = examples['reminder_objs'][0].serialize()

        # Test invalid work_hours (end before start)
        data["work_hours_start"] = "17:00"
        data["work_hours_end"] = "09:00"
        with pytest.raises(ValueError, match="work_hours must be in order"):
            Reminder.from_db(data.values())

        # Test valid work_hours
        data["work_hours_start"] = "09:00"
        data["work_hours_end"] = "17:00"
        reminder = Reminder.from_db(data.values())
        assert reminder.work_hours_start == time(9)
        assert reminder.work_hours_end == time(17)

    def test_work_days_validation(self, app, examples):
        """Test work_days validation"""
        Reminder = get_reminder(app)
        data = examples['reminder_objs'][0].serialize()

        # TODO:
        # Test empty work_days
        # data["work_days"] = ''
        # with pytest.raises(ValueError, match="work_days must not be empty"):
        #     Reminder.from_db(data.values())

        # Test valid work_days
        data["work_days"] = '1,0,1,0,1,0,0'
        reminder = Reminder.from_db(data.values())
        assert reminder.work_days == [True, False, True, False, True, False, False]

    def test_timedelta_parsing(self, app):
        """Test parsing of timedelta strings"""
        Reminder = get_reminder(app)
        # Test various valid formats
        test_cases = [
            ("1h", timedelta(hours=1)),
            ("30m", timedelta(minutes=30)),
            ("2d 3h 15m", timedelta(days=2, hours=3, minutes=15)),
            ("1y 6mo", timedelta(days=365 + 180)),  # Approximate
            ("1h 30m 45s", timedelta(hours=1, minutes=30, seconds=45)),
        ]

        for time_str, expected in test_cases:
            result = Reminder.cast_timedelta(time_str)
            assert result == expected, f"Failed for {time_str}"

        # Test invalid formats
        invalid_cases = [
            "",  # Empty string
            "1x",  # Invalid unit
            "1h 2x",  # Mixed valid and invalid
            "abc",  # No numbers
            "1h 2h 3h",  # Repeating units
        ]

        for time_str in invalid_cases:
            with pytest.raises(ValueError):
                print(time_str)
                Reminder.cast_timedelta(time_str)

    # TODO:
    def test_distribution_validation(self, app, examples):
        """Test distribution-specific validation"""
        return
        Reminder = get_reminder(app)
        data = examples['reminder_objs'][0]

        # Test UNIFORM distribution (requires min_time and max_time)
        data["dist"] = "uniform"
        data.pop("min_time", None)
        with pytest.raises(ValueError, match="min_time and max_time must be provided for UNIFORM distribution"):
            Reminder.from_db(data.values())

        # Test NORMAL distribution (requires mean and std)
        data["dist"] = "normal"
        data["dist_params"] = {"mean": "1h"}  # Missing std
        with pytest.raises(ValueError, match="mean and std must be provided for NORMAL distribution"):
            Reminder.from_db(data.values())

        # Test EXPONENTIAL distribution (requires mean)
        data["dist"] = "exponential"
        data["dist_params"] = {}  # Missing mean
        with pytest.raises(ValueError, match="mean must be provided for EXPONENTIAL distribution"):
            Reminder.from_db(data.values())

    def test_from_db(self, app, db, examples):
        """Test creating a reminder from a database row"""
        Reminder = get_reminder(app)
        # Mock a database row (tuple with values in the order of the columns)
        # db_row = (
        #     examples['reminders'][0]['id'],  # id
        #     1,          # version
        #     "DB Reminder",  # title
        #     "From DB",  # message
        #     "09:00,17:00",  # work_hours
        #     "1,1,1,1,1,0,0",  # work_days
        #     (datetime.now() + timedelta(hours=1)).isoformat(),  # min_time
        #     (datetime.now() + timedelta(days=1)).isoformat(),   # max_time
        #     "uniform",  # dist
        #     "{}",       # dist_params (JSON string)
        #     True,       # repeat
        #     "1h",       # spacing_min
        #     "24h",      # spacing_max
        #     True,       # alive
        #     None,       # last_trigger_time
        #     None,       # next_trigger_time
        #     examples['devices'][0]['device_id'],  # device_id
        # )

        # reminder = Reminder.from_db(db_row)
        # assert reminder.title == "DB Reminder"
        # assert reminder.device_id == examples['devices'][0]['device_id']
        # assert reminder.dist == Reminder.Distribution.UNIFORM
        # assert reminder.work_days == [True] * 5 + [False] * 2, reminder.work_days

        # Now get one of the test ones preloaded in the test db to test extraction
        reminder = Reminder.from_db(db.execute("SELECT * FROM reminders WHERE device_id = ?", (examples['devices'][0]['device_id'],)).fetchone())
        assert reminder.title == examples['reminder_objs'][0].title
        assert reminder.device_id == examples['devices'][0]['device_id']
        assert reminder.dist == examples['reminder_objs'][0].dist
        assert reminder.work_days == examples['reminder_objs'][0].work_days
        assert reminder.min_time == examples['reminder_objs'][0].min_time
        assert reminder.max_time == examples['reminder_objs'][0].max_time
        assert reminder.dist_params == examples['reminder_objs'][0].dist_params
        assert reminder.repeat is examples['reminder_objs'][0].repeat
        assert reminder.spacing_min == examples['reminder_objs'][0].spacing_min
        assert reminder.spacing_max == examples['reminder_objs'][0].spacing_max
        assert reminder.alive is examples['reminder_objs'][0].alive
        assert reminder.last_trigger_time is examples['reminder_objs'][0].last_trigger_time
        assert reminder.next_trigger_time == examples['reminder_objs'][0].next_trigger_time

    def test_trigger_time_sampling(self, app, examples):
        """Test that next_trigger_time is set correctly"""
        for reminder in examples['reminder_objs']:
            assert reminder.next_trigger_time is not None
            if reminder.min_time is not None:
                assert reminder.next_trigger_time > reminder.min_time
            if reminder.max_time is not None:
                assert reminder.next_trigger_time < reminder.max_time
            assert reminder.can_trigger(reminder.next_trigger_time) == reminder.alive

    def test_reminder_equality(self, app, examples):
        """Test that reminders with the same ID are considered equal"""
        reminder1 = examples['reminder_objs'][0]
        reminder2 = deepcopy(examples['reminder_objs'][0])

        # Same ID, different title
        reminder2.title = "Different Title"

        assert reminder1 == reminder2

        # Different ID
        reminder2.id = str(uuid.uuid4())
        assert reminder1 != reminder2
