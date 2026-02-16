"""
Configuration management CLI commands.

Manages mf settings stored in config.yaml (or config.json for backwards compatibility).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
import yaml
from rich.console import Console
from rich.table import Table

from mf.core.backup import DEFAULT_KEEP_COUNT, DEFAULT_KEEP_DAYS
from mf.core.config import get_paths

console = Console()


def get_config_path() -> Path:
    """Get path to config file."""
    paths = get_paths()
    return paths.config_file


def load_config() -> dict[str, Any]:
    """Load configuration from file (supports YAML and JSON)."""
    config_path = get_config_path()
    if not config_path.exists():
        return {}

    content = config_path.read_text()
    if not content.strip():
        return {}

    # Detect format: YAML files typically don't start with '{'
    if content.strip().startswith("{"):
        result: dict[str, Any] = json.loads(content)
        return result
    else:
        loaded = yaml.safe_load(content)
        if isinstance(loaded, dict):
            return loaded
        return {}


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to file (YAML format)."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    # Use YAML for cleaner config files
    config_path.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))


def get_config_value(key: str, default: Any = None) -> Any:
    """Get a configuration value by dotted key."""
    config = load_config()
    parts = key.split(".")
    current = config
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def set_config_value(key: str, value: Any) -> None:
    """Set a configuration value by dotted key."""
    config = load_config()
    parts = key.split(".")

    # Navigate to the parent dict
    current = config
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]

    # Set the value
    current[parts[-1]] = value
    save_config(config)


# Default configuration schema with descriptions
CONFIG_SCHEMA: dict[str, dict[str, Any]] = {
    "backup.keep_days": {
        "default": DEFAULT_KEEP_DAYS,
        "type": int,
        "description": "Maximum age of backups in days",
    },
    "backup.keep_count": {
        "default": DEFAULT_KEEP_COUNT,
        "type": int,
        "description": "Minimum number of backups to keep",
    },
    "github.default_user": {
        "default": None,
        "type": str,
        "description": "Default GitHub username for project commands",
    },
}


@click.group()
def config():
    """Manage mf configuration.

    Settings are stored in .mf/config.yaml.
    """
    pass


@config.command(name="show")
@click.option("--all", "show_all", is_flag=True, help="Show all settings including defaults")
def show_cmd(show_all: bool):
    """Show current configuration.

    Without --all, only shows settings that differ from defaults.
    """
    config = load_config()
    config_path = get_config_path()

    if not config and not show_all:
        console.print("[dim]No custom configuration set. Using defaults.[/dim]")
        console.print(f"[dim]Config file: {config_path}[/dim]")
        console.print("\n[dim]Use 'mf config show --all' to see all settings.[/dim]")
        return

    table = Table(title="Configuration", show_header=True, header_style="bold cyan")
    table.add_column("Setting")
    table.add_column("Value", style="green")
    table.add_column("Default", style="dim")
    table.add_column("Description", style="dim")

    for key, schema in CONFIG_SCHEMA.items():
        current = get_config_value(key)
        default = schema["default"]
        is_custom = current is not None and current != default

        if show_all or is_custom:
            display_value = str(current) if current is not None else f"[dim]{default}[/dim]"
            table.add_row(
                key,
                display_value,
                str(default),
                schema["description"],
            )

    console.print(table)
    console.print(f"\n[dim]Config file: {config_path}[/dim]")


@config.command(name="get")
@click.argument("key")
def get_cmd(key: str):
    """Get a configuration value.

    Examples:
        mf config get backup.keep_days
        mf config get backup.keep_count
    """
    if key not in CONFIG_SCHEMA:
        console.print(f"[red]Unknown setting: {key}[/red]")
        console.print("\nAvailable settings:")
        for k in CONFIG_SCHEMA:
            console.print(f"  - {k}")
        return

    value = get_config_value(key)
    default = CONFIG_SCHEMA[key]["default"]

    if value is None:
        console.print(f"{key} = {default} [dim](default)[/dim]")
    else:
        console.print(f"{key} = {value}")


@config.command(name="set")
@click.argument("key")
@click.argument("value")
def set_cmd(key: str, value: str):
    """Set a configuration value.

    Examples:
        mf config set backup.keep_days 14
        mf config set backup.keep_count 5
    """
    if key not in CONFIG_SCHEMA:
        console.print(f"[red]Unknown setting: {key}[/red]")
        console.print("\nAvailable settings:")
        for k in CONFIG_SCHEMA:
            console.print(f"  - {k}")
        return

    schema = CONFIG_SCHEMA[key]

    # Convert to appropriate type
    typed_value: int | float | bool | str
    try:
        if schema["type"] is int:
            typed_value = int(value)
        elif schema["type"] is float:
            typed_value = float(value)
        elif schema["type"] is bool:
            typed_value = value.lower() in ("true", "1", "yes")
        else:
            typed_value = value
    except ValueError:
        console.print(f"[red]Invalid value type. Expected {schema['type'].__name__}[/red]")
        return

    set_config_value(key, typed_value)
    console.print(f"[green]Set {key} = {typed_value}[/green]")


@config.command(name="reset")
@click.argument("key", required=False)
@click.option("--all", "reset_all", is_flag=True, help="Reset all settings to defaults")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def reset_cmd(key: str | None, reset_all: bool, force: bool):
    """Reset configuration to defaults.

    Examples:
        mf config reset backup.keep_days   # Reset single setting
        mf config reset --all              # Reset all settings
    """
    if not key and not reset_all:
        console.print("[red]Specify a key or use --all to reset all settings[/red]")
        return

    if reset_all:
        if not force and not click.confirm("Reset all settings to defaults?"):
            console.print("[yellow]Cancelled[/yellow]")
            return

        config_path = get_config_path()
        if config_path.exists():
            config_path.unlink()
        console.print("[green]All settings reset to defaults[/green]")
        return

    if key not in CONFIG_SCHEMA:
        console.print(f"[red]Unknown setting: {key}[/red]")
        return

    config = load_config()
    parts = key.split(".")

    # Remove the key from config
    current = config
    for part in parts[:-1]:
        if part in current:
            current = current[part]
        else:
            console.print(f"[dim]{key} is already at default[/dim]")
            return

    if parts[-1] in current:
        del current[parts[-1]]
        save_config(config)
        console.print(f"[green]Reset {key} to default ({CONFIG_SCHEMA[key]['default']})[/green]")
    else:
        console.print(f"[dim]{key} is already at default[/dim]")


@config.command(name="path")
def path_cmd():
    """Show path to config file."""
    config_path = get_config_path()
    console.print(str(config_path))
