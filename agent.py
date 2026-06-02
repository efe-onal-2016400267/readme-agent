import os
import uuid
from dotenv import load_dotenv
from typing import Literal, List, Optional, Annotated, Union, Any
from pydantic import BaseModel, Field
from operator import add

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage, ToolMessage, AnyMessage
from langchain_core.runnables.config import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from tools import read_local_codebase, write_readme_file, commit_and_push_changes, read_file_contents
from prompts import BASE_SYSTEM_PROMPT, REFLECTION_PROMPT

load_dotenv("secrets.env")
load_dotenv("paths.env")

WORKSPACE_DIR = os.getenv("WORKSPACE_DIR")

# Model config and tool binding
model = ChatGoogleGenerativeAI(model="gemini-3.5-flash", temperature=0.2)
tools = [read_local_codebase, write_readme_file, commit_and_push_changes, read_file_contents]
model_with_tools = model.bind_tools(tools)

def append_strings_reducer(left: List[str], right: Union[str, List[str]]) -> List[str]:
    """
    A Pydantic-safe list reducer that mirrors operator.add, 
    but filters out structural initialization placeholders.
    """
    # Initialize the baseline list
    current_list = list(left) if left else []
    
    # Handle list-type updates (e.g., returning [] or ["repo-name"])
    if isinstance(right, list):
        # Only append items that are actual valid strings, ignoring empty nested arrays
        clean_updates = [item for item in right if isinstance(item, str) and item]
        return current_list + clean_updates
        
    # Handle single string updates (if a node returns a raw string instead of a list)
    if isinstance(right, str) and right:
        return current_list + [right]
        
    return current_list

def messages_state_operator(
    left: List[BaseMessage],
    right: List[BaseMessage]
) -> List[BaseMessage]:
    MAX_MESSAGES = 15

    current = list(left) if left else []

    if isinstance(right, list):
        new = right
    else:
        new = [right]

    combined = current + new
    split_index = None
    # We find the last instance of a regular Human or AI message and trim the history before it
    for i in range(1, len(combined) + 1):
        if i >= MAX_MESSAGES:
            msg = combined[-i]
            if isinstance(msg, HumanMessage) or (isinstance(msg, AIMessage) and msg.tool_calls in (None, [])):
                split_index = len(combined) - i
                break
                   
    if split_index is not None:
        return combined[split_index:]
    else:
        return combined
    


class SelectedRepos(BaseModel):
    """The list of repositories the user wants to process."""
    repo_names: List[str] = Field(default=[], description="A clean list of individual repository directory names extracted from the input text.")


class AgentState(BaseModel):
    messages: Annotated[List[AnyMessage], messages_state_operator] = Field(default_factory=list)
    discovered_repos: List[str] = Field(default_factory=list)
    target_repos: List[str] = Field(default_factory=list)
    done_repos: Annotated[List[str], append_strings_reducer] = Field(default_factory=list)
    current_repo: Optional[str] = None
    further_user_request: Optional[str] = None
    last_node: Annotated[List[str], append_strings_reducer] = Field(default_factory=list)

def discover_workspace_repos(state: AgentState):
    """
    Scan workspace directory for folders. Each folder is a potential git repository. Update the state with discovered repo names.
    """
    try:
        repos = [
            d for d in os.listdir(WORKSPACE_DIR) 
            if os.path.isdir(os.path.join(WORKSPACE_DIR, d)) and not d.startswith(".")
        ]
        return {"discovered_repos": repos, "last_node": ["discover_repos"]}
    except Exception as e:
        return {"discovered_repos": [], "last_node": ["discover_repos"]}

def ask_user_for_repo_selection(state: AgentState):
    """
    Displays the found repos for the user and asks for a selection to be processed.
    The user selects any repo by typing its name, separated by commas.
    """
    repo_list_str = "\n".join(f"* {repo}" for repo in state.discovered_repos)

    msg = AIMessage(content=f"I found the following repositories in your workspace:\n{repo_list_str}\n\nPlease type the names of the repositories you want me to process.")
    return {"messages": [msg], "last_node": ["ask_user_selection"]}

def call_model(state: AgentState, config: RunnableConfig, store:BaseStore):
    """
    Main agent node. Reads short term messages and long term memory.
    """

    user_id = config["configurable"].get("user_id")
    if not user_id:
        user_id = "default_user"
    
    # The name space
    namespace = ("profile", user_id)
    # The field, key
    key = "profile_scratchpad"

    existing_memory = store.get(namespace, key)
    long_term_memory = existing_memory.value.get("content", "No specific formatting or project preferences recorded yet.") if existing_memory else "No preferences recorded yet."

    current_repo = state.current_repo

    repo_context = (
        f"\n\n[TARGET REPOSITORY CONTEXT]\n"
        f"You are explicitly assigned to work ONLY on the repository directory: '{current_repo}'.\n"
        f"You must use your tools to analyze and write the README for this directory ONLY.\n"
        f"Once you have finished writing or committing the README for this repository, stop and inform the user. Do not attempt to guess or process any other folders."
    )
    target_repos = state.target_repos
    repos_to_process_str = "\n".join(f"* {r}" for r in target_repos) if target_repos else "No repositories selected yet."

    

    if state.last_node[-2] != "call_model":
        human_request = HumanMessage(content=f"Please continue working on the current repository: {state.current_repo}. Remember to follow the instructions and use the tools at your disposal.")
    else:
        human_request = None
    

    # Format base system prompt with workspace and long term memory
    formatted_system_prompt = BASE_SYSTEM_PROMPT.format(WORKSPACE_DIR=WORKSPACE_DIR, long_term_memory=long_term_memory, repos_to_process=repos_to_process_str) + repo_context

    # Run the model turn
    if human_request:
        response = model_with_tools.invoke([SystemMessage(content=formatted_system_prompt)] + state.messages + [human_request])
    else:
        response = model_with_tools.invoke([SystemMessage(content=formatted_system_prompt)] + state.messages)
    return {"messages": [response], "last_node": ["call_model"]}


