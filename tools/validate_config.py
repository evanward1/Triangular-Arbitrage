#!/usr/bin/env python3
"""
Configuration validation CLI tool

Validates YAML strategy configuration files against the schema.
"""

import sys
import argparse
import json
from pathlib import Path
from typing import List, Dict, Any

import yaml
from pydantic import ValidationError

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from triangular_arbitrage.config_schema import validate_config_file, StrategyConfig


def validate_single_config(config_path: Path, verbose: bool = False) -> Dict[str, Any]:
    """
    Validate a single configuration file

    Returns:
        Dictionary with validation results
    """
    result = {
        "file": str(config_path),
        "valid": False,
        "errors": [],
        "warnings": [],
        "config": None,
    }

    try:
        # Validate the configuration
        config = validate_config_file(config_path)
        result["valid"] = True
        result["config"] = config.model_dump() if verbose else None

        # Add any warnings based on configuration values
        warnings = []

        # Check for potential issues
        if config.min_profit_bps <= 5:
            warnings.append(
                "min_profit_bps is very low (≤5 bps) - may result in unprofitable trades"
            )

        if config.max_slippage_bps > config.min_profit_bps:
            warnings.append(
                f"max_slippage_bps ({config.max_slippage_bps}) > min_profit_bps ({config.min_profit_bps}) - may result in losses"
            )

        if config.execution and config.execution.mode == "paper":
            paper_config = config.execution.paper
            if paper_config and paper_config.fill_ratio < 0.5:
                warnings.append(
                    "Paper trading fill_ratio is very low (<0.5) - may not reflect realistic execution"
                )

        if config.risk_controls.max_open_cycles > 10:
            warnings.append(
                "max_open_cycles is high (>10) - consider capital allocation implications"
            )

        result["warnings"] = warnings

    except FileNotFoundError as e:
        result["errors"].append(f"File not found: {e}")
    except yaml.YAMLError as e:
        result["errors"].append(f"YAML parsing error: {e}")
    except ValidationError as e:
        result["errors"].append(f"Validation error: {e}")
    except Exception as e:
        result["errors"].append(f"Unexpected error: {e}")

    return result


def validate_multiple_configs(
    config_paths: List[Path], verbose: bool = False
) -> List[Dict[str, Any]]:
    """Validate multiple configuration files"""
    results = []

    for config_path in config_paths:
        result = validate_single_config(config_path, verbose)
        results.append(result)

    return results


def find_config_files(directory: Path, pattern: str = "*.yaml") -> List[Path]:
    """Find configuration files in a directory"""
    if not directory.exists():
        return []

    config_files = []

    # Search recursively for YAML files
    for file_path in directory.rglob(pattern):
        if file_path.is_file():
            config_files.append(file_path)

    # Also check for .yml extension
    if pattern == "*.yaml":
        for file_path in directory.rglob("*.yml"):
            if file_path.is_file():
                config_files.append(file_path)

    return sorted(config_files)


def print_validation_results(
    results: List[Dict[str, Any]], verbose: bool = False, json_output: bool = False
):
    """Print validation results in human-readable or JSON format"""

    if json_output:
        print(json.dumps(results, indent=2, default=str))
        return

    total_files = len(results)
    valid_files = sum(1 for r in results if r["valid"])
    invalid_files = total_files - valid_files

    print(f"\n=== Configuration Validation Results ===")
    print(f"Total files: {total_files}")
    print(f"Valid files: {valid_files}")
    print(f"Invalid files: {invalid_files}")
    print("=" * 45)

    for result in results:
        file_path = result["file"]
        status = "✓ VALID" if result["valid"] else "✗ INVALID"

        print(f"\n{status}: {file_path}")

        # Print errors
        if result["errors"]:
            print("  Errors:")
            for error in result["errors"]:
                print(f"    - {error}")

        # Print warnings
        if result["warnings"]:
            print("  Warnings:")
            for warning in result["warnings"]:
                print(f"    - {warning}")

        # Print config details if verbose and valid
        if verbose and result["valid"] and result["config"]:
            print("  Configuration summary:")
            config = result["config"]
            print(f"    - Strategy: {config.get('name', 'N/A')}")
            print(f"    - Exchange: {config.get('exchange', 'N/A')}")
            execution_config = config.get("execution", {})
            execution_mode = (
                execution_config.get("mode", "live") if execution_config else "live"
            )
            print(f"    - Execution mode: {execution_mode}")
            print(f"    - Min profit: {config.get('min_profit_bps', 'N/A')} bps")
            print(f"    - Max slippage: {config.get('max_slippage_bps', 'N/A')} bps")


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Validate triangular arbitrage strategy configuration files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate a single configuration file
  python tools/validate_config.py configs/strategies/my_strategy.yaml

  # Validate all configurations in a directory
  python tools/validate_config.py --directory configs/strategies/

  # Validate with verbose output
  python tools/validate_config.py --verbose configs/strategies/strategy_robust_example.yaml

  # Output results as JSON
  python tools/validate_config.py --json configs/strategies/

  # Validate and exit with error code if any invalid
  python tools/validate_config.py --strict configs/strategies/
        """,
    )

    # Input options
    parser.add_argument(
        "config_files", nargs="*", help="Configuration file(s) to validate"
    )
    parser.add_argument(
        "--directory",
        "-d",
        type=Path,
        help="Directory to search for configuration files",
    )

    # Output options
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed configuration information",
    )
    parser.add_argument(
        "--json", "-j", action="store_true", help="Output results in JSON format"
    )
    parser.add_argument(
        "--strict",
        "-s",
        action="store_true",
        help="Exit with error code if any configuration is invalid",
    )
    parser.add_argument(
        "--pattern",
        "-p",
        default="*.yaml",
        help="File pattern to search for when using --directory (default: *.yaml)",
    )

    args = parser.parse_args()

    # Determine config files to validate
    config_paths = []

    if args.config_files and args.directory:
        print("Error: Cannot specify both config files and directory")
        return 1
    elif args.config_files:
        config_paths = [Path(f) for f in args.config_files]
    elif args.directory:
        config_paths = find_config_files(args.directory, args.pattern)

        if not config_paths:
            print(
                f"No configuration files found in {args.directory} matching pattern '{args.pattern}'"
            )
            return 1
    else:
        print("Error: Must specify either config files or directory")
        return 1

    # Validate configurations
    try:
        results = validate_multiple_configs(config_paths, verbose=args.verbose)
    except KeyboardInterrupt:
        print("\nValidation interrupted by user")
        return 1
    except Exception as e:
        print(f"Unexpected error during validation: {e}")
        return 1

    # Print results
    print_validation_results(results, verbose=args.verbose, json_output=args.json)

    # Determine exit code
    if args.strict:
        invalid_count = sum(1 for r in results if not r["valid"])
        if invalid_count > 0:
            if not args.json:
                print(
                    f"\nValidation failed: {invalid_count} invalid configuration(s) found"
                )
            return 1

    # Print summary if not JSON output
    if not args.json:
        valid_count = sum(1 for r in results if r["valid"])
        print(
            f"\nValidation complete: {valid_count}/{len(results)} configurations valid"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
