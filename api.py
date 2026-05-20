from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict
from langchain_core.messages import HumanMessage, AIMessage
from main import app as langgraph_graph

app = FastAPI(title="IT-Support Chatbot API", version="1.0")


class ChatRequest(BaseModel):
    """
    datastructure for frontend requests
    """
    user_message: str
    history: List[Dict[str, str]]  # Format: [{"role": "user", "content": "Hallo"}, {"role": "bot", "content": "Hi"}]
    customer_name: str = ""
    matrikelnummer: str = ""
    issue_description: str = ""


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    API Endpoint to chat with the llm
    :param request: the state of the conversation
    :return: returns the updated state, after the llm processed the request
    """
    # translates JSON objects into LangChain objects
    langchain_messages = []
    for msg in request.history:
        if msg["role"] == "user":
            langchain_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "bot":
            langchain_messages.append(AIMessage(content=msg["content"]))

    langchain_messages.append(HumanMessage(content=request.user_message))

    current_state = {
        "messages": langchain_messages,
        "customer_name": request.customer_name,
        "matrikelnummer": request.matrikelnummer,
        "issue_description": request.issue_description,
        "is_complete": False
    }

    updated_state = langgraph_graph.invoke(current_state)
    bot_response = updated_state["messages"][-1].content
    return {
        "bot_response": bot_response,
        "customer_name": updated_state.get("customer_name", ""),
        "matrikelnummer": updated_state.get("matrikelnummer", ""),
        "issue_description": updated_state.get("issue_description", ""),
        "is_complete": updated_state.get("is_complete", False)
    }