def reflect_on_profile(state: AgentState, config: RunnableConfig, store:BaseStore):
    """
    Reflection node. Reviews the conversation and updates long term memory if needed.
    """

    user_id = config["configurable"].get("user_id")
    if not user_id:
        user_id = "default_user"
    namespace = ("profile", user_id)
    key = "profile_scratchpad"

    existing_memory = store.get(namespace, key)
    current_scratchpad = existing_memory.value.get("content", "Empty scratchpad.") if existing_memory else "Empty scratchpad."

    # Flatten histoty into a single string for the model
    human_lines = [f"User: {m.content}" for m in state.messages if isinstance(m, HumanMessage)]
    history_str = "\n".join(human_lines)

    eval_prompt = f"{REFLECTION_PROMPT.format(current_scratchpad=current_scratchpad)}\n\n--- RECENT HISTORY ---\n{history_str}"
    response = model.invoke([HumanMessage(content=eval_prompt)])
    new_scratchpad_content = response.content[0]["text"].strip()

    # Save back to the memory store
    store.put(namespace, key, {"content": new_scratchpad_content})
    return {"messages": [AIMessage(content=f"Are you satisfied with the generated README for repo: {state.current_repo}? If yes, type 'yes'. If not, please provide more details on how I can improve."),],
            "last_node": ["reflect"],}

def advance_loop(state: AgentState):
    """
    Transitions the queue of selected repos. Moves the to done pops the next repo.
    """
    further_user_request = state.further_user_request
    if not further_user_request or further_user_request.lower() == "yes":
        remaining = [r for r in state.target_repos if r not in state.done_repos and r != state.current_repo]

        newly_done = state.current_repo if state.current_repo else []

        next_repo_queue = [r for r in remaining if r != state.current_repo]
        next_repo = next_repo_queue[0] if next_repo_queue else None
        if next_repo:
            thank_you_msg = HumanMessage(content=f"Great! Moving on to the next repository: {next_repo}.")
        else:
            thank_you_msg = HumanMessage(content=f"Great! All repositories are done. Thank you my sweet minnion!")
        return {
            #"messages": [thank_you_msg],
            "done_repos": [newly_done],
            "current_repo": next_repo,
            "further_user_request": None,
            "last_node": ["advance_loop"]
        }
    else:
        msg = HumanMessage(further_user_request)
        return {"messages": [msg], "further_user_request": None, "last_node": ["advance_loop"]}



def route_after_model(state: AgentState, config: RunnableConfig, store:BaseStore) -> Literal["tools", "reflect"]:
    """
    Routing node. Decides whether to call tools or reflect based on the model's response.
    """
    last_message = state.messages[-1] if state.messages else None
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    else:
        return "reflect"
    

def route_after_advance_loop(state: AgentState, config: RunnableConfig, store:BaseStore) -> Literal["call_model", "__end__"]:
    """
    Check if all selected user repos are done. If yes, end the graph. If not, loop back to the model for another turn.
    """
    remaining = [r for r in state.target_repos if r not in state.done_repos]
    if remaining:
        return "call_model"
    else:
        return "__end__"

    

builder = StateGraph(AgentState)

builder.add_node("discover_repos", discover_workspace_repos)
builder.add_node("ask_user_selection", ask_user_for_repo_selection)
builder.add_node("call_model", call_model)
builder.add_node("advance_loop", advance_loop)
builder.add_node("tools", ToolNode(tools=tools))
builder.add_node("reflect", reflect_on_profile)

builder.add_edge(START, "discover_repos")
builder.add_edge("discover_repos", "ask_user_selection")
builder.add_edge("ask_user_selection", "advance_loop")
builder.add_conditional_edges("call_model", route_after_model)
builder.add_edge("tools", "call_model")
builder.add_edge("reflect", "advance_loop")

builder.add_conditional_edges(
    "advance_loop",
    route_after_advance_loop,
    {
        "call_model": "call_model",
        "__end__": END
    }
)

long_term_store = InMemoryStore()
short_term_checkpointer = MemorySaver()

#graph = builder.compile(checkpointer=short_term_checkpointer, store=long_term_store)
graph = builder.compile(interrupt_after=["ask_user_selection", "reflect"])