"""Load and validate command-line configuration from TOML files."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Mapping, TypeAlias


DEFAULT_CONFIG_PATH = Path("strat-echo.toml")

ConfigValue: TypeAlias = str | int | float
ConfigDocument: TypeAlias = dict[str, dict[str, ConfigValue]]

_STRING_OPTIONS = {
    "symbol",
    "start",
    "end",
    "source",
    "csv_path",
    "csv_period_anchor",
    "chart",
    "sizing",
    "commission_model",
    "strategy",
    "benchmark",
}
_INTEGER_OPTIONS = {
    "years",
    "buy_size",
    "sell_size",
    "short_window",
    "long_window",
    "rsi_period",
    "mean_window",
    "entry_window",
    "exit_window",
}
_NUMBER_OPTIONS = {
    "initial_capital",
    "buy_percent",
    "sell_percent",
    "buffer_rate",
    "fixed_commission",
    "commission_rate",
    "slippage_rate",
    "rsi_min",
    "rsi_max",
    "mean_threshold",
}
_BACKTEST_OPTIONS = (
    _STRING_OPTIONS | _INTEGER_OPTIONS | _NUMBER_OPTIONS
) - {"benchmark"}
_SECTION_OPTIONS = {
    "backtest": _BACKTEST_OPTIONS,
    "compare": {"benchmark", "chart"},
}
_BACKTEST_ONLY_OPTIONS = {"chart"}
# ``buffer_rate`` modifies buy quantity resolution after the base sizing
# instruction is selected, so it deliberately has no selector dependency.
_SELECTOR_DEPENDENCIES = {
    "sizing": {"buy_size", "sell_size", "buy_percent", "sell_percent"},
    "commission_model": {"fixed_commission", "commission_rate"},
}


class ConfigError(ValueError):
    """Raised when a TOML configuration file cannot be used."""


def load_config(path: Path, *, required: bool) -> ConfigDocument:
    """Load a configuration file, or return an empty config if optional.

    Args:
        path: Explicit or default configuration path.
        required: Whether a missing file is an error. Explicit ``--config``
            paths are required, while the default path is optional.
    """

    if not path.exists():
        if required:
            raise ConfigError(f"Configuration file does not exist: {path}")
        return {}

    if not path.is_file():
        raise ConfigError(f"Configuration path is not a file: {path}")

    try:
        with path.open("rb") as config_file:
            document = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read configuration file {path}: {exc}") from exc

    return _validate_document(document, path)


def config_to_cli_arguments(
    config: ConfigDocument,
    command: str,
    *,
    cli_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    """Convert applicable TOML values to arguments parsed before real CLI input.

    Parsing these generated arguments through ``argparse`` keeps choices,
    ranges, and cross-option validation identical for TOML and CLI values. Real
    CLI arguments are appended later, which gives them the required priority.
    """

    options = dict(config.get("backtest", {}))
    if command == "compare":
        for name in _BACKTEST_ONLY_OPTIONS:
            options.pop(name, None)
        options.update(config.get("compare", {}))

    # If the CLI changes a selector, dependent TOML values for the old choice
    # must not make the new combination invalid. The CLI must provide any
    # values required by its newly selected model.
    for selector, dependencies in _SELECTOR_DEPENDENCIES.items():
        cli_value = (cli_overrides or {}).get(selector)
        config_value = options.get(selector)
        if cli_value is not None and config_value is not None:
            if cli_value != str(config_value):
                for dependency in dependencies:
                    options.pop(dependency, None)

    arguments: list[str] = []
    for name, value in options.items():
        arguments.extend((f"--{name.replace('_', '-')}", str(value)))

    return arguments


def _validate_document(document: dict[str, object], path: Path) -> ConfigDocument:
    unknown_sections = document.keys() - _SECTION_OPTIONS.keys()
    if unknown_sections:
        section_list = ", ".join(sorted(unknown_sections))
        raise ConfigError(f"Unknown configuration section(s) in {path}: {section_list}")

    validated: ConfigDocument = {}
    for section_name, raw_section in document.items():
        if not isinstance(raw_section, dict):
            raise ConfigError(
                f"Configuration section [{section_name}] in {path} must be a table."
            )

        unknown_options = raw_section.keys() - _SECTION_OPTIONS[section_name]
        if unknown_options:
            option_list = ", ".join(sorted(unknown_options))
            raise ConfigError(
                f"Unknown option(s) in [{section_name}] in {path}: {option_list}"
            )

        validated[section_name] = {
            name: _validate_value(section_name, name, value, path)
            for name, value in raw_section.items()
        }

    return validated


def _validate_value(
    section: str,
    name: str,
    value: object,
    path: Path,
) -> ConfigValue:
    if name in _STRING_OPTIONS:
        expected = "a string"
        valid = type(value) is str
    elif name in _INTEGER_OPTIONS:
        expected = "an integer"
        valid = type(value) is int
    else:
        expected = "a number"
        valid = type(value) in (int, float)

    if not valid:
        raise ConfigError(
            f"Option {name!r} in [{section}] in {path} must be {expected}."
        )

    assert isinstance(value, (str, int, float))
    return value
