# conftest.py — pytest configuration
# These files are standalone integration scripts (not pytest-compatible).
# They run at module level and/or call sys.exit(). Exclude from collection.
collect_ignore = [
    "test_day2.py",
    "test_day3.py",
    "test_dashboard.py",
    "test_private_sessions.py",
    "test_team_mailbox.py",
    "test_techie_marketplace.py",
    "test_guard_activation.py",
]
