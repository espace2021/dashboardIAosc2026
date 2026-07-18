"""
agent_dashboard.py

Agent Dashboard MCP avec Gemini via LangChain.

Architecture :

User
 |
agent_dashboard.py
 |
ChatGoogleGenerativeAI
 |
LangChain Tool Calling
 |
FastMCP Tools
 |
Dashboard HTML
"""

import asyncio
import datetime as dt
import json
import os
import sys
import webbrowser

from pathlib import Path

from dotenv import load_dotenv
from fastmcp import Client

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    ToolMessage
)

from langchain_core.tools import StructuredTool

from pydantic import create_model


# =====================================================
# Import service Gemini
# =====================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT)
    )


from services.gemini_service import get_llm_with_tools



load_dotenv()



# =====================================================
# Configuration
# =====================================================

MCP_SERVER_URL = (
    "http://127.0.0.1:8000/mcp"
)


OUTPUT_HTML = Path(
    "dashboard_africa.html"
)


MAX_STEPS = 8



SKILL_PATH = (
    Path(__file__).parent.parent
    /
    "skills"
    /
    "skill-orchestrateur-agent.md"
)



# =====================================================
# Extraction résultat MCP
# =====================================================

def _tool_result_to_value(result):

    if getattr(result,"data",None) is not None:
        return result.data


    if getattr(result,"structured_content",None) is not None:
        return result.structured_content


    text = result.content[0].text


    try:
        return json.loads(text)

    except Exception:
        return text



# =====================================================
# Création schema Pydantic depuis MCP
# =====================================================

def build_args_schema(mcp_tool):

    schema = (
        mcp_tool.inputSchema
        or {}
    )


    properties = schema.get(
        "properties",
        {}
    )


    required = schema.get(
        "required",
        []
    )


    fields = {}


    for name,info in properties.items():


        t = object


        typ = info.get(
            "type"
        )


        if typ == "string":
            t = str

        elif typ == "integer":
            t = int

        elif typ == "number":
            t = float

        elif typ == "boolean":
            t = bool

        elif typ == "array":
            t = list

        elif typ == "object":
            t = dict



        default = ...


        if name not in required:
            default = None



        fields[name] = (
            t,
            default
        )



    return create_model(
        f"{mcp_tool.name}_Args",
        **fields
    )



# =====================================================
# Conversion MCP -> LangChain Tool
# =====================================================

def create_tool(
        mcp_client,
        mcp_tool
):


    async def call_tool(**arguments):


        # Correction Gemini/LangChain
        # suppression encapsulation inutile

        if "kwargs" in arguments:
            arguments = arguments["kwargs"]


        if "arguments" in arguments:
            arguments = arguments["arguments"]



        print(
            "\nArguments MCP envoyés :",
            arguments
        )


        result = await mcp_client.call_tool(
            mcp_tool.name,
            arguments
        )


        return _tool_result_to_value(
            result
        )



    ArgsSchema = build_args_schema(
        mcp_tool
    )



    return StructuredTool.from_function(
        coroutine=call_tool,
        name=mcp_tool.name,
        description=(
            mcp_tool.description
            or ""
        ),
        args_schema=ArgsSchema
    )



def create_langchain_tools(
        mcp_client,
        mcp_tools
):

    return [
        create_tool(
            mcp_client,
            tool
        )
        for tool in mcp_tools
    ]



# =====================================================
# Agent ReAct
# =====================================================

async def run_agent(prompt:str):


    async with Client(
        MCP_SERVER_URL
    ) as mcp_client:


        print(
            "\nChargement des tools MCP..."
        )


        mcp_tools = await mcp_client.list_tools()



        print(
            f"{len(mcp_tools)} tools disponibles"
        )



        tools = create_langchain_tools(
            mcp_client,
            mcp_tools
        )



        llm = get_llm_with_tools(
            tools
        )



        skill_prompt = SKILL_PATH.read_text(
            encoding="utf-8"
        )



        today = dt.date.today().isoformat()



        messages = [

            SystemMessage(
                content=skill_prompt
            ),


            HumanMessage(
                content=f"""
Nous sommes le {today}.

Demande utilisateur :

{prompt}

Utilise les tools MCP nécessaires.
Quand les données sont disponibles,
utilise generate_dashboard_html.
"""
            )
        ]



        for step in range(MAX_STEPS):


            print(
                f"\nEtape {step+1}"
            )


            response = llm.invoke(
                messages
            )


            messages.append(
                response
            )



            if not response.tool_calls:

                return response.content



            for tool_call in response.tool_calls:


                name = tool_call["name"]


                args = dict(
                    tool_call["args"]
                )



                print(
                    "\nTool appelé :",
                    name
                )


                print(
                    args
                )



                # correction JSON string

                for key,value in list(args.items()):

                    if isinstance(value,str):

                        value=value.strip()

                        if (
                            value.startswith("[")
                            or
                            value.startswith("{")
                        ):

                            try:
                                args[key]=json.loads(value)

                            except:
                                pass



                try:


                    result = await mcp_client.call_tool(
                        name,
                        args
                    )


                    value = _tool_result_to_value(
                        result
                    )


                except Exception as exc:


                    value={
                        "error":str(exc)
                    }


                    print(
                        "Erreur tool:",
                        exc
                    )



                # Tool final

                if (
                    name ==
                    "generate_dashboard_html"
                    and isinstance(value,str)
                ):

                    return value



                messages.append(

                    ToolMessage(
                        content=json.dumps(
                            value,
                            ensure_ascii=False
                        ),
                        tool_call_id=
                            tool_call["id"]
                    )
                )



        return (
            "Nombre maximum d'étapes atteint."
        )



# =====================================================
# Main
# =====================================================

async def main(prompt):


    print(
        "\nPrompt :",
        prompt
    )



    result = await run_agent(
        prompt
    )



    if not (
        result.startswith("<!DOCTYPE")
        or
        result.startswith("<html")
    ):

        print(result)
        return



    OUTPUT_HTML.write_text(
        result,
        encoding="utf-8"
    )



    print(
        "\nDashboard créé :",
        OUTPUT_HTML.resolve()
    )



    webbrowser.open(
        OUTPUT_HTML.resolve().as_uri()
    )



if __name__ == "__main__":


    prompt = (
        " ".join(sys.argv[1:])
        if len(sys.argv)>1
        else input(
            "Décrivez le dashboard voulu : "
        )
    )


    asyncio.run(
        main(prompt)
    )