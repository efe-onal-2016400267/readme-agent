# readme_agent

`readme_agent` is an elite, state-of-the-art LangGraph-powered assistant designed to automate code auditing, README documentation generation, and Git workflow automation. Equipped with both short-term conversational memory and a long-term profile scratchpad, the agent dynamically learns developer preferences, scans local workspaces, generates beautifully structured Markdown documentation, and commits/pushes changes directly to Git repositories.

---

## Key Features

- **Workspace Discovery**: Automatically scans your workspace directory to identify potential Git repositories.
- **Interactive Repository Selection**: Prompts the user to select one or multiple repositories to process in a single session.
- **State-of-the-Art LangGraph Architecture**: Implements a robust `StateGraph` with custom state reducers, conditional routing, and interrupt-driven human-in-the-loop validation.
- **Gemini-Optimized Message Reducers**: Implements custom state reducers (such as `messages_state_operator`) to enforce strict message ordering and history trimming, as Gemini models require specific message sequences (e.g., preventing orphaned tool messages or invalid conversational turns).
- **Long-Term Memory & Reflection**: Uses an `InMemoryStore` to persist developer preferences (e.g., formatting styles, naming conventions) across sessions, updating them dynamically via a reflection node.
- **Short-Term Memory**: Uses `MemorySaver` for thread-level checkpointing and conversation history.
- **Automated Git Workflows**: Integrates tools to read local codebases, read individual files (including Jupyter Notebooks with cell outputs stripped), write READMEs, and commit/push changes.

---

## Architecture & Graph Flow

The agent's workflow is modeled as a state machine using LangGraph:

```
  [START]
     │
     ▼
[discover_repos]
     │
     ▼
[ask_user_selection] <─── (Interrupt / User Input)
     │
     ▼
[advance_loop] ◄──────────────────────────────────────────┐
     │                                                    │
     ├─► [call_model] ──► [tools] ──► [call_model]        │
     │        │                                           │
     │        ▼                                           │
     │    [reflect] <─── (Interrupt / User Feedback) ─────┘
     │
     ▼
   [END]
```

### Node Descriptions

1. **`discover_repos`**: Scans the workspace directory for folders and updates the state with discovered repositories.
2. **`ask_user_selection`**: Displays the found repositories and interrupts execution to wait for user selection.
3. **`advance_loop`**: Manages the queue of selected repositories, transitioning from one repository to the next once processing is complete.
4. **`call_model`**: The main agent node. Formulates prompts using the workspace context, long-term memory preferences, and short-term message history.
5. **`tools`**: Executes tool calls requested by the model (e.g., reading files, writing READMEs, committing changes).
6. **`reflect`**: Reviews the conversation history to identify and persist long-term developer preferences in the profile scratchpad, then interrupts for user feedback.

---

## Custom State Reducers & Gemini Compatibility

Because Gemini models require strict message ordering (e.g., every `ToolMessage` must follow an `AIMessage` with matching tool calls, and the conversation history must start with a valid `HumanMessage` or `AIMessage`), a custom message reducer `messages_state_operator` was developed. 

This reducer:
- Limits the conversation history to a maximum of 15 messages to prevent context bloat.
- Dynamically trims older messages while ensuring that the sliced history always begins with a valid, non-orphaned message (a regular `HumanMessage` or an `AIMessage` without pending tool calls).
- Prevents API validation errors from Gemini when resuming interrupted threads or executing multiple tool-calling loops.

---

## Repository Structure

- **`agent.py`**: Defines the `AgentState`, custom reducers, graph nodes, conditional routing logic, and compiles the LangGraph workflow.
- **`tools.py`**: Contains the tool definitions:
  - `read_local_codebase`: Recursively lists files in a directory (filtering out build/virtual environment folders).
  - `read_file_contents`: Reads text files and parses Jupyter Notebooks (stripping cell outputs).
  - `write_readme_file`: Writes the generated Markdown content to `README.md`.
  - `commit_and_push_changes`: Pulls, commits, and pushes changes to the repository.
- **`prompts.py`**: Contains the system prompts and reflection prompts used by the LLM.
- **`main.py`**: The interactive terminal execution loop that manages the human-in-the-loop interrupts and resumes the graph.
- **`trials.py`**: A simple testing script to verify codebase reading functionality.
- **`langgraph.json`**: Configuration file for deploying the graph.

---

## Installation

To set up and run `readme_agent` locally, follow these steps:

1. **Clone the Repository**:
   ```bash
   git clone <repository-url>
   cd readme_agent
   ```

2. **Install Dependencies**:
   Install all required dependencies via the provided `requirements.txt` file:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Create a `secrets.env` file and a `paths.env` file in the root directory:
   
   **`secrets.env`**:
   ```env
   GOOGLE_API_KEY=your_google_gemini_api_key
   ```
   
   **`paths.env`**:
   ```env
   WORKSPACE_DIR=/path/to/your/local/workspace
   ```

---

## Usage

To start the interactive documentation assistant, run:

```bash
python main.py
```

### Workflow Example:
1. The agent will scan your `WORKSPACE_DIR` and list all discovered repositories.
2. Enter the names of the repositories you want to process (comma-separated).
3. The agent will automatically read the codebase of the first repository, generate a comprehensive `README.md`, write it to disk, and prompt you for feedback.
4. If you are satisfied, type `yes` to commit/push the changes and proceed to the next repository. If you want changes, type your feedback, and the agent will refine the README accordingly.
