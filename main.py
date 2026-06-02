import os
import uuid
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

# Import the builder directly from your agent file
from agent import builder

load_dotenv("secrets.env")
load_dotenv("paths.env")

def run_interactive_agent():
    local_checkpointer = MemorySaver()
    local_store = InMemoryStore()
    
    # Compile the graph matching your local runtime requirements
    executable_graph = builder.compile(
        checkpointer=local_checkpointer, 
        store=local_store,
        interrupt_after=["ask_user_selection", "reflect"]
    )
    
    config = {
        "configurable": {
            "thread_id": str(uuid.uuid4()),
            "user_id": "efe_local_dev"
        }
    }
    
    print("🚀 Git Agent Initialized locally via terminal execution loop.")
    print("Type 'exit' to quit at any prompt.")
    print("-" * 60)
    
    # First kick off: start the graph from the beginning
    inputs = {"messages": []}
    
    while True:
        # Stream the graph execution until it finishes or hits an interrupt hook
        for event in executable_graph.stream(inputs, config, stream_mode="updates"):
            # Print out standard node message emissions so you can see progress in terminal
            for node_name, node_output in event.items():
                if "messages" in node_output and node_output["messages"]:
                    last_msg = node_output["messages"][-1]
                    if isinstance(last_msg, AIMessage):
                        print(f"\nBot: {last_msg.content}")

        # Fetch the current state snapshot to check if we are interrupted
        state_snapshot = executable_graph.get_state(config)
        
        # If there are no more tasks waiting, the graph has reached END cleanly
        if not state_snapshot.next:
            print("\n🎉 Graph execution finished processing successfully.")
            break
            
        current_interrupt_node = state_snapshot.next[0]
        
        # Accept terminal input from the engineer
        user_input = input("\nYou: ")
        if user_input.lower().strip() == "exit":
            print("Exiting thread execution loop.")
            break
            
        if not user_input.strip():
            inputs = None  # Resume without sending anything new
            continue

        # Route updates back into the graph depending on which node interrupted execution
        if current_interrupt_node == "ask_user_selection":
            # Extract names from user input comma array
            selected_repos = [r.strip() for r in user_input.split(",") if r.strip()]
            
            # Update state with target repos and set the initial tracking target repo
            executable_graph.update_state(
                config,
                {
                    "target_repos": selected_repos,
                    "current_repo": selected_repos[0] if selected_repos else None,
                    "messages": [HumanMessage(content=user_input)]
                }
            )
        elif current_interrupt_node == "reflect":
            # Update user feedback criteria configuration
            executable_graph.update_state(
                config,
                {
                    "further_user_request": user_input,
                    "messages": [HumanMessage(content=user_input)]
                }
            )
            
        # Set inputs to None to signal LangGraph to resume right from where it paused
        inputs = None

if __name__ == "__main__":
    run_interactive_agent()