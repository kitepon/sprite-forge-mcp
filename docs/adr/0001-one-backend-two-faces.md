# ADR 0001 — One Backend, Two Faces

- Status: Accepted
- Date: 2026-07-04

## Context

README and CLAUDE.md define sprite-forge-mcp as one Python backend with two user surfaces: a FastAPI WebUI for humans and a FastMCP server for agents. Both surfaces call `backend/services.py`.

The project also requires production gates for transparency, pose/bbox alignment, mandatory style phrasing, and explicit adoption. Those gates must not diverge between human and agent use.

## Decision

Keep FastAPI and FastMCP in the same `uvicorn` process and route both through the shared service layer in `backend/services.py`.

ComfyUI remains the generation engine behind the backend. The backend is responsible for orchestration, deterministic post-processing, auditing, and adoption gates.

## Consequences

- WebUI and MCP behavior stay aligned because they share implementation.
- Gate logic has one enforcement point.
- The MCP server depends on the backend process being up; MCP registration alone is not enough.
- Changes to gate behavior must be made in the service layer, not separately in UI or MCP wrappers.
