from tools import read_local_codebase, write_readme_file, commit_and_push_changes
import os
from dotenv import load_dotenv

load_dotenv("./paths.env")

WORKSPACE_DIR = os.getenv("WORKSPACE_DIR")

print(read_local_codebase(WORKSPACE_DIR))