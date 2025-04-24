#!/usr/bin/env python3
"""
Ollama Scanner Filter Function for OpenWebUI
-------------------------------------------
This function integrates the Ollama Scanner into OpenWebUI
using the Filter Function architecture.
"""

from typing import Dict, List, Optional, Union, Callable, Awaitable
from pydantic import BaseModel, Field

class Filter:
    """
    Ollama Scanner Filter Function for OpenWebUI.
    
    This filter provides capabilities to:
    1. Discover Ollama instances using Shodan
    2. Search and filter discovered instances
    3. Add discovered instances as endpoints in OpenWebUI
    """
    
    class Valves(BaseModel):
        """
        System configurable values (admin settings)
        """
        SHODAN_API_KEY: str = Field(
            default="",
            description="Shodan API key for scanning Ollama instances"
        )
        MAX_RESULTS: int = Field(
            default=100,
            description="Maximum number of results to return from a scan"
        )
    
    class UserValves(BaseModel):
        """
        User configurable values (per-user settings)
        """
        enable_scanner: bool = Field(
            default=True,
            description="Enable Ollama Scanner features"
        )
    
    def __init__(self):
        """Initialize the filter"""
        self.valves = self.Valves()
    
    async def inlet(
        self,
        query: str,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        __user__: Optional[dict] = None
    ) -> str:
        """
        Process the input message before it goes to the LLM.
        This is where we can add context about Ollama Scanner features.
        
        Args:
            query: The user's input message
            __event_emitter__: An event emitter function for streaming responses
            __user__: User information including valves
            
        Returns:
            str: The processed input message
        """
        # Check if Ollama Scanner related query
        scanner_keywords = [
            "ollama scanner", "find ollama", "discover ollama", 
            "search for ollama", "scan for ollama"
        ]
        
        # Get the user valves if available
        user_valves = None
        if __user__ and "valves" in __user__:
            user_valves = __user__["valves"]
        
        # Only modify the query if the scanner is enabled for this user
        is_enabled = True
        if user_valves and hasattr(user_valves, "enable_scanner"):
            is_enabled = user_valves.enable_scanner
        
        if is_enabled and any(keyword in query.lower() for keyword in scanner_keywords):
            # Add context about Ollama Scanner to the user's query
            return (
                f"{query}\n\n"
                "Note: You can use the Ollama Scanner feature to discover and connect to Ollama instances. "
                "Go to Admin Panel > Ollama Scanner to use this feature. "
                "The scanner requires a Shodan API key to search for instances."
            )
        
        return query
    
    async def stream(
        self,
        chunk: str,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        __user__: Optional[dict] = None
    ) -> str:
        """
        Process each chunk of the LLM's response as it's generated.
        We simply pass through the chunks unchanged.
        
        Args:
            chunk: A chunk of the model's response
            __event_emitter__: An event emitter function
            __user__: User information
            
        Returns:
            str: The processed chunk
        """
        return chunk
    
    async def outlet(
        self,
        response: str,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        __user__: Optional[dict] = None
    ) -> str:
        """
        Process the complete LLM response after it's been generated.
        
        Args:
            response: The complete response from the LLM
            __event_emitter__: An event emitter function
            __user__: User information
            
        Returns:
            str: The processed response
        """
        # Check if we need to process the response
        scanner_related = any(term in response.lower() for term in [
            "ollama scanner", "scan ollama", "discover ollama", "ollama instances"
        ])
        
        # Get the user valves if available
        user_valves = None
        if __user__ and "valves" in __user__:
            user_valves = __user__["valves"]
        
        # Only modify the response if the scanner is enabled for this user
        is_enabled = True
        if user_valves and hasattr(user_valves, "enable_scanner"):
            is_enabled = user_valves.enable_scanner
        
        if is_enabled and scanner_related:
            # Add a note about accessing the scanner UI
            footer = (
                "\n\n---\n"
                "**Ollama Scanner Note**: To use the Ollama Scanner, visit the Admin Panel and navigate to "
                "the Ollama Scanner section. You'll need a Shodan API key to scan for instances."
            )
            return response + footer
        
        return response 