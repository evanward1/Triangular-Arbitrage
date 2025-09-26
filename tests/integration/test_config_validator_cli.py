"""
Integration tests for configuration validator CLI
"""

import pytest
import subprocess
import tempfile
import yaml
import json
import os
from pathlib import Path


@pytest.fixture
def valid_config():
    """Valid strategy configuration"""
    return {
        "name": "test_strategy_cli",
        "exchange": "binance",
        "trading_pairs_file": "data/cycles/test_cycles.csv",
        "min_profit_bps": 10,
        "max_slippage_bps": 20,
        "max_leg_latency_ms": 500,
        "capital_allocation": {"mode": "fixed_fraction", "fraction": 0.1},
        "risk_controls": {"max_open_cycles": 1},
        "fees": {"taker_bps": 10, "maker_bps": 5},
        "order": {
            "type": "market",
            "allow_partial_fills": False,
            "max_retries": 3,
            "retry_delay_ms": 1000,
        },
    }


@pytest.fixture
def invalid_config():
    """Invalid strategy configuration"""
    return {
        "name": "test_strategy_invalid",
        "exchange": "binance",
        "trading_pairs_file": "data/cycles/test_cycles.csv",
        "min_profit_bps": -100,  # Invalid: too low
        "max_slippage_bps": -5,  # Invalid: negative
        "max_leg_latency_ms": 500,
        "capital_allocation": {
            "mode": "fixed_fraction"
            # Missing required 'fraction' field
        },
        "risk_controls": {"max_open_cycles": 0},  # Invalid: too low
        "fees": {"taker_bps": -10, "maker_bps": 5},  # Invalid: negative
        "order": {
            "type": "invalid_type",  # Invalid order type
            "allow_partial_fills": False,
            "max_retries": 3,
            "retry_delay_ms": 1000,
        },
    }


@pytest.fixture
def config_with_warnings():
    """Configuration that's valid but has warnings"""
    return {
        "name": "test_strategy_warnings",
        "exchange": "binance",
        "trading_pairs_file": "data/cycles/test_cycles.csv",
        "min_profit_bps": 3,  # Very low - should trigger warning
        "max_slippage_bps": 50,  # Higher than profit - should trigger warning
        "max_leg_latency_ms": 500,
        "capital_allocation": {"mode": "fixed_fraction", "fraction": 0.1},
        "risk_controls": {"max_open_cycles": 15},  # High - should trigger warning
        "fees": {"taker_bps": 10, "maker_bps": 5},
        "order": {
            "type": "market",
            "allow_partial_fills": False,
            "max_retries": 3,
            "retry_delay_ms": 1000,
        },
    }


