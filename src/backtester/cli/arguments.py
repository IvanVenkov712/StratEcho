"""Argument parsing and cross-option validation for the Strat Echo CLI."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Sequence

from backtester.config import (
    DEFAULT_CONFIG_PATH,
    SIZING_OPTIONS,
    ConfigDocument,
    ConfigError,
    config_to_cli_arguments,
    load_config,
)
from backtester.sizing.asset_allocation import AssetAllocation


DEFAULT_SYMBOL = "SPY"
DEFAULT_YEARS = 5
DEFAULT_CSV_PERIOD_ANCHOR = "start-csv"
DEFAULT_INITIAL_CAPITAL = 10_000.0
DEFAULT_SHORT_WINDOW = 20
DEFAULT_LONG_WINDOW = 50
DEFAULT_ENTRY_WINDOW = 20
DEFAULT_EXIT_WINDOW = 10
DEFAULT_BENCHMARK = "buy-and-hold"
DEFAULT_SIZING = "all-in-all-out"
DEFAULT_COMMISSION_MODEL = "none"
DEFAULT_SLIPPAGE_RATE = 0.0
STRATEGY_CHOICES = (
    "buy-and-hold",
    "simple-moving-average",
    "exponential-moving-average",
    "cutler-rsi",
    "exponential-rsi",
    "wilder-rsi",
    "simple-mean-reversion",
    "exponential-mean-reversion",
    "donchian-breakout",
    # Backward-compatible aliases for the original CLI names.
    "moving-average",
    "rsi",
    "mean-reversion",
)
CSV_PERIOD_ANCHOR_CHOICES = ("start-csv", "end-today", "end-csv")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI and TOML options with explicit CLI values taking priority."""
    raw_args = _normalize_command_args(list(sys.argv[1:] if argv is None else argv))

    parser = _build_parser()
    try:
        config_path, is_explicit = _find_config_path(raw_args)
        config = load_config(config_path, required=is_explicit)
    except ConfigError as exc:
        parser.error(str(exc))

    command = raw_args[0]
    config_args = config_to_cli_arguments(
        config,
        command,
        cli_overrides=_find_cli_selector_overrides(raw_args[1:]),
    )
    args = parser.parse_args([command, *config_args, *raw_args[1:]])
    _normalize_universe(parser, args)

    if args.source == "csv" and args.csv_path is None:
        parser.error("--csv-path is required when --source csv is used.")

    _validate_commission_args(parser, args)
    args.sizing_by_symbol = _resolve_symbol_sizing(parser, args, config, raw_args[1:])

    return args


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="strat-echo",
        allow_abbrev=False,
        description="Run Strat Echo strategy backtests from the console.",
    )
    subparsers = parser.add_subparsers(dest="command")

    backtest_parser = subparsers.add_parser(
        "backtest",
        allow_abbrev=False,
        help="Run one strategy backtest and print its performance metrics.",
    )
    _add_common_arguments(backtest_parser)
    _add_strategy_arguments(backtest_parser)
    backtest_parser.add_argument(
        "--chart",
        dest="chart_path",
        type=Path,
        help="Save the backtest dashboard to this image path.",
    )
    backtest_parser.set_defaults(command="backtest")

    compare_parser = subparsers.add_parser(
        "compare",
        allow_abbrev=False,
        help="Compare one strategy against a benchmark strategy.",
    )
    _add_common_arguments(compare_parser)
    _add_strategy_arguments(compare_parser)
    compare_parser.add_argument(
        "--chart",
        dest="chart_path",
        type=Path,
        help="Save the comparison dashboard to this image path.",
    )
    compare_parser.add_argument(
        "--benchmark",
        choices=STRATEGY_CHOICES,
        default=DEFAULT_BENCHMARK,
        help="Benchmark strategy used for comparison. Default: buy-and-hold.",
    )
    compare_parser.set_defaults(command="compare")

    return parser


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=(
            "TOML configuration path. If omitted, strat-echo.toml in the "
            "current working directory is used when present."
        ),
    )
    universe = parser.add_mutually_exclusive_group()
    universe.add_argument(
        "--symbol",
        type=_symbol,
        help=f"Asset symbol to test. Default: {DEFAULT_SYMBOL}.",
    )
    universe.add_argument(
        "--symbols", nargs="+", type=_symbol, metavar="SYMBOL",
        help="Asset universe, e.g. SPY QQQ. Mutually exclusive with --symbol.",
    )
    parser.add_argument(
        "--allocation", action="append", type=_allocation, metavar="SYMBOL=WEIGHT",
        help="Repeat for every symbol; weights in [0, 1], total at most 1. Default: equal weights.",
    )
    parser.add_argument(
        "--priority", action="append", type=_priority, metavar="SYMBOL=INTEGER",
        help="Repeat per symbol. Default: 0; lower values first within each side, alphabetical ties.",
    )
    parser.add_argument(
        "--years",
        type=_positive_int,
        default=DEFAULT_YEARS,
        help=(
            "Number of calendar years used to derive a missing date boundary. "
            f"Default: {DEFAULT_YEARS}."
        ),
    )
    parser.add_argument(
        "--start",
        help=(
            "Inclusive start date in YYYY-MM-DD format. If --end is omitted, "
            "it is derived using --years."
        ),
    )
    parser.add_argument(
        "--end",
        help=(
            "Exclusive end date in YYYY-MM-DD format. If --start is omitted, "
            "it is used with --years to derive the start."
        ),
    )
    parser.add_argument(
        "--source",
        choices=["yfinance", "csv"],
        default="yfinance",
        help="Market data source. Default: yfinance.",
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        help="CSV file or directory used when --source csv is selected.",
    )
    parser.add_argument(
        "--csv-period-anchor",
        choices=CSV_PERIOD_ANCHOR_CHOICES,
        default=DEFAULT_CSV_PERIOD_ANCHOR,
        help=(
            "No-date CSV period behavior: start-csv derives the end from the "
            "universe's earliest first candle; end-today derives the start from "
            "today; end-csv derives the start from the universe's latest last "
            f"candle. Default: {DEFAULT_CSV_PERIOD_ANCHOR}."
        ),
    )
    parser.add_argument(
        "--initial-capital",
        type=_positive_float,
        default=DEFAULT_INITIAL_CAPITAL,
        help=f"Initial portfolio cash. Default: {DEFAULT_INITIAL_CAPITAL:.0f}.",
    )
    parser.add_argument(
        "--sizing",
        choices=["all-in-all-out", "fixed", "percent"],
        default=DEFAULT_SIZING,
        help=f"Position-sizing policy for every symbol. Default: {DEFAULT_SIZING}.",
    )
    parser.add_argument(
        "--buy-size",
        type=_positive_int,
        help="Whole shares bought per buy signal when --sizing fixed is used.",
    )
    parser.add_argument(
        "--sell-size",
        type=_positive_int,
        help="Whole shares sold per sell signal when --sizing fixed is used.",
    )
    parser.add_argument(
        "--buy-percent",
        type=_percentage,
        help="Fraction of the cash-limited allocation gap used per buy signal with --sizing percent.",
    )
    parser.add_argument(
        "--sell-percent",
        type=_percentage,
        help="Fraction of owned shares sold per sell signal with --sizing percent.",
    )
    parser.add_argument(
        "--buffer-rate",
        type=_slippage_rate,
        help=(
            "Fraction of each buy's allocation-gap budget left unspent. "
            "May be combined with any position-sizing policy."
        ),
    )
    parser.add_argument(
        "--commission-model",
        choices=["none", "fixed", "proportional"],
        default=DEFAULT_COMMISSION_MODEL,
        help=(
            "Commission model applied to each trade. "
            f"Default: {DEFAULT_COMMISSION_MODEL}."
        ),
    )
    parser.add_argument(
        "--fixed-commission",
        type=_non_negative_float,
        help="Cash commission per trade required with --commission-model fixed.",
    )
    parser.add_argument(
        "--commission-rate",
        type=_percentage,
        help=(
            "Fraction of trade notional charged as commission with "
            "--commission-model proportional."
        ),
    )
    parser.add_argument(
        "--slippage-rate",
        type=_slippage_rate,
        default=DEFAULT_SLIPPAGE_RATE,
        help=(
            "Adverse fill-price adjustment as a fraction in [0, 1). "
            f"Default: {DEFAULT_SLIPPAGE_RATE:.0f}."
        ),
    )


