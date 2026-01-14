# app.py
from __future__ import annotations

from dataclasses import dataclass

from config import settings
from storage import store
from services.http import http

# These will exist after we paste them in next steps
# from services.standings import StandingsService
# from services.teams import TeamsService
# from services.permissions import PermissionsService
# from services.scheduling import SchedulingService


@dataclass
class App:
    settings: object = settings
    store: object = store
    http: object = http

    # services:
    # teams: TeamsService = None
    # standings: StandingsService = None
    # permissions: PermissionsService = None
    # scheduling: SchedulingService = None


app = App()
