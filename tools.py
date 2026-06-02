import os
import subprocess
from langchain_core.tools import tool
import json

@tool
def read_local_codebase(root_dir: str) -> str:
    """
    Reads the local codebase starting from the specified root directory and returns its content as a string.
    
    Args:
        root_dir (str): The root directory of the codebase to read.
    
    Returns:
        str: The content of the local codebase as a string.
    """

    content = []
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', '__pycache__', 'venv', 'env', 'packages', '.vscode']]
        for file in files:
            if file.endswith(('.py', '.js', '.json', '.md', '.yaml', '.ipynb')):
                content.append(os.path.join(root, file))
    return "\n".join(content)


@tool
def read_file_contents(file_path: str) -> str:
    """
    Reads the contents of a file and returns it as a string.
    
    Args:
        file_path (str): The path to the file to read.
    
        try:
    """
    try:
        if not os.path.exists(file_path):
            return f"Error: The file '{file_path}' does not exist."
        
        if file_path.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.pdf')):
            return f"Error: The file '{file_path}' is a binary file and cannot be read as text."
        
        # --- Handle Jupyter Notebooks ---
        if file_path.endswith('.ipynb'):
            with open(file_path, 'r', encoding='utf-8') as f:
                notebook_data = json.load(f)
            
            clean_content = []
            cells = notebook_data.get('cells', [])
            
            for index, cell in enumerate(cells):
                cell_type = cell.get('cell_type', 'unknown')
                # Source is usually a list of strings (one per line)
                source_lines = cell.get('source', [])
                source_text = "".join(source_lines) if isinstance(source_lines, list) else str(source_lines)
                
                clean_content.append(f"### [Cell {index} - Type: {cell_type}]\n{source_text}\n")
            
            notebook_string = "\n".join(clean_content)
            return f"--- CONTENTS OF {os.path.basename(file_path)} (CELL OUTPUTS STRIPPED) ---\n{notebook_string}"
            
        # --- Handle All Other Text Files ---
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return f"--- CONTENTS OF {os.path.basename(file_path)} ---\n{content}"
        
    except json.JSONDecodeError:
        return f"Error: '{os.path.basename(file_path)}' is an invalid JSON/Notebook file."
    except Exception as e:
        return f"An error occurred while reading the file: {e}"

@tool
def write_readme_file(repo_path: str, readme_content: str) -> str:
    """
    Writes a README.md file in the specified repository path with the provided content.
    
    Args:
        repo_path (str): The path to the repository where the README.md file will be created.
        readme_content (str): The content to be written in the README.md file.
    
    Returns:
        str: A message indicating that the README.md file has been created successfully.
    """
    readme_path = os.path.join(repo_path, 'README.md')
    with open(readme_path, 'w') as f:
        f.write(readme_content)
    return f"README.md written created at {readme_path}"


@tool
def commit_and_push_changes(repo_path: str, commit_message: str, do_current_branch: bool = True, branch: str = "main") -> str:
    """
    Commits and pushes changes to the specified branch in the repository.
    
    Args:
        repo_path (str): The path to the repository where changes will be committed and pushed.
        commit_message (str): The commit message to use for the commit.
        do_current_branch (bool): Whether to use the current branch (default is True).
        branch (str): The branch to which the changes will be pushed (default is "main").
    
    Returns:
        str: A message indicating that the changes have been committed and pushed successfully.
    """
    try:
        if do_current_branch:
            # get current branch
            result = subprocess.run(["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
            branch = result.stdout.strip()
        # First pull the changes to avoid conflicts
        subprocess.run(["git", "-C", repo_path, "pull", "origin", branch], check=True)

        #subprocess.run(["git", "-C", repo_path, "add", "."], check=True)
        #subprocess.run(["git", "-C", repo_path, "commit", "-m", commit_message], check=True)
        #subprocess.run(["git", "-C", repo_path, "push", "origin", branch], check=True)
        return f"Changes committed with message '{commit_message}' and pushed to branch '{branch}'."
    except subprocess.CalledProcessError as e:
        return f"An error occurred while committing and pushing changes: {e}"
