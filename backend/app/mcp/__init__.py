"""
QuantX — Model Context Protocol integration.

``handlers`` holds the framework-free core (testable without the ``mcp``
package); ``server`` wires it onto the MCP stdio transport and is imported only
when the server is actually run.
"""

from __future__ import annotations

from app.mcp.handlers import handle_call, list_tool_specs

__all__ = ["handle_call", "list_tool_specs"]
