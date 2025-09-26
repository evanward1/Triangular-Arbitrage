"""Version information for triangular arbitrage system."""

__version__ = "0.2.0"
__version_info__ = tuple(int(i) for i in __version__.split("."))

# Version metadata
VERSION_MAJOR = __version_info__[0]
VERSION_MINOR = __version_info__[1]
VERSION_PATCH = __version_info__[2]

def get_version() -> str:
    """Get the current version string."""
    return __version__

def get_version_info() -> dict:
    """Get detailed version information."""
    return {
        "version": __version__,
        "major": VERSION_MAJOR,
        "minor": VERSION_MINOR,
        "patch": VERSION_PATCH,
    }