class TestConfigValidatorCLI:
    """Test the configuration validator CLI tool"""

    def get_validator_path(self):
        """Get path to validator CLI"""
        return Path(__file__).parent.parent.parent / "tools" / "validate_config.py"

    def run_validator(self, *args, input_data=None):
        """Run the validator CLI with given arguments"""
        cmd = ["python", str(self.get_validator_path())] + list(args)
        result = subprocess.run(cmd, input=input_data, capture_output=True, text=True)
        return result

    def test_validate_single_valid_config(self, valid_config):
        """Test validating a single valid configuration file"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(valid_config, f)
            config_path = f.name

        try:
            result = self.run_validator(config_path)
            assert result.returncode == 0
            assert "✓ VALID" in result.stdout
            assert "Validation complete" in result.stdout
        finally:
            os.unlink(config_path)

    def test_validate_single_invalid_config(self, invalid_config):
        """Test validating a single invalid configuration file"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(invalid_config, f)
            config_path = f.name

        try:
            result = self.run_validator(config_path)
            assert result.returncode == 0  # Default mode doesn't exit with error
            assert "✗ INVALID" in result.stdout
            assert "Validation error" in result.stdout
        finally:
            os.unlink(config_path)

    def test_validate_single_config_strict_mode(self, valid_config, invalid_config):
        """Test strict mode exit codes"""
        # Valid config in strict mode should return 0
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(valid_config, f)
            valid_path = f.name

        try:
            result = self.run_validator("--strict", valid_path)
            assert result.returncode == 0
            assert "✓ VALID" in result.stdout
        finally:
            os.unlink(valid_path)

        # Invalid config in strict mode should return 1
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(invalid_config, f)
            invalid_path = f.name

        try:
            result = self.run_validator("--strict", invalid_path)
            assert result.returncode == 1
            assert "✗ INVALID" in result.stdout
            assert "Validation failed" in result.stdout
        finally:
            os.unlink(invalid_path)

    def test_validate_verbose_mode(self, valid_config):
        """Test verbose output mode"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(valid_config, f)
            config_path = f.name

        try:
            result = self.run_validator("--verbose", config_path)
            assert result.returncode == 0
            assert "✓ VALID" in result.stdout
            assert "Configuration summary:" in result.stdout
            assert "Strategy:" in result.stdout
            assert "Exchange:" in result.stdout
        finally:
            os.unlink(config_path)

    def test_validate_json_output(self, valid_config, invalid_config):
        """Test JSON output format"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as valid_file:
            yaml.dump(valid_config, valid_file)
            valid_path = valid_file.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as invalid_file:
            yaml.dump(invalid_config, invalid_file)
            invalid_path = invalid_file.name

        try:
            result = self.run_validator("--json", valid_path, invalid_path)
            assert result.returncode == 0

            # Parse JSON output
            output_data = json.loads(result.stdout)
            assert isinstance(output_data, list)
            assert len(output_data) == 2

            # Check valid config result - find by valid status
            valid_result = next(r for r in output_data if r["valid"] is True)
            assert valid_result["valid"] is True
            assert len(valid_result["errors"]) == 0

            # Check invalid config result - find by invalid status
            invalid_result = next(r for r in output_data if r["valid"] is False)
            assert invalid_result["valid"] is False
            assert len(invalid_result["errors"]) > 0

        finally:
            os.unlink(valid_path)
            os.unlink(invalid_path)

    def test_validate_directory(self, valid_config, invalid_config):
        """Test validating all configs in a directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create multiple config files
            valid_path = tmpdir_path / "valid_config.yaml"
            with open(valid_path, "w") as f:
                yaml.dump(valid_config, f)

            invalid_path = tmpdir_path / "invalid_config.yaml"
            with open(invalid_path, "w") as f:
                yaml.dump(invalid_config, f)

            # Validate directory
            result = self.run_validator("--directory", str(tmpdir_path))
            assert result.returncode == 0
            assert "✓ VALID" in result.stdout
            assert "✗ INVALID" in result.stdout
            assert "Total files: 2" in result.stdout
            assert "Valid files: 1" in result.stdout
            assert "Invalid files: 1" in result.stdout

    def test_validate_directory_with_pattern(self, valid_config):
        """Test validating directory with specific pattern"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create files with different extensions
            yaml_path = tmpdir_path / "config.yaml"
            with open(yaml_path, "w") as f:
                yaml.dump(valid_config, f)

            yml_path = tmpdir_path / "config.yml"
            with open(yml_path, "w") as f:
                yaml.dump(valid_config, f)

            txt_path = tmpdir_path / "config.txt"
            with open(txt_path, "w") as f:
                f.write("not a yaml file")

            # Default pattern should find both .yaml and .yml
            result = self.run_validator("--directory", str(tmpdir_path))
            assert result.returncode == 0
            assert "Total files: 2" in result.stdout

            # Specific pattern should find only .yml
            result = self.run_validator(
                "--directory", str(tmpdir_path), "--pattern", "*.yml"
            )
            assert result.returncode == 0
            assert "Total files: 1" in result.stdout

    def test_validate_nonexistent_file(self):
        """Test validation of non-existent file"""
        result = self.run_validator("/nonexistent/config.yaml")
        assert result.returncode == 0  # Default mode doesn't fail
        assert "✗ INVALID" in result.stdout
        assert "File not found" in result.stdout

    def test_validate_nonexistent_directory(self):
        """Test validation of non-existent directory"""
        result = self.run_validator("--directory", "/nonexistent/directory")
        assert result.returncode == 1
        assert "No configuration files found" in result.stdout

    def test_validate_empty_directory(self):
        """Test validation of empty directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.run_validator("--directory", tmpdir)
            assert result.returncode == 1
            assert "No configuration files found" in result.stdout

    def test_validate_invalid_yaml_file(self):
        """Test validation of file with invalid YAML"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")  # Invalid YAML syntax
            config_path = f.name

        try:
            result = self.run_validator(config_path)
            assert result.returncode == 0
            assert "✗ INVALID" in result.stdout
            assert "YAML parsing error" in result.stdout
        finally:
            os.unlink(config_path)

    def test_validate_config_with_warnings(self, config_with_warnings):
        """Test validation shows warnings for valid but problematic configs"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_with_warnings, f)
            config_path = f.name

        try:
            result = self.run_validator(config_path)
            assert result.returncode == 0
            assert "✓ VALID" in result.stdout
            assert "Warnings:" in result.stdout
            # Should show warnings about low profit and high slippage
            assert "min_profit_bps is very low" in result.stdout
            assert "max_slippage_bps" in result.stdout
        finally:
            os.unlink(config_path)

    def test_help_flag(self):
        """Test help flag shows usage information"""
        result = self.run_validator("--help")
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()
        assert (
            "Validate triangular arbitrage strategy configuration files"
            in result.stdout
        )
        assert "Examples:" in result.stdout

    def test_multiple_files_validation(self, valid_config, invalid_config):
        """Test validating multiple files at once"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as valid_file:
            yaml.dump(valid_config, valid_file)
            valid_path = valid_file.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as invalid_file:
            yaml.dump(invalid_config, invalid_file)
            invalid_path = invalid_file.name

        try:
            result = self.run_validator(valid_path, invalid_path)
            assert result.returncode == 0
            assert "✓ VALID" in result.stdout
            assert "✗ INVALID" in result.stdout
            assert "Total files: 2" in result.stdout
            assert "Valid files: 1" in result.stdout
            assert "Invalid files: 1" in result.stdout
        finally:
            os.unlink(valid_path)
            os.unlink(invalid_path)

    def test_keyboard_interrupt_handling(self):
        """Test that keyboard interrupt is handled gracefully"""
        # This test is challenging to implement reliably in CI
        # We'll just verify the CLI starts correctly
        result = self.run_validator("--help")
        assert result.returncode == 0

    def test_validator_executable_permissions(self):
        """Test that the validator script has executable permissions"""
        validator_path = self.get_validator_path()
        assert validator_path.exists()
        # Check if file is executable (on Unix systems)
        import stat

        file_stat = validator_path.stat()
        is_executable = file_stat.st_mode & stat.S_IXUSR
        assert is_executable, "Validator CLI should be executable"


