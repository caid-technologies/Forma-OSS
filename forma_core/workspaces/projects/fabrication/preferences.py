"""Account-owned printer preferences; never executable paths or raw slicer flags."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


PrinterId = Literal["creality_ender_3_04", "bambu_a1_04"]
DEFAULT_PRINTER_ID: PrinterId = "creality_ender_3_04"


class FabricationPreferenceUpdate(BaseModel):
    """Select one reviewed printer/material/process bundle for the account.

    The current catalog intentionally fixes PLA, a 0.4 mm nozzle and the
    printer's standard process. User data cannot select server executables,
    arbitrary profile files, start/end G-code, or command-line arguments.
    """

    model_config = ConfigDict(extra="forbid")
    printer_id: PrinterId
