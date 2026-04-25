The current event is a stalled worker event.

Stalled means a running worker has not shown progress for a while.
Inspect its files and logs before deciding whether to resume it, schedule a later check, cancel it, or start another worker.
Prefer resuming or scheduling over cancelling if the worker may still be useful.
Do not start a replacement worker unless the existing worker cannot reasonably continue.