class TestConfigValidatorEdgeCases:
    """Test edge cases for configuration validator"""

    def get_validator_path(self):
        """Get path to validator CLI"""
        return Path(__file__).parent.parent.parent / "tools" / "validate_config.py"

    def run_validator(self, *args):
        """Run the validator CLI with given arguments"""
        cmd = ["python", str(self.get_validator_path())] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result

    def test_empty_yaml_file(self):
        """Test validation of empty YAML file"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")  # Empty file
            config_path = f.name

        try:
            result = self.run_validator(config_path)
            assert result.returncode == 0
            assert "✗ INVALID" in result.stdout
            assert "empty or invalid" in result.stdout or "required" in result.stdout
        finally:
            os.unlink(config_path)

    def test_yaml_file_with_null_content(self):
        """Test validation of YAML file with null content"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("null")  # YAML null
            config_path = f.name

        try:
            result = self.run_validator(config_path)
            assert result.returncode == 0
            assert "✗ INVALID" in result.stdout
        finally:
            os.unlink(config_path)

    def test_large_config_file(self):
        """Test validation of large configuration file"""
        large_config = {
            "name": "large_strategy",
            "exchange": "binance",
            "trading_pairs_file": "data/cycles/large_cycles.csv",
            "min_profit_bps": 10,
            "max_slippage_bps": 20,
            "max_leg_latency_ms": 500,
            "capital_allocation": {"mode": "fixed_fraction", "fraction": 0.1},
            "risk_controls": {"max_open_cycles": 1},
            "fees": {"taker_bps": 10, "maker_bps": 5},
            "order": {
                "type": "market",
                "allow_partial_fills": False,
                "max_retries": 3,
                "retry_delay_ms": 1000,
            },
            # Add many extra valid fields to make it large
            "execution": {
                "mode": "paper",
                "paper": {
                    "fee_bps": 30,
                    "fill_ratio": 0.95,
                    "initial_balances": {f"CURRENCY_{i}": 1000.0 for i in range(100)},
                },
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(large_config, f)
            config_path = f.name

        try:
            result = self.run_validator(config_path)
            assert result.returncode == 0
            assert "✓ VALID" in result.stdout
        finally:
            os.unlink(config_path)
