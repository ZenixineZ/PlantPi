#!/usr/bin/env python3
"""Run PlantPi simulation tests and compare output against expected_<name>.txt files.

Each test consists of:
  <name>_cfg.json       — config passed to PlantPi.py -c
  <name>_sample.csv     — simulator input data (referenced inside cfg)
  expected_<name>.txt   — reference output

Lines in expected_*.txt:
  # comment              — skipped (documentation only)
  [*] variable line      — skipped (content varies per run, e.g. state restore)
  [... description ...]  — skipped (wildcard: matches any number of output lines)
  anything else          — MUST appear verbatim in actual output (stripped)

Tests are discovered automatically: any expected_<name>.txt with a matching
<name>_cfg.json in the same directory is included.

Usage:
  python3 tests/run_tests.py                  # run all tests
  python3 tests/run_tests.py topoff           # run one test by name
  python3 tests/run_tests.py -v               # show full output on failure
  python3 tests/run_tests.py -v aggregate_alert
"""

import subprocess
import sys
import os
import argparse

TESTS_DIR = os.path.dirname(os.path.realpath(__file__))
PLANTPI   = os.path.realpath(os.path.join(TESTS_DIR, '..', 'PlantPi.py'))
REPO_ROOT = os.path.dirname(PLANTPI)

# Timeout in seconds per test — override per name if needed
DEFAULT_TIMEOUT = 30
TIMEOUTS = {
    'top_and_bottom_fill': 60,
}


def discover_tests():
    """Return sorted list of test names found in TESTS_DIR."""
    names = []
    for f in os.listdir(TESTS_DIR):
        if f.startswith('expected_') and f.endswith('.txt'):
            name = f[len('expected_'):-len('.txt')]
            cfg = os.path.join(TESTS_DIR, f'{name}_cfg.json')
            if os.path.exists(cfg):
                names.append(name)
    return sorted(names)


def load_required(name):
    """Return required assertion strings from expected_<name>.txt."""
    path = os.path.join(TESTS_DIR, f'expected_{name}.txt')
    required = []
    with open(path) as f:
        for raw in f:
            line = raw.rstrip('\n')
            s = line.strip()
            if not s:
                continue
            if s.startswith('#'):
                continue
            if s.startswith('[*]'):
                continue
            if s.startswith('[...') and s.endswith('...]'):
                continue
            required.append(s)
    return required


def run_test(name, timeout):
    cfg = os.path.join(TESTS_DIR, f'{name}_cfg.json')
    try:
        r = subprocess.run(
            ['python3', '-u', PLANTPI, '-c', cfg],
            capture_output=True, text=True,
            timeout=timeout, cwd=REPO_ROOT,
        )
        return (r.stdout + r.stderr).splitlines(), None
    except subprocess.TimeoutExpired:
        return [], 'timed out'


def check(name, verbose=False):
    timeout = TIMEOUTS.get(name, DEFAULT_TIMEOUT)
    print(f'  {name}...', end=' ', flush=True)

    lines, err = run_test(name, timeout)
    if err:
        print(f'FAIL ({err})')
        return False

    actual = {l.strip() for l in lines}
    required = load_required(name)
    missing = [r for r in required if r not in actual]

    if missing:
        print('FAIL')
        for m in missing:
            print(f'    MISSING: {m!r}')
        if verbose:
            print('    --- actual output ---')
            for l in lines:
                print(f'    {l}')
        return False

    print('PASS')
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run PlantPi simulation tests')
    parser.add_argument('tests', nargs='*',
                        help='test name(s) to run (default: all discovered)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='show full output on failure')
    args = parser.parse_args()

    all_tests = discover_tests()

    if args.tests:
        unknown = [n for n in args.tests if n not in all_tests]
        if unknown:
            print(f'Unknown test(s): {unknown}. Available: {all_tests}')
            sys.exit(1)
        suite = args.tests
    else:
        suite = all_tests

    print(f'Running {len(suite)} test(s)...')
    results = [check(n, args.verbose) for n in suite]

    passed = sum(results)
    total  = len(results)
    print(f'\n{passed}/{total} passed')
    sys.exit(0 if all(results) else 1)
