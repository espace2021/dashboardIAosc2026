import json
import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI


load_dotenv()



def get_llm(
        model="gemini-2.5-flash",
        temperature=0
):
    """
    Retourne une instance Gemini LangChain.
    """

    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        google_api_key=os.getenv(
            "GOOGLE_API_KEY"
        )
    )



def get_llm_with_tools(tools):
    """
    Retourne Gemini avec les tools MCP associés.
    """

    llm = get_llm(
        model="gemini-2.5-flash",
        temperature=0
    )

    return llm.bind_tools(
        tools
    )



def call_gemini_json(
        prompt,
        model="gemini-2.5-flash",
        temperature=0.2
):
    """
    Appel Gemini avec réponse JSON.
    Utilisé par les skills
    (ex: skill-3-generation-insights).
    """


    llm = get_llm(
        model=model,
        temperature=temperature
    )


    response = llm.invoke(
        prompt
    )


    content = response.content


    # Suppression éventuelle du markdown JSON
    content = (
        content
        .replace("```json", "")
        .replace("```", "")
        .strip()
    )


    return json.loads(content)