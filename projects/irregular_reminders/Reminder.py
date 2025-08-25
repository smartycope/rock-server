"""
A complex, non-standard Reminder class. This file is versioned (incrementally), becuase it gets
copied verbatim between the server and client.
"""
from datetime import datetime, timedelta, time
import sqlite3
from enum import Enum
import random
import enum
from typing import Literal
import uuid



class Reminder:
    """ A complex, non-standard reminder with many parameters
        Does not trigger itself.
    """
    __version__ = 2
    __last_modified_by__ = "single file"

    @enum.unique
    class Distribution(Enum):
        UNIFORM = random.uniform
        NORMAL = random.normalvariate
        EXPONENTIAL = random.expovariate

    def __init__(
        self,
        title,
        message,
        trigger_work_hours: tuple[time, time] | None = None,
        trigger_work_days: list[int] = [0, 1, 2, 3, 4, 5, 6],
        trigger_min_time: datetime | None = None,
        trigger_max_time: datetime | None = None,
        trigger_dist: Distribution = Distribution.UNIFORM,
        trigger_dist_params: dict = {},
        repeat: bool = False,
        spacing_min: timedelta | None = timedelta(seconds=1),
        spacing_max: timedelta | None = None,
        spacing_dist: Distribution | None = Distribution.UNIFORM,
        spacing_dist_params: dict | None = {},
        id=None,
    ):
        """
        Initialize a new reminder
        To initialize an existing reminder, use Reminder.deserialize()

        If trigger_dist is UNIFORM, trigger_dist_params are auto-set to a = trigger_min_time and b = trigger_max_time.
        Any given trigger_dist_params will be ignored, and trigger_min_time and trigger_max_time must be provided.

        Otherwise, trigger_dist/_params behave as expected, but are optionally bounded by
        trigger_min_time and trigger_max_time.

        Same goes for spacing_dist/_params and spacing_min and spacing_max.

        NORMAL takes mean (datetime) and std (float) as parameters.
        EXPONENTIAL takes mean (timedelta) as a parameter (lambda = 1/mean, for example,
        wait at least trigger_min_time, and then wait on average mean amount of time before going off)

        """
        self.title = title
        self.message = message
        self.id = uuid.uuid4() if id is None else id
        self.alive = trigger_max_time is None or trigger_max_time > datetime.now()
        # the last time it went off - None for hasn't yet
        self.last_trigger_time: datetime | None = None

        # Parameters
        # period of the day when the alarm is allowed to trigger
        self.trigger_work_hours: tuple[time, time] | None = trigger_work_hours
        # day of the week it's allowed to go off (Monday is 0, Sunday is 6 (to be compliant with datetime.weekday()))
        self.trigger_work_days: list[int] = trigger_work_days
        # min/max timedelta from now of the window when it should go off
        self.trigger_min_time: datetime | None = trigger_min_time
        self.trigger_max_time: datetime | None = trigger_max_time
        # statistical distrobution describing when within that window it should go off
        self.trigger_dist: Reminder.Distribution = trigger_dist
        self.trigger_dist_params: dict = trigger_dist_params
        # if it should go off repeatedly or not
        self.repeat: bool = repeat

        # min/max amount of time it should wait before going off again
        self.spacing_min: timedelta | None = spacing_min if self.repeat else None
        self.spacing_max: timedelta | None = spacing_max if self.repeat else None

        # statistical distrobution describing when within that window it should go off
        self.spacing_dist: Reminder.Distribution | None = spacing_dist if self.repeat else None
        self.spacing_dist_params: dict | None = (
            spacing_dist_params if self.repeat else None
        )

        self.validate_params()
        # Deterministically sample the next trigger time
        self.next_trigger_time: datetime | None = self.sample_trigger_time(trigger=True)

    def validate_params(self):
        if self.trigger_dist == Reminder.Distribution.UNIFORM and (self.trigger_min_time is None or self.trigger_max_time is None):
            raise ValueError("trigger_min_time and trigger_max_time must be provided for UNIFORM distribution")
        if self.trigger_dist == Reminder.Distribution.NORMAL and ('mean' not in self.trigger_dist_params or 'std' not in self.trigger_dist_params):
            raise ValueError("mean and std must be provided for NORMAL distribution")
        if self.trigger_dist == Reminder.Distribution.EXPONENTIAL and 'mean' not in self.trigger_dist_params:
            raise ValueError("mean must be provided for EXPONENTIAL distribution")
        if not len(self.trigger_work_days):
            raise ValueError("trigger_work_days must not be empty")
        for day in self.trigger_work_days:
            if day < 0 or day > 6:
                raise ValueError("trigger_work_days must be between 0 and 6")
        if self.trigger_work_hours and (self.trigger_work_hours[0] > self.trigger_work_hours[1]):
            raise ValueError("trigger_work_hours must be in order")
        if self.trigger_min_time and self.trigger_max_time and self.trigger_min_time > self.trigger_max_time:
            raise ValueError("trigger_min_time must be before trigger_max_time")
        if self.spacing_min and self.spacing_max and self.spacing_min > self.spacing_max:
            raise ValueError("spacing_min must be before spacing_max")
        if self.spacing_dist == Reminder.Distribution.UNIFORM and (self.spacing_min is None or self.spacing_max is None):
            raise ValueError("spacing_min and spacing_max must be provided for UNIFORM distribution")
        try:
            if self.spacing_dist == Reminder.Distribution.NORMAL and ('mean' not in self.spacing_dist_params or 'std' not in self.spacing_dist_params):
                raise ValueError("mean and std must be provided for NORMAL distribution")
            if self.spacing_dist == Reminder.Distribution.EXPONENTIAL and 'mean' not in self.spacing_dist_params:
                raise ValueError("mean must be provided for EXPONENTIAL distribution")
        except TypeError as e:
            raise ValueError("Please provide valid spacing_dist_params for spacing_dist") from e

    def serialize(self):
        return {
            # Simply incrementally versioned. This is different from the file version
            "version": 1,
            "title": self.title,
            "message": self.message,
            "trigger_work_hours": self.trigger_work_hours,
            "trigger_min_time": self.trigger_min_time,
            "trigger_max_time": self.trigger_max_time,
            "trigger_dist": self.trigger_dist,
            "trigger_dist_params": self.trigger_dist_params,
            "trigger_work_days": self.trigger_work_days,
            "repeat": self.repeat,
            "spacing_min": self.spacing_min,
            "spacing_max": self.spacing_max,
            "spacing_dist": self.spacing_dist,
            "spacing_dist_params": self.spacing_dist_params,
            "id": self.id,
            "next_trigger_time": self.next_trigger_time,
            "last_trigger_time": self.last_trigger_time,
            "alive": self.alive,
        }

    @staticmethod
    def deserialize(data):
        # this is the only currently supported version
        if data['version'] != 1:
            raise ValueError("Invalid version")
        rtn = Reminder(
            title=data["title"],
            message=data["message"],
            trigger_work_hours=data["trigger_work_hours"],
            trigger_min_time=data["trigger_min_time"],
            trigger_max_time=data["trigger_max_time"],
            trigger_dist=data["trigger_dist"],
            trigger_dist_params=data["trigger_dist_params"],
            trigger_work_days=data["trigger_work_days"],
            repeat=data["repeat"],
            spacing_min=data["spacing_min"],
            spacing_max=data["spacing_max"],
            spacing_dist=data["spacing_dist"],
            spacing_dist_params=data["spacing_dist_params"],
            id=data["id"],
        )
        rtn.alive = data['alive']
        rtn.next_trigger_time = data["next_trigger_time"]
        rtn.last_trigger_time = data["last_trigger_time"]
        rtn.validate_params()
        return rtn

    def _trigger(self):
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
            self.next_trigger_time = self.sample_trigger_time(trigger=False)
        return True

    def can_trigger(self, now: datetime = None):
        if now is None:
            now = datetime.now()
        # trigger_work_hours
        if self.trigger_work_hours and not (
            self.trigger_work_hours[0] <= now.time() <= self.trigger_work_hours[1]
        ):
            return False

        # trigger_work_days
        if self.trigger_work_days and now.weekday() not in self.trigger_work_days:
            return False

        # trigger_min_time/max
        if self.trigger_min_time and now < self.trigger_min_time:
            return False
        # This should never happen, but we still want to check it
        if self.trigger_max_time and now > self.trigger_max_time:
            return False

        # spacing_min/max
        if self.spacing_min and now < self.spacing_min:
            return False
        # This should never happen, but we still want to check it
        if self.spacing_max and now > self.spacing_max:
            return False

        return True

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
            if self.trigger_min_time and next_time < self.trigger_min_time:
                next_time = self.trigger_min_time
            if self.trigger_max_time and next_time >= self.trigger_max_time:
                return

            # Ensure it's within the spacing window
            if self.repeat and self.last_trigger_time:
                if self.spacing_min and next_time < self.spacing_min + self.last_trigger_time:
                    next_time = self.spacing_min + self.last_trigger_time
                if self.spacing_max and next_time >= self.spacing_max + self.last_trigger_time:
                    return

            # If it's not a work day, we need to wait until the next work day
            if ((self.trigger_work_days and next_time.weekday() not in self.trigger_work_days) or
                # Or, if it is a work day, but work hours have already been past, we still need to wait until the next work day
                (self.trigger_work_hours and next_time.time() >= self.trigger_work_hours[1])):
                # Reset the hour to the start of the next day
                next_time = (next_time + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                # Increment the day until it's a work day
                while next_time.weekday() not in self.trigger_work_days:
                    next_time += timedelta(days=1)

            # it's now a work day, but work hours haven't started yet
            if self.trigger_work_hours and next_time.time() < self.trigger_work_hours[0]:
                next_time = next_time.replace(
                    hour=self.trigger_work_hours[0].hour,
                    minute=self.trigger_work_hours[0].minute,
                    second=0,
                    microsecond=0,
                )

            if next_time > self.trigger_max_time or (self.repeat and self.last_trigger_time and next_time > self.spacing_max + self.last_trigger_time):
                return

            return next_time

    def sample_trigger_time(self, trigger=True, adj:Literal['next', 'resample']='next') -> datetime:
        """
        Generates the next time this reminder will go off

        adj: If we randomly select an invalid time, 'next' will adjust it to the next
            allowed time, 'resample' will keep resampling until it's valid

        Note: if the parameters are particularly poorly chosen (i.e. the trigger window is very small,
            and the mean of a distribution is very close to or outside of the window),
            this function may take a very long time to return
        """
        if trigger:
            dist = self.trigger_dist
            params = self.trigger_dist_params
        else:
            dist = self.spacing_dist
            params = self.spacing_dist_params

        sample = None
        while sample is None:
            # If sample is None, it means it's outside the bounds of the trigger window
            if adj == 'next':
                sample = self.next_allowed_time(datetime.now() + timedelta(
                    seconds=dist(**self._interpret_dist_params(dist, params, trigger))
                ))
            elif adj == 'resample':
                sample = datetime.now() + timedelta(
                    seconds=dist(**self._interpret_dist_params(dist, params, trigger))
                )
                if not self.can_trigger(sample):
                    sample = None
            else:
                raise ValueError(f"Invalid adj value: {adj}")
        return sample

    def _interpret_dist_params(self, dist:Distribution, params: dict, trigger:bool=True) -> dict:
        """ Interprets the distribution parameters based on the distribution type, and returns a dictionary of parameters for the correct function """
        min = self.trigger_min_time if trigger else self.spacing_min
        max = self.trigger_max_time if trigger else self.spacing_max

        match dist:
            case Reminder.Distribution.UNIFORM:
                return {
                    "a": (min - datetime.now()).total_seconds(),
                    "b": (max - datetime.now()).total_seconds(),
                }
            case Reminder.Distribution.NORMAL:
                return {
                    "mu": params['mean'].total_seconds(),
                    "sigma": params['std'],
                }
            case Reminder.Distribution.EXPONENTIAL:
                return {
                    "lambd": params['mean'].total_seconds(),
                }

    def __str__(self):
        return f"{self.title} - {self.message}"

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def trigger_if_ready(self) -> bool:
        """
        Triggers the reminder if it's supposed to be triggered right now
        Returns True if it was triggered, False otherwise
        """
        if (self.next_trigger_time - datetime.now()).total_seconds() <= 1:
            return self._trigger()
        return False

    def add_to_db(self, conn:sqlite3.Connection):
        """ Adds the reminder to the database """
        with conn.cursor() as cur:
            data = self.serialize()
            cur.execute(
                # Keys are guaranteed to be safe, values, probably, but let's not risk it
                f"INSERT INTO reminders {tuple(data.keys())} VALUES ({'?, ' * len(data)})",
                data.values()
            )
