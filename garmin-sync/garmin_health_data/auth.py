"""
Garmin Connect authentication module.

Handles OAuth token management with Garmin Connect, including Multi-Factor
Authentication (MFA) support. Supports both interactive (terminal) and non-interactive
(CI / environment variable) authentication flows.

CI / GitHub Actions:     Instead of email+password+MFA login on every run, paste the
contents of     ``garmin_tokens.json`` (produced by a one-time ``garmin auth`` on your
local machine) into a ``GARMIN_TOKEN_JSON`` GitHub secret. The pipeline     restores the
token file to disk and uses the same transparent token     refresh as local mode.
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import click
from garmin_health_data.garmin_client import GarminClient
from garmin_health_data.garmin_client import tokens as garmin_tokens


def _get_email_env() -> Optional[str]:
    """
    Return the Garmin email/username from environment variables.

    Checks ``GARMIN_EMAIL`` first, then ``GARMIN_USERNAME``.

    :return: Email or username string, or None.
    """
    return os.getenv("GARMIN_EMAIL") or os.getenv("GARMIN_USERNAME")


def _get_password_env() -> Optional[str]:
    """
    Return the Garmin password from environment variables.

    :return: Password string, or None.
    """
    return os.getenv("GARMIN_PASSWORD")


def _get_token_json_env() -> Optional[str]:
    """
    Return the Garmin token JSON from environment variable.

    Checks ``GARMIN_TOKEN_JSON``.

    :return: Token JSON string, or None.
    """
    return os.getenv("GARMIN_TOKEN_JSON")


def get_credentials() -> Tuple[str, str]:
    """
    Get Garmin Connect credentials from user input or environment variables.

    Reads ``GARMIN_EMAIL`` or ``GARMIN_USERNAME`` and ``GARMIN_PASSWORD`` from the
    environment. Falls back to interactive prompting when environment variables are not
    set.

    :return: Tuple of (email, password).
    :raises click.ClickException: When credentials are required but not provided (empty
        email or password).
    """
    email = _get_email_env()
    password = _get_password_env()

    if email and password:
        click.echo(
            click.style("Using credentials from environment variables", fg="cyan")
        )
        click.echo(f"   Email: {email}")
        return email, password

    click.echo(click.style("Garmin Connect Authentication", fg="cyan", bold=True))
    click.echo()

    email = click.prompt("   Email", type=str)
    password = click.prompt("   Password", type=str, hide_input=True)

    if not email or not password:
        raise click.ClickException("Email and password are required")

    return email, password


def get_mfa_code() -> str:
    """
    Prompt user for MFA code.

    Checks ``GARMIN_MFA_CODE`` env var first. Falls back to interactive prompt when
    stdin is a TTY.

    :return: MFA code string.
    """
    env_code = os.getenv("GARMIN_MFA_CODE")
    if env_code:
        return env_code

    click.echo()
    click.echo(click.style("Multi-Factor Authentication Required", fg="yellow"))
    click.echo("   Check your email or phone for the MFA code")
    click.echo()

    mfa_code = click.prompt("   Enter 6-digit MFA code", type=str)

    if not mfa_code.isdigit() or len(mfa_code) != 6:
        click.secho("Warning: MFA code should be 6 digits", fg="yellow")

    return mfa_code


def _handle_mfa_authentication(garmin: GarminClient, result2) -> None:
    """
    Handle MFA authentication with one retry attempt.

    :param garmin: Garmin client instance.
    :param result2: MFA continuation token from login result.
    """
    click.secho("Initial authentication successful", fg="green")

    for attempt in range(2):
        try:
            mfa_code = get_mfa_code()
            click.echo("Completing MFA authentication...")
            garmin.resume_login(result2, mfa_code)
            click.secho("MFA authentication successful", fg="green", bold=True)
            return

        except Exception as e:
            if attempt == 0:
                click.secho(f"MFA authentication failed: {str(e)}", fg="red")
                click.echo("Please try again with a fresh MFA code")
                continue
            click.secho(
                f"MFA authentication failed after 2 attempts", fg="red", bold=True
            )
            raise


def _print_troubleshooting() -> None:
    """
    Print common troubleshooting steps.
    """
    click.echo()
    click.secho("Troubleshooting:", fg="yellow", bold=True)
    click.echo("   - Verify your email and password are correct")
    click.echo("   - Check for typos or case sensitivity")
    click.echo("   - Ensure you have internet connectivity")
    click.echo("   - If MFA is enabled, make sure the MFA code is current")
    click.echo("   - Try running the command again")
    click.echo("   - Check if Garmin Connect services are operational")
    click.echo()


def discover_accounts(
    base_token_dir: str = "~/.garminconnect",
) -> List[Tuple[str, Path]]:
    """
    Discover Garmin Connect accounts by scanning token subdirectories.

    Each numeric subdirectory in the base token directory represents a user_id with
    saved OAuth tokens.

    :param base_token_dir: Base directory containing per-account token subdirectories.
    :return: Sorted list of (user_id, token_dir_path) tuples.
    :raises FileNotFoundError: If base directory does not exist.
    :raises NotADirectoryError: If base path is not a directory.
    :raises RuntimeError: If no accounts are found.
    """
    base_path = Path(base_token_dir).expanduser()

    if not base_path.exists():
        raise FileNotFoundError(f"Token directory does not exist: {base_path}")

    if not base_path.is_dir():
        raise NotADirectoryError(f"Token path is not a directory: {base_path}")

    accounts = [
        (entry.name, entry)
        for entry in sorted(base_path.iterdir())
        if entry.is_dir() and entry.name.isdigit() and any(entry.iterdir())
    ]

    if accounts:
        return accounts

    token_files = list(base_path.glob("*token*.json"))
    if token_files:
        click.secho(
            "Warning: Found legacy token layout (tokens at root level). "
            "Run 'garmin auth' to migrate to per-account subdirectories.",
            fg="yellow",
        )
        return [("legacy", base_path)]

    raise RuntimeError(
        f"No accounts found in {base_path}. Run 'garmin auth' to authenticate."
    )


def restore_tokens_from_json(
    token_json: str,
    base_token_dir: str = "~/.garminconnect",
) -> bool:
    """
    Restore Garmin tokens from a JSON string and persist them to disk.

    Parses the JSON (same format as ``garmin_tokens.json``), loads tokens into a
    temporary client, calls the Garmin profile API to discover the user ID, and writes
    the token file to ``<base_token_dir>/<user_id>/garmin_tokens.json``.

    This is the preferred authentication path for CI/CD pipelines: paste the contents of
    ``garmin_tokens.json`` into the ``GARMIN_TOKEN_JSON`` GitHub secret after a one-time
    local login.

    :param token_json: JSON string containing ``di_token``, ``di_refresh_token``, and
        ``di_client_id``.
    :param base_token_dir: Base directory for per-account token storage.
    :return: True if tokens were successfully restored.
    :raises click.ClickException: If the JSON is invalid, the tokens are expired, or the
        profile fetch fails.
    """
    try:
        data = json.loads(token_json)
    except json.JSONDecodeError as e:
        raise click.ClickException(f"GARMIN_TOKEN_JSON is not valid JSON: {e}") from e

    required = ["di_token", "di_refresh_token", "di_client_id"]
    missing = [k for k in required if k not in data]
    if missing:
        raise click.ClickException(
            f"GARMIN_TOKEN_JSON is missing required fields: {missing}"
        )

    base_path = Path(base_token_dir).expanduser()

    try:
        garmin = GarminClient()
        garmin_tokens.loads(garmin, token_json)

        user_profile = garmin.get_user_profile()
        user_id = user_profile.get("id")
        if not user_id:
            raise RuntimeError(
                "Could not determine user ID from Garmin profile. "
                "The 'id' field was missing from get_user_profile() response."
            )

        base_path.mkdir(parents=True, exist_ok=True)
        if sys.platform != "win32":
            base_path.chmod(0o700)

        token_path = base_path / str(user_id)
        token_path.mkdir(exist_ok=True)
        if sys.platform != "win32":
            token_path.chmod(0o700)

        garmin.dump(str(token_path))

        click.secho(
            f"Restored tokens for user {user_id} from GARMIN_TOKEN_JSON.",
            fg="cyan",
        )
        return True

    except Exception as e:
        raise click.ClickException(
            f"Failed to restore tokens from GARMIN_TOKEN_JSON: {e}"
        ) from e


def refresh_tokens(
    email: str,
    password: str,
    base_token_dir: str = "~/.garminconnect",
    silent: bool = False,
) -> None:
    """
    Refresh Garmin Connect tokens with MFA support.

    Authenticates the user, auto-detects their Garmin user ID, and stores tokens in a
    per-account subdirectory under ``base_token_dir``.

    :param email: Garmin Connect email.
    :param password: Garmin Connect password.
    :param base_token_dir: Base directory for per-account token storage.
    :param silent: If True, suppress non-essential output.
    """
    base_path = Path(base_token_dir).expanduser()

    if not silent:
        click.echo()
        click.echo(click.style("Authenticating with Garmin Connect...", fg="cyan"))
        click.echo(f"   Token storage: {base_path}")
        click.echo()

    try:
        garmin = GarminClient()
        login_result = garmin.login(email, password, return_on_mfa=True)

        if isinstance(login_result, tuple) and len(login_result) == 2:
            result1, result2 = login_result

            if result1 == "needs_mfa":
                _handle_mfa_authentication(garmin, result2)
            else:
                if not silent:
                    click.secho(
                        "Authentication successful (no MFA required)",
                        fg="green",
                        bold=True,
                    )
        else:
            if not silent:
                click.secho(
                    "Authentication successful (no MFA required)",
                    fg="green",
                    bold=True,
                )

        user_id = garmin.get_user_profile().get("id")
        if not user_id:
            raise RuntimeError(
                "Could not determine user ID from Garmin profile. "
                "The 'id' field was missing from get_user_profile() response."
            )

        if not silent:
            click.echo(f"Detected user ID: {user_id}")
            click.echo("Saving authentication tokens...")

        base_path.mkdir(parents=True, exist_ok=True)
        if sys.platform != "win32":
            base_path.chmod(0o700)

        token_path = base_path / str(user_id)
        token_path.mkdir(exist_ok=True)
        if sys.platform != "win32":
            token_path.chmod(0o700)

        garmin.dump(str(token_path))

        if not silent:
            click.echo()
            click.secho("Tokens successfully saved!", fg="green", bold=True)
            click.echo(f"   User ID:  {user_id}")
            click.echo(f"   Location: {token_path}")
            click.echo()
            click.secho("Success! You're authenticated with Garmin Connect", fg="green")
            click.echo("   You can now run: garmin extract")
            click.echo()
            click.echo("Tokens auto-refresh transparently during extraction.")

    except Exception as e:
        click.echo()
        click.secho(f"Authentication failed: {str(e)}", fg="red", bold=True)
        _print_troubleshooting()
        raise click.ClickException("Authentication failed")


def _has_token_files(base_token_dir: str) -> bool:
    """
    Check whether at least one token subdirectory with files exists on disk.

    :param base_token_dir: Base directory for per-account token storage.
    :return: True when token files exist on disk.
    """
    base_path = Path(base_token_dir).expanduser()
    if not base_path.exists():
        return False
    for entry in base_path.iterdir():
        if entry.is_dir() and entry.name.isdigit() and any(entry.iterdir()):
            return True
    return any(base_path.glob("*token*.json"))


def check_authentication(base_token_dir: str = "~/.garminconnect") -> bool:
    """
    Check if valid authentication tokens exist for at least one account.

    Checks in order:
    1. ``GARMIN_TOKEN_JSON`` env var (can be restored to disk).
    2. ``GARMIN_EMAIL``/``GARMIN_USERNAME`` + ``GARMIN_PASSWORD`` env vars.
    3. Token files on disk in ``~/.garminconnect/``.

    :param base_token_dir: Base directory where per-account tokens are
        stored.
    :return: True if authentication is possible, False otherwise.
    """
    if _get_token_json_env():
        return True
    if _get_email_env() and _get_password_env():
        return True
    return _has_token_files(base_token_dir)


def ensure_authenticated(base_token_dir: str = "~/.garminconnect") -> None:
    """
    Ensure user is authenticated, prompt for credentials if not.

    Authentication is attempted in this priority order:

    1. Existing token files on disk (fast path, no API calls).
    2. ``GARMIN_TOKEN_JSON`` env var  restore to disk, then load.
    3. ``GARMIN_EMAIL``/``GARMIN_USERNAME`` + ``GARMIN_PASSWORD`` env
       vars  fresh login + MFA.
    4. Interactive prompt.

    :param base_token_dir: Base directory where per-account tokens are
        stored.
    :raises click.ClickException: If authentication fails.
    """
    # Priority 1: tokens already on disk (fastest path, no API calls).
    if _has_token_files(base_token_dir):
        return

    # Priority 2: GARMIN_TOKEN_JSON env var (CI with pre-generated token).
    token_json = _get_token_json_env()
    if token_json:
        click.secho(
            "Restoring tokens from GARMIN_TOKEN_JSON env var.",
            fg="cyan",
        )
        restore_tokens_from_json(token_json, base_token_dir)
        return

    # Priority 3: email/password env vars (fresh login in CI or local).
    email = _get_email_env()
    password = _get_password_env()
    if email and password:
        click.secho(
            "No saved tokens found; authenticating with env credentials.",
            fg="cyan",
        )
        refresh_tokens(email, password, base_token_dir, silent=True)
        return

    # Priority 4: interactive prompt.
    click.echo()
    click.secho(
        "No authentication tokens found. Please authenticate first.",
        fg="yellow",
        bold=True,
    )
    click.echo()

    if click.confirm("Would you like to authenticate now?", default=True):
        email, password = get_credentials()
        refresh_tokens(email, password, base_token_dir)
    else:
        raise click.ClickException(
            "Authentication required. Run 'garmin auth' to authenticate."
        )
