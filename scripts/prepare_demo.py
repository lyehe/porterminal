"""Create a fresh scratch copy of the agent demo and print its absolute path."""

from pathlib import Path
from shutil import copytree, ignore_patterns
from tempfile import mkdtemp


def main() -> None:
    source = Path(__file__).resolve().parents[1] / "examples" / "agent-demo"
    destination = Path(mkdtemp(prefix="porterminal-demo-")) / "invoice"
    copytree(source, destination, ignore=ignore_patterns("__pycache__", "*.pyc"))
    print(destination)


if __name__ == "__main__":
    main()
