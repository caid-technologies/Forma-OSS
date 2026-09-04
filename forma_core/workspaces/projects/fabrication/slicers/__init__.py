"""Slicer backends."""

from forma_core.workspaces.projects.fabrication.slicers.base import SlicerAdapter
from forma_core.workspaces.projects.fabrication.slicers.cura import CuraSlicerAdapter

__all__ = ["CuraSlicerAdapter", "SlicerAdapter"]
