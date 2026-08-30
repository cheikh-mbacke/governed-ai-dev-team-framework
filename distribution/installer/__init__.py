"""Distribution installer — Installation Record v2 and v1→v2 migration."""

from distribution.installer.migrate_v1_v2 import (
    MigrationError,
    MigrationResult,
    ensure_installation_record_v2,
    migrate_v1_to_v2,
)
from distribution.installer.record import (
    INSTALLATION_RECORD_FILE,
    LEGACY_VERSION_FILE,
    is_v1_manifest,
    is_v2_record,
    load_installation_record,
    managed_files_union,
    read_installation_manifest,
)

__all__ = [
    "INSTALLATION_RECORD_FILE",
    "LEGACY_VERSION_FILE",
    "MigrationError",
    "MigrationResult",
    "ensure_installation_record_v2",
    "is_v1_manifest",
    "is_v2_record",
    "load_installation_record",
    "managed_files_union",
    "migrate_v1_to_v2",
    "read_installation_manifest",
]
