import os
import re
import shutil
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

# match lines like KEY=VALUE, ignoring comments and blank lines
ENV_LINE_RE = re.compile(r"^([^#\n=]+?)=(.*)$")
OLD_PREFIX = "ANIWORLD_"
NEW_PREFIX = "H0MELAB_"


def modern_env_key(key: str) -> str:
    """Return the v2 name while keeping provider-specific names untouched."""
    return NEW_PREFIX + key[len(OLD_PREFIX) :] if key.startswith(OLD_PREFIX) else key


def legacy_env_key(key: str) -> str:
    return OLD_PREFIX + key[len(NEW_PREFIX) :] if key.startswith(NEW_PREFIX) else key


def sync_env_aliases(values=None):
    """Expose v1 and v2 names in-process; v2 always wins when both exist.

    The compatibility aliases let an existing deployment upgrade without losing
    a single setting while the rest of the code moves to the new public names.
    """
    source = dict(values or os.environ)
    for key, value in source.items():
        if key.startswith(NEW_PREFIX):
            os.environ[legacy_env_key(key)] = str(value)
        elif key.startswith(OLD_PREFIX) and modern_env_key(key) not in source:
            os.environ[modern_env_key(key)] = str(value)


def initialize_app_env(example_path: Path, default_dir: Path) -> Path:
    """Resolve the app directory and load its .env file.

    The default .env doubles as the pointer to a relocated app directory. On
    first relocation, copy the existing file so user settings move with it.
    """
    default_dir = Path(default_dir).expanduser().resolve()
    home_legacy_dir = (Path.home() / ".aniworld").resolve()
    docker_legacy_dir = Path("/home/aniworld/.aniworld")
    legacy_dir = (
        docker_legacy_dir.resolve()
        if docker_legacy_dir.exists() and not home_legacy_dir.exists()
        else home_legacy_dir
    )
    legacy_default_pointer = False

    configured_dir = os.environ.get("H0MELAB_INSTALL_FOLDER")
    if configured_dir is None:
        legacy_setting = os.environ.get("ANIWORLD_INSTALL_FOLDER")
        if legacy_setting:
            legacy_setting_path = Path(legacy_setting).expanduser()
            if not legacy_setting_path.is_absolute():
                legacy_setting_path = Path.home() / legacy_setting_path
            is_old_default = legacy_setting.strip() in (".aniworld", "~/.aniworld")
            if not is_old_default and legacy_setting_path.resolve() != legacy_dir:
                configured_dir = legacy_setting
            else:
                legacy_default_pointer = True

    # First v2 start: preserve the complete v1 state (database, secrets,
    # themes, captcha profile and .env) before anything is opened or migrated.
    migrated_from_legacy = (
        configured_dir is None
        and default_dir != legacy_dir
        and not default_dir.exists()
        and legacy_dir.exists()
    )
    if migrated_from_legacy:
        shutil.copytree(legacy_dir, default_dir)
    default_env_path = default_dir / ".env"

    if configured_dir is None and default_env_path.exists():
        configured = dotenv_values(default_env_path)
        configured_dir = configured.get("H0MELAB_INSTALL_FOLDER")
        if configured_dir is None:
            legacy_setting = configured.get("ANIWORLD_INSTALL_FOLDER")
            if legacy_setting:
                legacy_setting_path = Path(legacy_setting).expanduser()
                if not legacy_setting_path.is_absolute():
                    legacy_setting_path = Path.home() / legacy_setting_path
                is_old_default = legacy_setting.strip() in (".aniworld", "~/.aniworld")
                if not is_old_default and legacy_setting_path.resolve() != legacy_dir:
                    configured_dir = legacy_setting
                else:
                    legacy_default_pointer = True

    app_dir = Path(configured_dir or default_dir).expanduser()
    if not app_dir.is_absolute():
        app_dir = Path.home() / app_dir
    app_dir = app_dir.resolve()

    env_path = app_dir / ".env"
    if (
        env_path != default_env_path
        and not env_path.exists()
        and default_env_path.exists()
    ):
        app_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(default_env_path, env_path)

    merge_env(example_path, env_path)
    if migrated_from_legacy or legacy_default_pointer:
        persist_env_values(env_path, {"H0MELAB_INSTALL_FOLDER": str(default_dir)})
        os.environ["H0MELAB_INSTALL_FOLDER"] = str(default_dir)
    sync_env_aliases()
    return app_dir


def merge_env(example_path: Path, env_path: Path):
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if not example_path.exists():
        if env_path.exists():
            load_dotenv(env_path)
        return

    example_lines = example_path.read_text().splitlines()

    # Load existing values from old env
    existing_values = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            m = ENV_LINE_RE.match(line)
            if m:
                existing_values[m.group(1).strip()] = m.group(2).strip()

    # An old .env is rewritten into the v2 schema in place. Values are copied,
    # never discarded, and provider names such as ANIWORLD_ENABLE_ANIWORLD keep
    # their semantic value under the new H0MELAB_ prefix.
    for key, value in tuple(existing_values.items()):
        modern = modern_env_key(key)
        if modern != key and modern not in existing_values:
            existing_values[modern] = value

    merged_lines = []
    written_keys = set()
    for line in example_lines:
        m = ENV_LINE_RE.match(line)
        if not m:
            # keep comments, blank lines, formatting exactly
            merged_lines.append(line)
            continue

        key = m.group(1).strip()
        written_keys.add(key)
        default_value = m.group(2)

        # replace value if user has one
        if key in existing_values:
            merged_lines.append(f"{key}={existing_values[key]}")
        else:
            merged_lines.append(f"{key}={default_value}")

    # Preserve deployment-specific variables that are not part of the shipped
    # example. Legacy product-prefixed keys are emitted once under the v2 name.
    extras = []
    for key, value in existing_values.items():
        modern = modern_env_key(key)
        if key.startswith(OLD_PREFIX) or modern in written_keys or modern in extras:
            continue
        extras.append(modern)
        merged_lines.append(f"{modern}={value}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(merged_lines) + "\n")

    # Load the merged env file
    load_dotenv(env_path)
    sync_env_aliases(dotenv_values(env_path))


def persist_env_values(env_path: Path, updates: dict):
    """Write specific KEY=VALUE pairs into the .env file, preserving the rest.

    Only the given keys are touched: existing lines (comments, other keys,
    formatting) are kept as-is, matching keys are rewritten in place, and any
    missing keys are appended at the end. Values are quoted so paths, templates
    and secrets survive a write/read round trip unchanged.
    """
    env_path = Path(env_path)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = (
        env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    )

    remaining = dict(updates)
    out = []
    for line in lines:
        m = ENV_LINE_RE.match(line)
        key = m.group(1).strip() if m else None
        if key is not None and key in remaining:
            out.append(f"{key}={_quote_env_value(remaining.pop(key))}")
        else:
            out.append(line)

    for key, value in remaining.items():
        out.append(f"{key}={_quote_env_value(value)}")

    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _quote_env_value(value):
    """Encode one value using python-dotenv's single-quoted grammar."""
    value = str(value)
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"
