"""Nautobot Jobs for the Device Lifecycle app."""

from nautobot.apps.jobs import register_jobs

from .cve_tracking import GenerateVulnerabilities, NistCveSyncSoftware
from .eosl_sync import EoslHardwareNoticeSync
from .lifecycle_reporting import (
    DeviceHardwareNoticeFullReport,
    DeviceSoftwareValidationFullReport,
    InventoryItemSoftwareValidationFullReport,
)
from .model_migration import DLMToNautobotCoreModelMigration

jobs = [
    EoslHardwareNoticeSync,
    DeviceHardwareNoticeFullReport,
    DeviceSoftwareValidationFullReport,
    InventoryItemSoftwareValidationFullReport,
    GenerateVulnerabilities,
    DLMToNautobotCoreModelMigration,
    NistCveSyncSoftware,
]
register_jobs(*jobs)
