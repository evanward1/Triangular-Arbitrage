#!/usr/bin/env python3
"""
CLI smoke test for snapshot and health commands
"""

import tempfile
import shutil
import subprocess
import json
from pathlib import Path


def test_snapshot_cli():
    """Test snapshot command creates files"""
    print("\nTesting snapshot CLI...")

    temp_dir = tempfile.mkdtemp()

    try:
        result = subprocess.run(
            ['python', 'monitor_cycles.py', 'snapshot', '--out-dir', temp_dir, '--recent', '5', '--window', '60'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0

        out_path = Path(temp_dir)
        json_files = list(out_path.glob("ops_snapshot_*.json"))
        md_files = list(out_path.glob("ops_snapshot_*.md"))

        assert len(json_files) == 1, f"Expected 1 JSON file, found {len(json_files)}"
        assert len(md_files) == 1, f"Expected 1 MD file, found {len(md_files)}"

        with open(json_files[0], 'r') as f:
            data = json.load(f)

        assert 'metadata' in data
        assert 'config' in data
        assert 'suppression_summary' in data

        print(f"  ✓ Created JSON: {json_files[0].name}")
        print(f"  ✓ Created MD: {md_files[0].name}")
        print(f"  ✓ JSON contains required sections")

    finally:
        shutil.rmtree(temp_dir)


def test_health_cli():
    """Test health command returns exit code"""
    print("\nTesting health CLI...")

    result = subprocess.run(
        ['python', 'monitor_cycles.py', 'health', '--window', '60', '--max-suppression-rate', '95'],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"Health check failed: {result.stdout}"
    assert "OK" in result.stdout or "FAIL" in result.stdout

    print(f"  ✓ Exit code: {result.returncode}")
    print(f"  ✓ Output: {result.stdout.strip()}")


if __name__ == '__main__':
    print("="*60)
    print("CLI SMOKE TEST: Snapshot & Health")
    print("="*60)

    test_snapshot_cli()
    test_health_cli()

    print("\n" + "="*60)
    print("ALL CLI SMOKE TESTS PASSED ✓")
    print("="*60)
    print()