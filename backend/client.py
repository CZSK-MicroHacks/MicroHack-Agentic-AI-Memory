# client.py
import asyncio
import os
from dotenv import load_dotenv
from agent_framework import Agent
from agent_framework_ag_ui import AGUIChatClient

# Load environment variables from .env file
load_dotenv()

async def interactive_chat():
    """Interactive chat session with streaming responses."""
    
    # Connect to the AG-UI server
    base_url = os.getenv("AGUI_SERVER_URL", "http://localhost:8000/chat")
    print(f"Connecting to: {base_url}\n")
    
    # Initialize the AG-UI client
    client = AGUIChatClient(endpoint=base_url)
    
    # Create a local agent representation
    agent = Agent(client=client)
    
    # Start a new conversation session
    conversation_thread = agent.create_session()
    
    print("Chat started! Type 'exit' or 'quit' to end the session.\n")
    
    try:
        while True:
            # Collect user input
            user_message = input("You: ")
            
            # Handle empty input
            if not user_message.strip():
                print("Please enter a message.\n")
                continue
            
            # Check for exit commands
            if user_message.lower() in ["exit", "quit", "bye"]:
                print("\nGoodbye!")
                break
            
            # Stream the agent's response
            print("Agent: ", end="", flush=True)
            
            # Track tool calls to avoid duplicate prints
            seen_tools = set()
            
            async for update in agent.run(user_message, stream=True, session=conversation_thread):
                # Display text content
                if update.text:
                    print(update.text, end="", flush=True)
                
                # Display tool calls and results from contents
                for content in update.contents:
                    content_dict = content.to_dict() if hasattr(content, 'to_dict') else {}
                    content_type = content_dict.get('type', '')
                    
                    if content_type == 'function_call':
                        call_id = content_dict.get('call_id', '')
                        if call_id and call_id not in seen_tools:
                            seen_tools.add(call_id)
                            name = content_dict.get('name', 'unknown')
                            print(f"\n[Calling tool: {name}]", flush=True)
                    elif content_type == 'function_result':
                        call_id = content_dict.get('call_id', '')
                        result_id = f"result_{call_id}"
                        if result_id not in seen_tools:
                            seen_tools.add(result_id)
                            result_text = content_dict.get('result', '')
                            if isinstance(result_text, dict):
                                result_text = str(result_text)
                            print(f"[Tool result: {result_text}]", flush=True)
            
            print("\n")  # New line after response completes
            
    except KeyboardInterrupt:
        print("\n\nChat interrupted by user.")
    except ConnectionError as e:
        print(f"\nConnection error: {e}")
        print("Make sure the server is running.")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Entry point for the AG-UI client."""
    asyncio.run(interactive_chat())

if __name__ == "__main__":
    main()
