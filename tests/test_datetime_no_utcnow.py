"""Test that no datetime.utcnow() usage remains in the codebase (portable implementation)."""
import os


EXCLUDED_DIRS = {"__pycache__", ".venv", ".git"}


def test_datetime_no_utcnow():
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    matches = []
    this_file = os.path.abspath(__file__)
    for root, dirs, files in os.walk(backend_dir):
        # Prune excluded dirs
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for fname in files:
            if not fname.endswith(('.py', '.txt', '.md')):
                continue
            path = os.path.join(root, fname)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    for lineno, line in enumerate(f, 1):
                        if 'datetime.utcnow' in line and path != this_file:
                            matches.append(f"{path}:{lineno}:{line.strip()}")
            except Exception:
                continue
    assert not matches, "Found datetime.utcnow() usage:\n" + "\n".join(matches)
    print("✅ No datetime.utcnow() usage found in codebase")

if __name__ == "__main__":
    test_datetime_no_utcnow()