from __future__ import annotations

from .kill_switch import KillSwitch

# Prozess-weiter Singleton — wird von gateway und router geteilt
instance: KillSwitch = KillSwitch()
