"""Test to ensure volarix4_backtest does not import volarix4.core.* modules.

This test guards against accidental strategy logic imports in the backtest package.
All signal generation MUST go through the HTTP API.
"""

import ast
import sys
from pathlib import Path


def check_file_for_core_imports(filepath: Path) -> list:
    """Check a Python file for volarix4.core.* imports.

    Args:
        filepath: Path to Python file to check

    Returns:
        List of forbidden import statements found
    """
    forbidden_imports = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=str(filepath))

        for node in ast.walk(tree):
            # Check for: import volarix4.core.xxx
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith('volarix4.core'):
                        forbidden_imports.append(f"import {alias.name}")

            # Check for: from volarix4.core.xxx import yyy
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith('volarix4.core'):
                    imports = ', '.join(alias.name for alias in node.names)
                    forbidden_imports.append(f"from {node.module} import {imports}")

    except Exception as e:
        print(f"Warning: Failed to parse {filepath}: {e}")

    return forbidden_imports


def check_package_for_core_imports(package_dir: Path) -> dict:
    """Check entire package for volarix4.core.* imports.

    Args:
        package_dir: Path to package directory

    Returns:
        Dictionary mapping filepath to list of forbidden imports
    """
    violations = {}

    # Get all Python files in package (excluding tests and this file)
    python_files = list(package_dir.glob("*.py"))

    for filepath in python_files:
        # Skip test files
        if filepath.name.startswith("test_"):
            continue

        # Skip __pycache__
        if "__pycache__" in str(filepath):
            continue

        forbidden = check_file_for_core_imports(filepath)
        if forbidden:
            violations[filepath] = forbidden

    return violations


def main():
    """Main test function."""
    # Get package directory
    package_dir = Path(__file__).parent

    print("=" * 70)
    print("CHECKING FOR FORBIDDEN volarix4.core.* IMPORTS")
    print("=" * 70)
    print(f"Package directory: {package_dir}")
    print()

    # Note: data_source.py is ALLOWED to import volarix4.core.data.fetch_ohlc
    # for MT5 data loading (not strategy logic), so we'll allow that specific import
    ALLOWED_IMPORTS = {
        "data_source.py": ["from volarix4.core.data import fetch_ohlc"]
    }

    violations = check_package_for_core_imports(package_dir)

    # Filter out allowed imports
    filtered_violations = {}
    for filepath, forbidden_imports in violations.items():
        filename = filepath.name
        allowed = ALLOWED_IMPORTS.get(filename, [])

        # Filter out allowed imports
        remaining = [imp for imp in forbidden_imports if imp not in allowed]

        if remaining:
            filtered_violations[filepath] = remaining

    if filtered_violations:
        print("FAILED: Found forbidden volarix4.core.* imports:")
        print()
        for filepath, imports in filtered_violations.items():
            print(f"  {filepath.name}:")
            for imp in imports:
                print(f"    - {imp}")
        print()
        print("=" * 70)
        print("volarix4_backtest MUST NOT import volarix4.core.* modules!")
        print("All signal generation must go through the HTTP API.")
        print("=" * 70)
        return 1
    else:
        print("PASSED: No forbidden volarix4.core.* imports found")
        print()
        print("Allowed exceptions:")
        for filename, allowed in ALLOWED_IMPORTS.items():
            print(f"  {filename}:")
            for imp in allowed:
                print(f"    - {imp} (data loading only, not strategy logic)")
        print()
        print("=" * 70)
        return 0


if __name__ == "__main__":
    sys.exit(main())
