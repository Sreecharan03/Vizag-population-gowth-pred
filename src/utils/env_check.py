"""Pre-flight environment checks.

Fail fast with a clear, actionable message before any real data operation —
never a vague downstream error. These checks only inspect local state
(installed drivers, env var presence); they never make a network call, so
they can't themselves distinguish "wrong credentials" from "read-only key" —
that's the storage backend's job (Part 0.5), using the AuthFailedError /
ReadOnlyKeyError types defined here.
"""

from __future__ import annotations

import os
from typing import Callable

REQUIRED_B2_CREDENTIAL_ENV_VARS = ("Backbaze-keyID", "Backbaze-applicationKey")


class EnvironmentCheckError(Exception):
    """Base class for all pre-flight environment check failures."""


class MissingDriverError(EnvironmentCheckError):
    """A required GDAL driver isn't registered in this environment."""


class NoCredentialsError(EnvironmentCheckError):
    """A required credential environment variable is missing entirely."""


class AuthFailedError(EnvironmentCheckError):
    """Credentials are present but B2 rejected them.

    Raised by the storage backend (Part 0.5) when it actually attempts a
    connection — never by this module, which only checks presence.
    """


class ReadOnlyKeyError(EnvironmentCheckError):
    """Credentials are present and valid, but scoped read-only, and a write
    was attempted.

    Raised by the storage backend (Part 0.5) — never by this module.
    """


def check_jp2_driver_available(extensions_provider: "Callable[[], dict] | None" = None) -> None:
    """Raise MissingDriverError unless GDAL's JP2OpenJPEG driver is
    registered — Sentinel-2 bands are .jp2 files, so this must pass before
    any Phase 3 read.

    `extensions_provider` defaults to rasterio's real driver table; tests
    inject a fake one to simulate a missing driver without touching the
    real GDAL build.
    """
    if extensions_provider is None:
        import rasterio

        extensions_provider = rasterio.drivers.raster_driver_extensions

    extensions = extensions_provider()
    driver = extensions.get("jp2")
    if driver != "JP2OpenJPEG":
        raise MissingDriverError(
            "GDAL build is missing the JP2OpenJPEG driver (required to read Sentinel-2 "
            ".jp2 bands). Install hint: reinstall rasterio with OpenJPEG support "
            "(pip install --force-reinstall rasterio), or use a GDAL build compiled "
            "with --with-openjpeg."
        )


def check_b2_credentials_present(env: dict | None = None) -> None:
    """Raise NoCredentialsError unless all required B2 credential env vars
    are set. Presence-only — never attempts a network call.
    """
    env = os.environ if env is None else env
    missing = [name for name in REQUIRED_B2_CREDENTIAL_ENV_VARS if not env.get(name)]
    if missing:
        raise NoCredentialsError(
            f"Missing required B2 credential environment variable(s): {missing}. "
            "Set them via Lightning Studio secrets or a local .env file — never commit them."
        )