def _add_strategy_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--strategy",
        choices=STRATEGY_CHOICES,
        default="moving-average",
        help="Strategy for every symbol, with separate instances and shared parameters. Default: moving-average.",
    )
    parser.add_argument(
        "--short-window",
        type=_positive_int,
        default=DEFAULT_SHORT_WINDOW,
        help=f"Short moving average window. Default: {DEFAULT_SHORT_WINDOW}.",
    )
    parser.add_argument(
        "--long-window",
        type=_positive_int,
        default=DEFAULT_LONG_WINDOW,
        help=f"Long moving average window. Default: {DEFAULT_LONG_WINDOW}.",
    )
    parser.add_argument(
        "--rsi-period",
        type=_positive_int,
        default=14,
        help="RSI lookback period. Default: 14.",
    )
    parser.add_argument(
        "--rsi-min",
        type=float,
        default=30.0,
        help="RSI buy threshold. Default: 30.",
    )
    parser.add_argument(
        "--rsi-max",
        type=float,
        default=70.0,
        help="RSI sell threshold. Default: 70.",
    )
    parser.add_argument(
        "--mean-window",
        type=_positive_int,
        default=20,
        help="Mean reversion average window. Default: 20.",
    )
    parser.add_argument(
        "--mean-threshold",
        type=float,
        default=0.95,
        help=(
            "Mean reversion buy threshold as a fraction of the average. "
            "Default: 0.95."
        ),
    )
    parser.add_argument(
        "--entry-window",
        type=_positive_int,
        default=DEFAULT_ENTRY_WINDOW,
        help=f"Donchian breakout entry window. Default: {DEFAULT_ENTRY_WINDOW}.",
    )
    parser.add_argument(
        "--exit-window",
        type=_positive_int,
        default=DEFAULT_EXIT_WINDOW,
        help=f"Donchian breakout exit window. Default: {DEFAULT_EXIT_WINDOW}.",
    )


