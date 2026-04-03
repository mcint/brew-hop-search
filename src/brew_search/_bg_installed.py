"""Background process to refresh installed packages index."""
from brew_search.sources.installed import refresh

if __name__ == "__main__":
    refresh(silent=True)
