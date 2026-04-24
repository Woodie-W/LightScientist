The current event is a background worker event.

Treat background as an intentional suspension for external progress, not as failure or stall.
Do not immediately resume the worker unless files/logs show concrete new information that the worker can use.
Inspect artifacts or logs first, then decide whether to wait, resume the worker with concrete findings, or cancel it.
If the worker should continue later without another supervisor decision, call schedule_worker_resume(agent_id, seconds, message) with the exact future message to send to that worker.
