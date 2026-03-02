"""
Test runner for Codex Guardian testbench.

Discovers and runs all test_*.py files in this directory.
Exit code 0 = all tests passed. Exit code 1 = one or more failures.

Usage (from repo root):
    python testbench/run_all_tests.py
"""

import sys
import os
import unittest

# Ensure both the testbench and the project root are on the path
testbench_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(testbench_dir, "..")
sys.path.insert(0, project_root)
sys.path.insert(0, testbench_dir)

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=testbench_dir, pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    if result.wasSuccessful():
        print(f"\n✓ All {result.testsRun} tests passed.")
        sys.exit(0)
    else:
        failures = len(result.failures)
        errors = len(result.errors)
        print(f"\n✗ {failures} failure(s), {errors} error(s) out of {result.testsRun} tests.")
        sys.exit(1)
