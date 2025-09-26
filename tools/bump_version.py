#!/usr/bin/env python3
"""
Version bumping tool for triangular arbitrage system.

Automatically updates version numbers and creates changelog entries following
semantic versioning principles.
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Tuple

# Version bump types
BUMP_TYPES = ["major", "minor", "patch"]

def get_current_version() -> str:
    """Get current version from version.py."""
    version_file = Path(__file__).parent.parent / "triangular_arbitrage" / "version.py"

    if not version_file.exists():
        raise FileNotFoundError(f"Version file not found: {version_file}")

    content = version_file.read_text()
    match = re.search(r'__version__ = ["\']([^"\']+)["\']', content)

    if not match:
        raise ValueError("Could not find version in version.py")

    return match.group(1)

def parse_version(version: str) -> Tuple[int, int, int]:
    """Parse semantic version string into components."""
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {version}")

    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        raise ValueError(f"Invalid version format: {version}")

def bump_version(current_version: str, bump_type: str) -> str:
    """Bump version based on type."""
    major, minor, patch = parse_version(current_version)

    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        raise ValueError(f"Invalid bump type: {bump_type}")

def update_version_file(new_version: str) -> None:
    """Update version.py with new version."""
    version_file = Path(__file__).parent.parent / "triangular_arbitrage" / "version.py"
    content = version_file.read_text()

    # Update version string
    content = re.sub(
        r'__version__ = ["\'][^"\']+["\']',
        f'__version__ = "{new_version}"',
        content
    )

    version_file.write_text(content)
    print(f"✅ Updated {version_file} to version {new_version}")

def update_changelog(version: str, bump_type: str, message: str = None) -> None:
    """Add entry to CHANGELOG.md."""
    changelog_file = Path(__file__).parent.parent / "CHANGELOG.md"

    if not changelog_file.exists():
        # Create new changelog
        changelog_content = """# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

"""
    else:
        changelog_content = changelog_file.read_text()

    # Create new entry
    date_str = datetime.now().strftime("%Y-%m-%d")
    entry_header = f"## [{version}] - {date_str}"

    # Determine change type based on bump type
    if bump_type == "major":
        change_type = "### Changed"
        default_message = "Breaking changes - see migration guide"
    elif bump_type == "minor":
        change_type = "### Added"
        default_message = "New features and enhancements"
    else:  # patch
        change_type = "### Fixed"
        default_message = "Bug fixes and improvements"

    entry_message = message or default_message

    new_entry = f"""
{entry_header}

{change_type}
- {entry_message}

"""

    # Insert after the header section
    lines = changelog_content.split('\n')
    insert_pos = 0

    # Find insertion point (after header)
    for i, line in enumerate(lines):
        if line.startswith('## [') or line.startswith('## Unreleased'):
            insert_pos = i
            break
        elif not line.strip() or line.startswith('#') or line.startswith('The format is'):
            continue
        else:
            insert_pos = i
            break

    # Insert new entry
    lines.insert(insert_pos, new_entry.strip())

    changelog_file.write_text('\n'.join(lines))
    print(f"✅ Updated CHANGELOG.md with version {version}")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Bump version and update changelog",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/bump_version.py patch
  python tools/bump_version.py minor --message "Added paper trading mode"
  python tools/bump_version.py major --message "Complete API redesign"
        """.strip()
    )

    parser.add_argument(
        "bump_type",
        choices=BUMP_TYPES,
        help="Type of version bump (major, minor, patch)"
    )

    parser.add_argument(
        "--message",
        "-m",
        help="Changelog message (optional)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )

    args = parser.parse_args()

    try:
        current_version = get_current_version()
        new_version = bump_version(current_version, args.bump_type)

        print(f"Current version: {current_version}")
        print(f"New version: {new_version}")

        if args.dry_run:
            print("🔍 Dry run - no files will be modified")
            return

        # Confirm the action
        confirm = input(f"Bump version from {current_version} to {new_version}? [y/N]: ")
        if confirm.lower() != 'y':
            print("❌ Version bump cancelled")
            return

        # Update files
        update_version_file(new_version)
        update_changelog(new_version, args.bump_type, args.message)

        print(f"""
🚀 Version bumped successfully!

Next steps:
1. Review the changes:
   git diff

2. Commit the version bump:
   git add triangular_arbitrage/version.py CHANGELOG.md
   git commit -m "Bump version to {new_version}"

3. Create a release tag:
   git tag -a v{new_version} -m "Release {new_version}"

4. Push changes:
   git push && git push --tags
        """)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()