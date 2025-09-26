# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-09-26

### Added
- **Reproducible Development Environment**: Docker and Docker Compose setup for consistent development
- **Professional Documentation**: Comprehensive docstrings and inline comments throughout codebase
- **Code Quality Tooling**: Pre-commit hooks, automated formatting (Black, isort), and linting (flake8)
- **Type Safety**: MyPy integration with comprehensive type annotations
- **Configuration Validation**: CLI tool for validating strategy configurations
- **Testing Infrastructure**: Comprehensive unit, integration, and performance test suites
- **Dependency Injection**: Time and RNG provider interfaces for better testability
- **Exception Hierarchy**: Structured exception system for better error handling
- **Metrics and Monitoring**: Prometheus metrics server with Grafana integration
- **Build System**: Modern pyproject.toml with console script entry points
- **Release Management**: Automated version bumping and changelog generation

### Enhanced
- **Exchange Adapters**: Paper trading and backtesting exchange implementations
- **Configuration System**: Normalized config loading with validation and defaults
- **Logging System**: Structured logging with consistent formatting
- **Constants Management**: Centralized enums and constants for maintainability

### Changed
- **Project Structure**: Reorganized codebase with proper module hierarchy
- **Import System**: Consistent absolute imports and reduced circular dependencies
- **Documentation**: Professional-grade docstrings following Google style
- **Code Organization**: Consolidated utility functions and removed duplicate code

## [0.1.0] - 2024-01-01

### Added
- Initial triangular arbitrage trading system implementation
- Basic opportunity detection using NetworkX graph algorithms
- Core execution engine with multi-leg order coordination
- Risk controls and position management
- Coinbase Advanced Trading API integration
- Basic paper trading simulation
- Configuration-driven strategy system
