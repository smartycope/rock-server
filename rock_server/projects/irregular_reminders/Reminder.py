"""
A complex, non-standard Reminder class. This file is versioned (incrementally), becuase it gets
copied verbatim between the server and client.
"""
from datetime import datetime, timedelta, time
import sqlite3
from enum import Enum
import random
import enum
from typing import Literal, ClassVar
import uuid
from pydantic import field_validator, model_validator, BaseModel
import re

# Client reminders look like this:
"""
{
    id: "uuid",
    version: 1,
    title: "Title",
    message: "Message",
    alive: true,
    work_hours: ["00:00", "23:59"], <-- TODO: not sure
    work_days: [True, True, True, True, True, True, True],
    min_time: "2025-08-26T12:27:56", <-- TODO: not sure
    max_time: "2025-08-26T12:27:56",
    dist: "uniform",
    dist_params: {"mean": "1s 1m 1h 1d", "std": "1s 1m 1h 1d"}, # Mean is a time delta, because it's reusable for repeating
    repeat: true,
    spacing_min: "1s 1m 1h 1d",
    spacing_max: "1s 1m 1h 1d"
}
"""


class Reminder(BaseModel):
    """ A complex, non-standard reminder with many parameters
        Does not trigger itself.
    """
    # This is the code version of this class
    __version__ = 4

    @enum.unique
    class Distribution(Enum):
        UNIFORM = "uniform"
        NORMAL = "normal"
        EXPONENTIAL = "exponential"

    # This is the version of the reminder
    version: int
    id: uuid.UUID
    device_id: str
    title: str
    message: str
    # period of the day when the alarm is allowed to trigger
    work_hours: tuple[time, time] | None = None
    # day of the week it's allowed to go off (Monday is 0, Sunday is 6 (to be compliant with datetime.weekday()))
    work_days: list[bool] = [True] * 7
    # min/max timedelta from now of the window when it should go off
    min_time: datetime | None = None
    max_time: datetime | None = None
    # statistical distribution describing when within that window it should go off
    dist: Distribution = Distribution.UNIFORM
    dist_params: dict = {}
    # if it should go off repeatedly or not
    repeat: bool = False
    # min/max amount of time it should wait before going off again
    spacing_min: timedelta | None = timedelta(seconds=1)
    spacing_max: timedelta | None = None
    # whether it's alive or not - None means it's not initialized, and gets set in __init__
    alive: bool | None = None

    # Really, these are just members, not fields, but whatever
    # the last time it went off - None for hasn't yet
    last_trigger_time: datetime | None = None
    # This gets calcuated immediately in __init__
    next_trigger_time: datetime | None = None


    # Class variables
    timedelta_regex: ClassVar = re.compile(r'(?P<num>\d+)(?P<key>(?:mo|[ymhds]))(?:\s+)?')
    # If we're off by this much, we'll just trigger it anyway
    allowed_resolution_sec: ClassVar = 5
    dist_map: ClassVar = {
        Distribution.UNIFORM: random.uniform,
        Distribution.NORMAL: random.normalvariate,
        Distribution.EXPONENTIAL: random.expovariate,
    }

    def __init__(self, *args, **kwargs):
        """
        Initialize a new reminder
        To initialize an existing reminder, use Reminder.deserialize()

        Not to be instantiated directly - use Reminder.from_db() or Reminder.from_client()

        If dist is UNIFORM, dist_params are auto-set to a = min_time and b = max_time.
        Any given dist_params will be ignored, and min_time and max_time must be provided.

        Otherwise, dist/_params behave as expected, but are optionally bounded by
        min_time and max_time.

        Same goes for spacing_dist/_params and spacing_min and spacing_max.

        NORMAL takes mean (datetime) and std (float) as parameters.
        EXPONENTIAL takes mean (timedelta) as a parameter (lambda = 1/mean, for example,
        wait at least min_time, and then wait on average mean amount of time before going off)
        """
        super().__init__(*args, **kwargs)
        if self.alive is None:
            self.alive = self.max_time is None or self.max_time > datetime.now()

        self.next_trigger_time = self._sample_trigger_time()


    @field_validator("spacing_min", "spacing_max", mode="before")
    @classmethod
    def validate_spacing(cls, v):
        return cls.cast_timedelta(v)

    @staticmethod
    def cast_timedelta(v):
        """
        Thank you ezregex.org
        key = either('mo', anyof('ymdhs'))
        pattern = group(number, name='num') + group(key, name='key') + ow
        """
        try:
            # Remove any whitespace
            trimmed = re.sub(r'\s+', '', v)
            matches = Reminder.timedelta_regex.finditer(trimmed)
            # An empty string is invalid
            if v == "":
                raise ValueError("Invalid timedelta format (empty string)")
            # If there's no matches
            if not matches:
                raise ValueError("Invalid timedelta format (no matches)")

            prev_end = 0
            total = timedelta()
            for m in matches:
                num = int(m['num'])
                key = m['key']

                # If there's characters that arent in any of the matches (after removing whitespace)
                # Or if there's overlapping matches (!= instead of <)
                if m.start() != prev_end:
                    raise ValueError("Invalid timedelta format (overlapping or non-contiguous matches)")
                prev_end = m.end()

                match key:
                    case 'mo': total += timedelta(days=num * 30)
                    case 'y':  total += timedelta(days=num * 365)
                    case 'd':  total += timedelta(days=num)
                    case 'h':  total += timedelta(hours=num)
                    case 'm':  total += timedelta(minutes=num)
                    case 's':  total += timedelta(seconds=num)

            if prev_end != len(trimmed):
                raise ValueError("Invalid timedelta format (trailing characters)")

        except ValueError as e:
            raise e
        except Exception as e:
            raise ValueError("Invalid timedelta format (error parsing)") from e

        return total

    @model_validator(mode="after")
    def validate_params(self):
        if self.dist == Reminder.Distribution.UNIFORM and (self.min_time is None or self.max_time is None):
            raise ValueError("min_time and max_time must be provided for UNIFORM distribution")
        if self.dist == Reminder.Distribution.UNIFORM and self.dist_params:
            raise ValueError("dist_params must be empty for UNIFORM distribution. Specify min_time and max_time instead.")
        if self.dist == Reminder.Distribution.NORMAL and self.dist_params.keys() != {'mean', 'std'}:
            raise ValueError("mean and std must be provided for NORMAL distribution")
        if self.dist == Reminder.Distribution.EXPONENTIAL and self.dist_params.keys() != {'mean'}:
            raise ValueError("mean must be provided for EXPONENTIAL distribution")
        if not len(self.work_days):
            raise ValueError("work_days must not be empty")
        if self.work_hours and (self.work_hours[0] > self.work_hours[1]):
            raise ValueError("work_hours must be in order")
        if self.min_time and self.max_time and self.min_time > self.max_time:
            raise ValueError("min_time must be before max_time")
        if self.spacing_min and self.spacing_max and self.spacing_min > self.spacing_max:
            raise ValueError("spacing_min must be before spacing_max")

        # Validate & cast dist_params
        if self.dist != Reminder.Distribution.UNIFORM:
            self.dist_params['mean'] = self.cast_timedelta(self.dist_params['mean'])
        if self.dist == Reminder.Distribution.NORMAL:
            self.dist_params['std'] = self.cast_timedelta(self.dist_params['std'])

        return self

    def serialize(self):
        """ Serialize the reminder to a dictionary """
        return {
            "id": self.id,
            "device_id": self.device_id,
            # Simply incrementally versioned. This is different from the file version
            "version": 1,
            "title": self.title,
            "message": self.message,
            "work_hours": self.work_hours,
            "min_time": self.min_time,
            "max_time": self.max_time,
            "dist": self.dist,
            "dist_params": self.dist_params,
            "work_days": self.work_days,
            "repeat": self.repeat,
            "spacing_min": self.spacing_min,
            "spacing_max": self.spacing_max,
            "next_trigger_time": self.next_trigger_time,
            "last_trigger_time": self.last_trigger_time,
            "alive": self.alive,
        }

    @staticmethod
    def from_db(row):
        """ Deserialize from a database row """
        # I'm pretty sure this won't work
        print("I'm pretty sure this won't work")
        return Reminder(**row)

    # @staticmethod
    # def from_client(**data):
    #     """ Validate and deserialize from a client request. This will handle validation and casting """
    #     return Reminder(**data)

    def _trigger(self, conn:sqlite3.Connection):
        """
        Triggers the reminder. Doesn't actually do anything, except update the internal state.
        returns True if successful
        returns False if it's not allowed to trigger right now, due to constraints
        """
        if not self.can_trigger():
            return False
        self.last_trigger_time = datetime.now()
        if not self.repeat:
            self.alive = False
        else:
            self.next_trigger_time = self._sample_trigger_time()

        conn.execute(
            "UPDATE reminders SET last_trigger_time = ?, next_trigger_time = ?, alive = ? WHERE id = ?",
            (self.last_trigger_time, self.next_trigger_time, self.alive, self.id)
        )
        conn.commit()
        return True

    def can_trigger(self, now: datetime = None):
        if now is None:
            now = datetime.now()

        # trigger_work_hours
        if self.work_hours and not (
            self.work_hours[0] <= now.time() <= self.work_hours[1]
        ):
            return False

        # trigger_work_days
        if self.work_days and not self.work_days[now.weekday()]:
            return False

        # trigger_min_time/max
        if self.min_time and now < self.min_time:
            return False
        # This should never happen, but we still want to check it
        if self.max_time and now > self.max_time:
            return False

        # spacing_min/max
        if self.spacing_min and now < self.spacing_min:
            return False
        # This should never happen, but we still want to check it
        if self.spacing_max and now > self.spacing_max:
            return False

        return self.alive

    def next_allowed_time(self, now: datetime = None) -> datetime | None:
        """
        Returns the next time this reminder is allowed to trigger
        If it is not allowed to trigger, returns None
        Will not set self.alive.
        """
        if now is None:
            now = datetime.now()
        if self.can_trigger(now):
            return now
        else:
            next_time = now
            # Ensure it's within the trigger window
            if self.min_time and next_time < self.min_time:
                next_time = self.min_time
            if self.max_time and next_time >= self.max_time:
                return

            # Ensure it's within the spacing window
            if self.repeat and self.last_trigger_time:
                if self.spacing_min and next_time < self.spacing_min + self.last_trigger_time:
                    next_time = self.spacing_min + self.last_trigger_time
                if self.spacing_max and next_time >= self.spacing_max + self.last_trigger_time:
                    return

            # If it's not a work day, we need to wait until the next work day
            if ((self.work_days and not self.work_days[next_time.weekday()]) or
                # Or, if it is a work day, but work hours have already been past, we still need to wait until the next work day
                (self.work_hours and next_time.time() >= self.work_hours[1])):
                # Reset the hour to the start of the next day
                next_time = (next_time + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                # Increment the day until it's a work day
                while not self.work_days[next_time.weekday()]:
                    next_time += timedelta(days=1)

            # it's now a work day, but work hours haven't started yet
            if self.work_hours and next_time.time() < self.work_hours[0]:
                next_time = next_time.replace(
                    hour=self.work_hours[0].hour,
                    minute=self.work_hours[0].minute,
                    second=0,
                    microsecond=0,
                )

            if next_time > self.max_time or (self.repeat and self.last_trigger_time and next_time > self.spacing_max + self.last_trigger_time):
                return

            return next_time

    def _sample_trigger_time(self, adj:Literal['next', 'resample']='next') -> datetime:
        """
        Generates the next time this reminder will go off

        adj: If we randomly select an invalid time, 'next' will adjust it to the next
            allowed time, 'resample' will keep resampling until it's valid

        Note: if the parameters are particularly poorly chosen (i.e. the trigger window is very small,
            and the mean of a distribution is very close to or outside of the window),
            this function may take a very long time to return

        This is private, because we make modifications to the reminder in here, which don't get
        updated in the db. This is only allowed in the constructor.
        """
        sample = None
        while sample is None:
            # If sample is None, it means it's outside the bounds of the trigger window
            if adj == 'next':
                sample = self.next_allowed_time(datetime.now() + timedelta(
                    seconds=self.dist_map[self.dist](**self._interpret_dist_params())
                ))
            elif adj == 'resample':
                sample = datetime.now() + timedelta(
                    seconds=self.dist_map[self.dist](**self._interpret_dist_params())
                )
                if not self.can_trigger(sample):
                    sample = None
            else:
                raise ValueError(f"Invalid adj value: {adj}")
        return sample

    def _interpret_dist_params(self) -> dict:
        """ Interprets the distribution parameters based on the distribution type, and returns a dictionary of parameters for the correct function """
        match self.dist:
            case Reminder.Distribution.UNIFORM:
                return {
                    "a": (self.min_time - datetime.now()).total_seconds(),
                    "b": (self.max_time - datetime.now()).total_seconds(),
                }
            case Reminder.Distribution.NORMAL:
                return {
                    "mu": self.dist_params['mean'].total_seconds(),
                    "sigma": self.dist_params['std'].total_seconds(),
                }
            case Reminder.Distribution.EXPONENTIAL:
                return {
                    "lambd": self.dist_params['mean'].total_seconds(),
                }

    def trigger_if_ready(self, conn:sqlite3.Connection) -> bool:
        """
        Triggers the reminder if it's supposed to be triggered right now
        Returns True if it was triggered, False otherwise

        Because we modify the reminder, we need a db connection so we can update it automatically as well
        """
        if (self.next_trigger_time - datetime.now()).total_seconds() <= self.allowed_resolution_sec:
            return self._trigger(conn)
        return False

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

# Throw some tests together
if __name__ == "__main__":
    r = Reminder.from_client(dict(
        id=str(uuid.uuid4()),
        version=4,
        title="Test",
        message="This is a test",
        work_days=[True] * 7,
        work_hours=["09:00", "17:00"],
        min_time="2025-08-26T09:00:00",
        max_time="2025-08-26T17:00:00",
        dist='normal',
        dist_params={
            "mean": "5s",
            "std": "2y 3s",
        },
        repeat=True,
        spacing_min="2m",
        spacing_max="1mo 2d 3h 4m 5s",
    ))
    print(r.serialize())

    assert r.spacing_max == timedelta(days=32, hours=3, minutes=4, seconds=5)

    # TODO: test db deserialization
    # TODO: test sample_trigger_time
    # TODO: test trigger_if_ready
    # TODO: test next_allowed_time

    print('\033[32mAll tests passed!\033[0m')