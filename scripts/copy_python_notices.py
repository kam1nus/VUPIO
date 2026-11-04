"""Copy installed Python distribution notices without publishing environment data."""
from importlib.metadata import distribution
from pathlib import Path
import re
import shutil
import sys

target=Path(sys.argv[1])
for name in sys.argv[2:]:
    package=distribution(name)
    folder=target/name
    folder.mkdir(parents=True,exist_ok=True)
    for entry in package.files or ():
        if any(part.lower()=='licenses' for part in entry.parts) or re.search(r'^(license|notice|copying)',entry.name,re.I):
            file=Path(package.locate_file(entry))
            if file.is_file():
                shutil.copyfile(file,folder/entry.name)
