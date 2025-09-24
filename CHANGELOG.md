# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-09-23
### 🚀 MAJOR RELEASE: Lightning Arbitrage Engine
#### Added
- **Lightning Arbitrage Mode**: Execute profitable trades IMMEDIATELY when found (no ranking delays)
- **Massive Opportunity Coverage**: Scan 1,920+ triangular arbitrage combinations from 329 currencies
- **Native Coinbase Advanced Trading API**: Direct integration with proper credential handling
- **Smart Profit Hunting**: Execute ALL profitable opportunities, not just the "best" one
- **Real-Time Profit Calculation**: Live basis point calculations with fee accounting
- **Comprehensive Cycle Generation**: `generate_all_cycles.py` creates thousands of arbitrage opportunities
- **Multi-Tier Strategy Files**: Priority (500), Massive (1,000), and Complete (1,920) cycle options

#### Changed
- **BREAKING**: Execution strategy completely rewritten for immediate profit capture
- **BREAKING**: Strategy files now use different cycle files (coinbase_cycles_*.csv)
- Updated README.md with comprehensive lightning arbitrage documentation
- Enhanced requirements.txt with all necessary dependencies

#### Improved
- Zero-delay execution eliminates opportunity loss from ranking/sorting
- Professional-grade risk management with configurable profit thresholds
- Real-time progress tracking and execution logging
- Optimized API usage for maximum scanning speed

#### Fixed
- Eliminated critical timing delays that killed arbitrage opportunities
- Fixed Coinbase API authentication issues with Advanced Trading credentials
- Resolved profit calculation accuracy with proper fee accounting

## [1.2.0] - 2024-10-24
### Added
- cycle detection by @ruidazeng

## [1.1.1] - 2024-09-07
### Fixed
- main profit result display

## [1.1.0] - 2024-09-07
### Added
- networkx dependencies

## [1.0.6] - 2024-04-18
### Added
- Added `whitelisted_symbols` to `run_detection`

## [1.0.5] - 2024-01-09
### Fixed
- Fix `is_delisted_symbols` 1.0.4 new condition

## [1.0.4] - 2024-01-09
### Fixed
- Consider delisted symbol if `ticker_time` is None

## [1.0.3] - 2024-01-08
### Fixed
- Add `None` check before restoring `best_triplet`

## [1.0.2] - 2024-01-08
### Added
- `ignored_symbols` param to `run_detection`

## [1.0.1] - 2023-10-18
### Fixed
- Added MANIFEST.in to fix PYPI installation

## [1.0.0] - 2023-10-18
### Added
- Initial version
