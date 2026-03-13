import re
from pathlib import Path


def get_version() -> str:
    # Automated version management from installed package
    """Get version from installed package, git tags, or commit ID."""
    # Try to get version from the installed package
    try:
        from importlib.metadata import version

        return version("fabulous-fpga")
    except Exception:
        pass

    repo_root = Path(__file__).parent.parent.parent

    # Fallback: read git data directly from .git directory
    try:
        git_dir = repo_root / ".git"

        # Get current commit hash
        head_file = git_dir / "HEAD"
        if head_file.exists():
            head_content = head_file.read_text().strip()

            # HEAD usually contains "ref: refs/heads/branch_name"
            if head_content.startswith("ref: "):
                ref_path = head_content[5:]  # Remove "ref: " prefix
                commit_file = git_dir / ref_path
                if commit_file.exists():
                    commit_hash = commit_file.read_text().strip()[:7]
                else:
                    commit_hash = "unknown"
            else:
                # Detached HEAD - contains the commit hash directly
                commit_hash = head_content[:7]

            # No tags found, return dev version with commit hash
            return f"dev-{commit_hash}"
    except Exception:
        pass

    # Fallback to unknown version
    return "unknown"


def get_display_version(version_text: str) -> str:
    """Strip development and local suffixes from the displayed version tag."""
    return re.sub(r"\.dev.*$", "", version_text)
