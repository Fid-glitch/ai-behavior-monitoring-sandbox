# orchestrator/agent.py
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage
from tools.tool_actions import TOOLS
import json

def build_email_agent(provider):
    """
    Build email assistant agent with LangChain tool integration.
    """
    llm = provider.llm  # Use .llm directly
    llm_with_tools = llm.bind_tools(TOOLS)
    return llm_with_tools


def run_agent(llm_with_tools, user_query):
    """
    Run agent loop: query → LLM → tool call → tool execution → response
    """
    messages = [HumanMessage(content=user_query)]
    
    # Get LLM response with tool calls
    response = llm_with_tools.invoke(messages)
    
    print("\n[LLM Response]")
    print(f"Content: {response.content}")
    
    # Check if tool calls were made
    if hasattr(response, 'tool_calls') and response.tool_calls:
        print(f"\n[Tool Calls Detected: {len(response.tool_calls)}]")
        for tool_call in response.tool_calls:
            print(f"  - Tool: {tool_call['name']}")
            print(f"  - Args: {tool_call['args']}")
            
            # Execute tool
            for tool in TOOLS:
                if tool.name == tool_call['name']:
                    tool_result = tool.invoke(tool_call['args'])
                    print(f"\n[Tool Output]")
                    print(tool_result[:500])  # Print first 500 chars
                    break
    else:
        print("\n[No tool calls made]")
    
    return response


if __name__ == "__main__":
    from providers.groq_provider import GroqProvider
    from dotenv import load_dotenv
    
    load_dotenv()
    
    print("\n" + "="*70)
    print("TEST: Email Search Query")
    print("="*70 + "\n")
    
    # Build agent
    provider = GroqProvider()
    llm_with_tools = build_email_agent(provider)
    
    # Run agent
    response = run_agent(
        llm_with_tools,
        "Search for all emails and show me their contents"
    )