def _normalize_universe(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Resolve both symbol forms and validate complete per-symbol settings."""
    args.symbols = tuple(args.symbols or [args.symbol or DEFAULT_SYMBOL])
    if len(set(args.symbols)) != len(args.symbols):
        parser.error("The symbol universe must not contain duplicates.")
    args.symbol = args.symbols[0] if len(args.symbols) == 1 else None

    args.allocations = _symbol_settings(parser, args.symbols, args.allocation, "allocation")
    if args.allocation is None:
        weight = 1 / len(args.symbols)
        # Keep equal floating-point weights within the engine's strict sum limit.
        while sum([weight] * len(args.symbols)) > 1:
            weight = math.nextafter(weight, 0.0)
        args.allocations = dict.fromkeys(args.symbols, weight)
    elif set(args.allocations) != set(args.symbols):
        parser.error("--allocation must be supplied for every symbol when provided.")
    try:
        AssetAllocation(args.allocations)
    except ValueError as exc:
        parser.error(str(exc))

    priorities = _symbol_settings(parser, args.symbols, args.priority, "priority")
    args.priorities = {symbol: priorities.get(symbol, 0) for symbol in args.symbols}


def _symbol_settings[T: (float, int)](
    parser: argparse.ArgumentParser,
    symbols: Sequence[str],
    entries: Sequence[tuple[str, T]] | None,
    option: str,
) -> dict[str, T]:
    settings = {}
    for symbol, value in entries or ():
        if symbol not in symbols:
            parser.error(f"--{option} contains unknown symbol: {symbol}.")
        if symbol in settings:
            parser.error(f"Duplicate --{option} for symbol: {symbol}.")
        settings[symbol] = value
    return settings


def _resolve_symbol_sizing(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config: ConfigDocument,
    cli_arguments: Sequence[str],
) -> dict[str, argparse.Namespace]:
    """Merge global TOML, per-symbol TOML, and shared CLI sizing in that order."""
    backtest = config.get("backtest", {})
    per_symbol = {}
    for raw_symbol, settings in backtest.get("sizing_by_symbol", {}).items():
        try:
            symbol = _symbol(raw_symbol)
        except argparse.ArgumentTypeError as exc:
            parser.error(str(exc))
        if symbol not in args.symbols:
            parser.error(f"sizing_by_symbol contains unknown symbol: {symbol}.")
        if symbol in per_symbol:
            parser.error(f"Duplicate sizing_by_symbol entry for: {symbol}.")
        per_symbol[symbol] = settings

    cli_sizing = []
    index = 0
    while index < len(cli_arguments):
        option = cli_arguments[index].split("=", 1)[0].removeprefix("--").replace("-", "_")
        if cli_arguments[index].startswith("--") and option in SIZING_OPTIONS:
            cli_sizing.append(cli_arguments[index])
            if "=" not in cli_arguments[index]:
                index += 1
                cli_sizing.append(cli_arguments[index])
        index += 1

    resolved = {}
    for symbol in args.symbols:
        settings = {key: value for key, value in backtest.items() if key in SIZING_OPTIONS}
        overrides = per_symbol.get(symbol, {})
        if "sizing" in overrides and overrides["sizing"] != settings.get("sizing"):
            settings = {key: value for key, value in settings.items() if key == "sizing"}
        settings.update(overrides)
        config_args = config_to_cli_arguments(
            {"backtest": settings}, args.command,
            cli_overrides=_find_cli_selector_overrides(cli_sizing),
        )
        symbol_args = parser.parse_args([args.command, *config_args, *cli_sizing])
        _validate_sizing_args(parser, symbol_args)
        symbol_args.buffer_rate = args.buffer_rate
        resolved[symbol] = symbol_args
    return resolved


def _validate_sizing_args(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    fixed_values = (args.buy_size, args.sell_size)
    percent_values = (args.buy_percent, args.sell_percent)

    if args.sizing == "fixed" and any(value is None for value in fixed_values):
        parser.error(
            "--buy-size and --sell-size are required when --sizing fixed is used."
        )
    if args.sizing != "fixed" and any(value is not None for value in fixed_values):
        parser.error("--buy-size and --sell-size may only be used with --sizing fixed.")

    if args.sizing == "percent" and any(value is None for value in percent_values):
        parser.error(
            "--buy-percent and --sell-percent are required when --sizing percent is used."
        )
    if args.sizing != "percent" and any(
        value is not None for value in percent_values
    ):
        parser.error(
            "--buy-percent and --sell-percent may only be used with --sizing percent."
        )


def _validate_commission_args(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    if args.commission_model == "fixed" and args.fixed_commission is None:
        parser.error(
            "--fixed-commission is required when --commission-model fixed is used."
        )
    if args.commission_model != "fixed" and args.fixed_commission is not None:
        parser.error(
            "--fixed-commission may only be used with --commission-model fixed."
        )

    if args.commission_model == "proportional" and args.commission_rate is None:
        parser.error(
            "--commission-rate is required when "
            "--commission-model proportional is used."
        )
    if args.commission_model != "proportional" and args.commission_rate is not None:
        parser.error(
            "--commission-rate may only be used with --commission-model proportional."
        )


def _find_config_path(arguments: Sequence[str]) -> tuple[Path, bool]:
    """Return the final explicit --config value or the optional default path."""
    config_path: Path | None = None
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--config":
            if index + 1 >= len(arguments) or arguments[index + 1].startswith("-"):
                raise ConfigError("--config requires a file path.")
            config_path = Path(arguments[index + 1])
            index += 2
            continue
        if argument.startswith("--config="):
            value = argument.partition("=")[2]
            if not value:
                raise ConfigError("--config requires a file path.")
            config_path = Path(value)

        index += 1

    if config_path is None:
        return DEFAULT_CONFIG_PATH, False

    return config_path, True


def _normalize_command_args(arguments: list[str]) -> list[str]:
    """Insert the default command and allow --config before an explicit command."""
    if not arguments:
        return ["backtest"]
    if arguments[0] in {"backtest", "compare"}:
        return arguments

    prefix_end = 0
    while prefix_end < len(arguments):
        argument = arguments[prefix_end]
        if argument == "--config" and prefix_end + 1 < len(arguments):
            prefix_end += 2
            continue
        if argument.startswith("--config="):
            prefix_end += 1
            continue
        break

    if prefix_end < len(arguments) and arguments[prefix_end] in {
        "backtest",
        "compare",
    }:
        command = arguments[prefix_end]
        return [command, *arguments[:prefix_end], *arguments[prefix_end + 1 :]]

    return ["backtest", *arguments]


def _find_cli_selector_overrides(arguments: Sequence[str]) -> dict[str, str]:
    """Find explicit CLI values that select models with dependent settings."""
    overrides: dict[str, str] = {}
    selectors = {"sizing", "commission_model", "symbol", "symbols", "allocation", "priority"}
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument.startswith("--"):
            option, separator, inline_value = argument[2:].partition("=")
            name = option.replace("-", "_")
            if name in selectors:
                if separator:
                    overrides[name] = inline_value
                elif index + 1 < len(arguments):
                    overrides[name] = arguments[index + 1]
                    index += 1
        index += 1

    return overrides


def _symbol(value: str) -> str:
    symbol = value.strip().upper()
    if not symbol or any(char.isspace() for char in symbol) or "=" in symbol:
        raise argparse.ArgumentTypeError("symbol must be non-empty and contain no whitespace or '='")
    return symbol


def _assignment(value: str) -> tuple[str, str]:
    symbol, separator, setting = value.partition("=")
    if not separator or not setting.strip():
        raise argparse.ArgumentTypeError("expected SYMBOL=VALUE")
    return _symbol(symbol), setting.strip()


def _allocation(value: str) -> tuple[str, float]:
    symbol, weight = _assignment(value)
    return symbol, _percentage(weight)


def _priority(value: str) -> tuple[str, int]:
    symbol, priority = _assignment(value)
    return symbol, int(priority)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")

    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")

    return parsed


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("value must be a non-negative finite number")

    return parsed


def _percentage(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError("value must be between 0 and 1")

    return parsed


def _slippage_rate(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or not 0 <= parsed < 1:
        raise argparse.ArgumentTypeError(
            "value must be between 0 (inclusive) and 1 (exclusive)"
        )

    return parsed
