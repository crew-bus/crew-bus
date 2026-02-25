# conftest.py — pytest configuration
# These files are standalone integration scripts (not pytest-compatible).
# They run at module level and/or call sys.exit(). Exclude from collection.
collect_ignore = [
    "test_techie_marketplace.py",
    "test_skill_vetting.py",
]
