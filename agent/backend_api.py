from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Fix absolute imports by referencing the agent module or relative imports
from agent.orchestrator.agent import build_email_agent, run_agent_with_gates
from agent.providers.groq_provider import GroqProvider

app = FastAPI(title="AI Behavior Monitoring API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

provider = GroqProvider()
llm_with_tools = build_email_agent(provider)

class PromptRequest(BaseModel):
    prompt: str

@app.post("/api/prompt")
async def evaluate_prompt(request: PromptRequest):
    result = run_agent_with_gates(llm_with_tools, request.prompt)
    return {"status": "ok", "response": str(result)}

if __name__ == "__main__":
    uvicorn.run("agent.backend_api:app", host="0.0.0.0", port=8000, reload=True)