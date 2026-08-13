import os

# Lets `coverage run` see code executed in the subprocess CLI tests
# (tests/test_cli_*.py spawn `sys.executable -m apiver.cli` as a child
# process). No-op unless COVERAGE_PROCESS_START is set by the coverage CI
# step, so this has no effect on a normal `pytest`/`apiver` run.
if os.environ.get("COVERAGE_PROCESS_START"):
    import coverage

    coverage.process_startup()
