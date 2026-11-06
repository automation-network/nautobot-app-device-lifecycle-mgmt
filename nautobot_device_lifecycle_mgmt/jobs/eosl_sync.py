"""Import hardware notices for existing devices from EOSL.ai."""

import json
import re
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import urlparse

from django.db import transaction
from nautobot.apps.jobs import BooleanVar, ChoiceVar, Job, ObjectVar
from nautobot.dcim.models import Device, DeviceType, Manufacturer
from requests import Session

from nautobot_device_lifecycle_mgmt.eosl import matching_groups, normalize_identifier, notice_defaults
from nautobot_device_lifecycle_mgmt.models import HardwareLCM

name = "Hardware Lifecycle Imports"  # pylint: disable=invalid-name
FAMILIES_URL = "https://eosl.ai/api/v1/families.json"
LOCAL_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "epsl"


def read_local_json(url):
    """Map EOSL API URLs to bundled snapshots, without accessing the network."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "eosl.ai" or parsed.query or parsed.fragment:
        raise ValueError(f"Unexpected EOSL API URL: {url}")
    if parsed.path == "/api/v1/families.json":
        relative_path = Path("families.json")
    elif re.fullmatch(r"/api/v1/family/[a-z0-9][a-z0-9-]*\.json", parsed.path):
        relative_path = Path("family") / parsed.path.rsplit("/", 1)[1]
    else:
        raise ValueError(f"Unexpected EOSL API path: {parsed.path}")
    path = LOCAL_DATA_DIR / relative_path
    if not path.resolve().is_relative_to(LOCAL_DATA_DIR.resolve()):
        raise ValueError("Local EOSL file must remain inside the bundled data directory")
    try:
        with path.open(encoding="utf-8-sig") as stream:
            return json.load(stream)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Missing local EOSL snapshot: {path}. Add it to the app before running.") from exc


def fetch_json(session, url):
    """Fetch only EOSL.ai API URLs, with a timeout and without redirects."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "eosl.ai" or not parsed.path.startswith("/api/v1/"):
        raise ValueError(f"Unexpected EOSL API URL: {url}")
    response = session.get(url, timeout=(10, 60), allow_redirects=False)
    response.raise_for_status()
    if response.is_redirect:
        raise ValueError("Unexpected EOSL API redirect")
    return response.json()


class EoslHardwareNoticeSync(Job):
    """Create missing hardware notices using exact vendor and SKU matches."""

    source = ChoiceVar(
        choices=(("api", "EOSL.ai API"), ("local", "Bundled local JSON files")),
        default="api",
        description="Read live API data or JSON snapshots bundled in the app's data/epsl directory.",
    )
    manufacturer = ObjectVar(model=Manufacturer, required=False, description="Optional manufacturer filter.")
    dry_run = BooleanVar(default=True, description="Preview matches without creating Hardware Notices.")

    class Meta:
        """Job metadata."""

        name = "EOSL.ai - Import Hardware Notices"
        description = "Create missing Hardware Notices for device types used by existing devices."
        has_sensitive_variables = False
        soft_time_limit = 3600

    def run(self, manufacturer=None, dry_run=True, source="api"):  # pylint: disable=arguments-differ, too-many-locals
        """Collect exact matches before creating any notices; preserve existing data."""
        if source not in ("api", "local"):
            raise ValueError("Source must be 'api' or 'local'")
        device_types = DeviceType.objects.filter(pk__in=Device.objects.values("device_type_id"))
        if manufacturer is not None:
            device_types = device_types.filter(manufacturer=manufacturer)
        device_types = list(device_types.select_related("manufacturer"))
        existing = set(HardwareLCM.objects.values_list("device_type_id", flat=True))
        targets = [device_type for device_type in device_types if device_type.pk not in existing]
        if not targets:
            self.logger.info("No device types need Hardware Notices.")
            return

        vendors = {normalize_identifier(device_type.manufacturer.name) for device_type in targets}
        matches = {device_type.pk: [] for device_type in targets}
        family_urls = {device_type.pk: set() for device_type in targets}
        self.logger.info("Reading EOSL data from %s", source)
        with Session() if source == "api" else nullcontext() as session:
            def load_json(url):
                return fetch_json(session, url) if source == "api" else read_local_json(url)

            payload = load_json(FAMILIES_URL)
            if not isinstance(payload, dict) or not isinstance(payload.get("families"), list):
                raise ValueError("EOSL families response must contain a families list")
            visited = set()
            for summary in payload["families"]:
                vendor = normalize_identifier(summary.get("vendor"))
                if vendor not in vendors or summary["detail"] in visited:
                    continue
                visited.add(summary["detail"])
                family = load_json(summary["detail"])
                if normalize_identifier(family.get("vendor")) != vendor:
                    raise ValueError("EOSL family vendor does not match its summary")
                for device_type in targets:
                    if normalize_identifier(device_type.manufacturer.name) != vendor:
                        continue
                    groups = matching_groups(family, device_type.model, device_type.part_number)
                    matches[device_type.pk].extend(groups)
                    if groups:
                        family_urls[device_type.pk].add(family["url"])

        created = 0
        for device_type in targets:
            try:
                defaults = notice_defaults(matches[device_type.pk])
            except ValueError as exc:
                self.logger.warning("Skipping %s: %s", device_type, exc)
                continue
            defaults["documentation_url"] = sorted(family_urls[device_type.pk])[0]
            defaults["comments"] += "\nEOSL families: " + ", ".join(sorted(family_urls[device_type.pk]))
            defaults["comments"] += f"\nImport source: {source}"
            notice = HardwareLCM(device_type=device_type, **defaults)
            if dry_run:
                notice.full_clean()
                self.logger.info("Would create Hardware Notice for %s: %s", device_type, defaults)
                continue
            # Lock the device type so simultaneous runs cannot create duplicate notices.
            with transaction.atomic():
                DeviceType.objects.select_for_update().get(pk=device_type.pk)
                if HardwareLCM.objects.filter(device_type=device_type).exists():
                    self.logger.info("Preserving existing Hardware Notice for %s", device_type)
                    continue
                notice.validated_save()
                created += 1
            self.logger.info("Created Hardware Notice for %s", device_type)
        self.logger.info("Finished: %d notices created; preview=%s.", created, dry_run)
