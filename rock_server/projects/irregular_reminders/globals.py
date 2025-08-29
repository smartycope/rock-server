DATABASE = "reminders.db"

# The next reminder to trigger, None if there are no reminders
# This isn't specific to a specific device, this goes for all of them
# This needs to be a multi-file global because it's used to communicate in both
# the main thread and the reminder thread
next_reminder = None