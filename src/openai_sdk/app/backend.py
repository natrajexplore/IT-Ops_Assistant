"""FastAPI backend for the IT Ops multi-team dashboard.

Each sidebar "team" is backed by a real agent with its own domain persona.
Two agent instances per team share one SQLiteSession (per Step 6): a
"reporter" agent (structured output_type=TeamReport, per Step 4) used for the
dashboard view, and a "chat" agent (freeform text) for ad hoc questions -
switching modes doesn't lose context since both read/write the same session.

Change requests ("propose_change_request", per Step 5's needs_approval=True)
generalize the approval flow already proven in this app: any team can
propose a weekend-planned or emergency-weekday change, which pauses the run
until the IT Ops manager approves or rejects it. Each CR carries a
configuration plan, an optional incident ID, the specific infra components it
touches (rendered as a diagram, highlighted, in the UI), and which other
teams should be aware of it. A CR row is created in SQLite the moment it's
proposed (status='pending') so it has a stable CR ID before any decision is
made, then updated in place once the manager decides.

Deliberately NOT included (kept as a focused demo, not the hardened
deployment stack from steps 11-14): API-key auth, Redis/multi-worker, rate
limiting. Single process, in-memory PENDING dict for in-flight approvals -
fine for a demo, not for production (a restart loses a run parked mid-approval).
"""

import json
import sqlite3
import subprocess
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import psutil
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents import Agent, RunState, Runner, SQLiteSession, ToolApprovalItem, function_tool

load_dotenv()

SESSIONS_DB_PATH = "ui_sessions.db"
CHANGE_REQUESTS_DB_PATH = "change_requests.db"

SIMULATION_NOTE = (
    "This is a training/demo environment with no live monitoring feeds wired "
    "in. When describing current observations (CVEs, alerts, findings), "
    "always clearly frame them as illustrative example scenarios for this "
    "exercise - never claim they are verified real-world data."
)


# --- Shared real tools -------------------------------------------------

@function_tool
def check_host_reachable(host: str) -> str:
    """Check whether a host responds to a real network ping. Read-only.

    Args:
        host: Hostname or IP to ping.
    """
    result = subprocess.run(
        ["ping", "-n", "1", "-w", "1000", host],
        capture_output=True,
        text=True,
    )
    reachable = result.returncode == 0
    return f"{host}: {'REACHABLE' if reachable else 'UNREACHABLE'} (real ping, exit code {result.returncode})"


@function_tool
def list_top_processes(limit: int = 5) -> str:
    """List the top processes on this machine by memory usage. Real data, read-only.

    Args:
        limit: How many processes to return.
    """
    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            mem_mb = p.info["memory_info"].rss / (1024 * 1024)
            procs.append((mem_mb, p.info["pid"], p.info["name"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(reverse=True)
    lines = [f"{name} (pid={pid}): {mem:.1f}MB" for mem, pid, name in procs[:limit]]
    return "\n".join(lines)


@function_tool(needs_approval=True)
def propose_change_request(
    title: str,
    description: str,
    configuration_plan: str,
    change_type: str,
    risk: str,
    affected_components: list[str],
    incident_id: str = "",
    impacted_teams: list[str] | None = None,
) -> str:
    """Propose a change request to the IT Ops manager. Pauses for approval.

    Args:
        title: Short title of the proposed change.
        description: What will be done and why (a short summary).
        configuration_plan: Detailed, step-by-step configuration/implementation plan.
        change_type: "weekend_planned" (routine maintenance window) or
            "emergency_weekday" (urgent, can't wait for the weekend).
        risk: Risk level: "low", "medium", or "high".
        affected_components: The specific infra components this touches - use
            the exact component names from YOUR team's topology list, given in
            your instructions.
        incident_id: A realistic incident ID (e.g. "INC-20458") if this change
            is in direct response to a specific incident, otherwise leave empty.
        impacted_teams: Other team names (from the list given in your
            instructions) that should be aware of or coordinate on this change.
    """
    return f"Change request '{title}' approved by the IT Ops manager and logged ({change_type}, risk={risk})."


# --- Team definitions ----------------------------------------------------
# "topology" is an ordered list of the infra components each team owns/cares
# about - shown to the model (so affected_components uses matching names) and
# returned to the frontend (so it can render the same diagram, highlighting
# whichever nodes a given change request touches).

TEAMS = [
    {
        "id": "vuln-mgmt",
        "name": "Vulnerability Management",
        "icon": "\U0001f6e1️",
        "focus": (
            "You track CVEs affecting the company's infrastructure devices "
            "and plan mitigation - patching, config workarounds, or "
            "firmware/hardware upgrades."
        ),
        "tools": [],
        "topology": ["Core Switches", "Edge Switches", "Firewalls", "VPN Gateways",
                     "Wireless Controllers", "Servers"],
    },
    {
        "id": "ops-security",
        "name": "Ops Security (SOC)",
        "icon": "\U0001f512",
        "focus": (
            "You monitor for suspicious activity, security alerts, and "
            "endpoint anomalies across the environment, and coordinate "
            "incident response. You can check real host reachability and "
            "real running processes on this machine as part of your monitoring."
        ),
        "tools": [check_host_reachable, list_top_processes],
        "topology": ["Endpoints", "SIEM", "Firewalls", "Servers", "Identity Provider"],
    },
    {
        "id": "red-team",
        "name": "Red Team",
        "icon": "\U0001f5e1️",
        "focus": (
            "You run offensive security exercises against internal "
            "infrastructure to find exploitable weaknesses before real "
            "attackers do, and report findings with remediation recommendations."
        ),
        "tools": [],
        "topology": ["External Perimeter", "DMZ", "Internal Network", "Servers",
                     "Domain Controller"],
    },
    {
        "id": "wireless",
        "name": "Wireless Team",
        "icon": "\U0001f4f6",
        "focus": (
            "You manage the wireless LAN infrastructure - access points, "
            "wireless controllers, RF health, rogue AP detection, and "
            "firmware upgrades. You can check real reachability of wireless "
            "infrastructure hosts."
        ),
        "tools": [check_host_reachable],
        "topology": ["Internet", "Wireless Controller", "Access Points",
                     "Guest SSID", "Corporate SSID"],
    },
    {
        "id": "ise-nac",
        "name": "ISE / NAC Team",
        "icon": "\U0001faaa",
        "focus": (
            "You manage network access control (Cisco ISE / NAC): endpoint "
            "compliance, authentication policy, and posture enforcement. You "
            "can check real reachability of ISE nodes/PSNs."
        ),
        "tools": [check_host_reachable],
        "topology": ["Endpoints", "Access Switch (802.1X)", "ISE Policy Service Nodes",
                     "ISE Admin Node", "RADIUS / AD"],
    },
    {
        "id": "routing-domain",
        "name": "Routing Domain",
        "icon": "\U0001f310",
        "focus": (
            "You manage core/edge routing infrastructure (BGP/OSPF, route "
            "stability, WAN links) and plan device upgrades and config "
            "changes. You can check real reachability of routing infrastructure."
        ),
        "tools": [check_host_reachable],
        "topology": ["WAN Links", "Core Routers", "Distribution Routers",
                     "Access Layer", "Data Center"],
    },
    {
        "id": "firewall-ops",
        "name": "Firewall Ops",
        "icon": "\U0001f9f1",
        "focus": (
            "You manage firewall policy, rule reviews, and HA pairs, and "
            "plan policy or firmware changes. You can check real reachability "
            "of firewall management hosts."
        ),
        "tools": [check_host_reachable],
        "topology": ["Internet Edge", "Perimeter Firewall (HA Pair)", "DMZ",
                     "Internal Firewall", "Core Network"],
    },
]

ALL_TEAM_NAMES = [t["name"] for t in TEAMS]


class TeamReport(BaseModel):
    observations: str
    mitigation_plan: str


def _instructions_for(team: dict) -> str:
    other_teams = [n for n in ALL_TEAM_NAMES if n != team["name"]]
    return (
        f"You are the lead of the {team['name']} team, reporting to the IT "
        f"Ops manager. {team['focus']} {SIMULATION_NOTE} "
        f"Your infrastructure topology is: {', '.join(team['topology'])}. "
        "When something you plan to do needs a maintenance window or urgent "
        "action, call propose_change_request. Use affected_components from "
        "your topology list above. Set change_type to 'weekend_planned' for "
        "routine work scheduled in the weekend maintenance window, or "
        "'emergency_weekday' for something urgent that can't wait. If the "
        "change is a direct response to an incident, include a realistic "
        "incident_id (e.g. 'INC-20458'); otherwise leave it empty. If it "
        f"affects other teams' domains, list them in impacted_teams - choose "
        f"from: {', '.join(other_teams)}. Always state risk and reasoning. "
        "Be concise and concrete."
    )


# team_id -> {"meta": dict, "reporter": Agent, "chat": Agent}
teams_runtime: dict[str, dict] = {}

# request_id -> {"state", "items", "session_id", "team_id", "agent_kind", "cr_ids"}
PENDING: dict[str, dict] = {}


# --- Change request persistence ------------------------------------------

def init_change_requests_db() -> None:
    conn = sqlite3.connect(CHANGE_REQUESTS_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS change_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            configuration_plan TEXT NOT NULL DEFAULT '',
            change_type TEXT NOT NULL,
            risk TEXT NOT NULL,
            affected_components TEXT NOT NULL DEFAULT '[]',
            incident_id TEXT,
            impacted_teams TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            decided_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def create_pending_change_request(*, team_id: str, title: str, description: str,
                                   configuration_plan: str, change_type: str, risk: str,
                                   affected_components: list[str], incident_id: str,
                                   impacted_teams: list[str]) -> int:
    conn = sqlite3.connect(CHANGE_REQUESTS_DB_PATH)
    cur = conn.execute(
        "INSERT INTO change_requests "
        "(team_id, title, description, configuration_plan, change_type, risk, "
        " affected_components, incident_id, impacted_teams, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
        (team_id, title, description, configuration_plan, change_type, risk,
         json.dumps(affected_components), incident_id or None, json.dumps(impacted_teams),
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def finalize_change_request(row_id: int, decision: str) -> None:
    conn = sqlite3.connect(CHANGE_REQUESTS_DB_PATH)
    conn.execute(
        "UPDATE change_requests SET status = ?, decided_at = ? WHERE id = ?",
        (decision, datetime.now(timezone.utc).isoformat(), row_id),
    )
    conn.commit()
    conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["affected_components"] = json.loads(d["affected_components"] or "[]")
    d["impacted_teams"] = json.loads(d["impacted_teams"] or "[]")
    return d


def get_change_request(row_id: int) -> dict | None:
    conn = sqlite3.connect(CHANGE_REQUESTS_DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM change_requests WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def list_decided_change_requests(limit: int = 50) -> list[dict]:
    conn = sqlite3.connect(CHANGE_REQUESTS_DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM change_requests WHERE status != 'pending' "
        "ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_change_requests_db()
    for team in TEAMS:
        instructions = _instructions_for(team)
        tools = [*team["tools"], propose_change_request]
        reporter = Agent(
            name=f"{team['name']} (Reporter)",
            instructions=instructions,
            model="gpt-5.1",
            tools=tools,
            output_type=TeamReport,
        )
        chat = Agent(
            name=f"{team['name']} (Chat)",
            instructions=instructions,
            model="gpt-5.1",
            tools=tools,
        )
        teams_runtime[team["id"]] = {"meta": team, "reporter": reporter, "chat": chat}
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _team_or_404(team_id: str) -> dict:
    runtime = teams_runtime.get(team_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail=f"Unknown team '{team_id}'")
    return runtime


class ChangeRequestInfo(BaseModel):
    id: int
    team_id: str
    title: str
    description: str
    configuration_plan: str
    change_type: str
    risk: str
    affected_components: list[str]
    incident_id: str | None
    impacted_teams: list[str]
    status: str
    created_at: str
    decided_at: str | None


class PendingAction(BaseModel):
    call_id: str
    tool_name: str
    arguments: str
    change_request: ChangeRequestInfo | None = None


class ChatResponse(BaseModel):
    status: str  # "done" or "pending_approval"
    reply: str | None = None
    report: TeamReport | None = None
    request_id: str | None = None
    actions: list[PendingAction] | None = None


def _build_actions(items: list[ToolApprovalItem], cr_ids: dict[str, int]) -> list[PendingAction]:
    actions = []
    for item in items:
        cr = None
        row_id = cr_ids.get(item.call_id)
        if row_id is not None:
            record = get_change_request(row_id)
            if record:
                cr = ChangeRequestInfo(**record)
        actions.append(PendingAction(
            call_id=item.call_id, tool_name=item.tool_name, arguments=item.arguments,
            change_request=cr,
        ))
    return actions


async def _settle(result, *, session_id: str, team_id: str, agent_kind: str) -> ChatResponse:
    if result.interruptions:
        request_id = uuid.uuid4().hex
        cr_ids: dict[str, int] = {}
        for item in result.interruptions:
            if item.tool_name == "propose_change_request":
                args = json.loads(item.arguments)
                row_id = create_pending_change_request(
                    team_id=team_id,
                    title=args.get("title", ""),
                    description=args.get("description", ""),
                    configuration_plan=args.get("configuration_plan", ""),
                    change_type=args.get("change_type", ""),
                    risk=args.get("risk", ""),
                    affected_components=args.get("affected_components") or [],
                    incident_id=args.get("incident_id", ""),
                    impacted_teams=args.get("impacted_teams") or [],
                )
                cr_ids[item.call_id] = row_id
        PENDING[request_id] = {
            "state": result.to_state(),
            "items": result.interruptions,
            "session_id": session_id,
            "team_id": team_id,
            "agent_kind": agent_kind,
            "cr_ids": cr_ids,
        }
        return ChatResponse(
            status="pending_approval",
            request_id=request_id,
            actions=_build_actions(result.interruptions, cr_ids),
        )
    output = result.final_output
    if isinstance(output, TeamReport):
        return ChatResponse(status="done", report=output)
    return ChatResponse(status="done", reply=str(output))


@app.get("/teams")
async def list_teams() -> list[dict]:
    return [
        {"id": t["id"], "name": t["name"], "icon": t["icon"], "topology": t["topology"]}
        for t in TEAMS
    ]


class MessageRequest(BaseModel):
    message: str


@app.post("/teams/{team_id}/refresh", response_model=ChatResponse)
async def refresh_team(team_id: str) -> ChatResponse:
    runtime = _team_or_404(team_id)
    session_id = f"team-{team_id}"
    session = SQLiteSession(session_id=session_id, db_path=SESSIONS_DB_PATH)
    result = await Runner.run(
        runtime["reporter"],
        "Give your current status report: what are you observing right now, "
        "and what's your mitigation/upgrade plan? Propose any change requests "
        "needed.",
        session=session,
    )
    return await _settle(result, session_id=session_id, team_id=team_id, agent_kind="reporter")


@app.post("/teams/{team_id}/message", response_model=ChatResponse)
async def message_team(team_id: str, req: MessageRequest) -> ChatResponse:
    runtime = _team_or_404(team_id)
    session_id = f"team-{team_id}"
    session = SQLiteSession(session_id=session_id, db_path=SESSIONS_DB_PATH)
    result = await Runner.run(runtime["chat"], req.message, session=session)
    return await _settle(result, session_id=session_id, team_id=team_id, agent_kind="chat")


class ApproveRequest(BaseModel):
    request_id: str
    # call_id -> True (approve) / False (reject). Anything left out is
    # rejected by default - fail closed, not open.
    decisions: dict[str, bool]


@app.post("/approve", response_model=ChatResponse)
async def approve(req: ApproveRequest) -> ChatResponse:
    pending = PENDING.pop(req.request_id, None)
    if pending is None:
        raise HTTPException(status_code=404, detail="Unknown or already-resolved request_id")

    for call_id, row_id in pending["cr_ids"].items():
        approved = req.decisions.get(call_id, False)
        finalize_change_request(row_id, "approved" if approved else "rejected")

    state: RunState = pending["state"]
    for item in pending["items"]:
        if req.decisions.get(item.call_id, False):
            state.approve(item)
        else:
            state.reject(item)

    runtime = _team_or_404(pending["team_id"])
    agent = runtime[pending["agent_kind"]]
    session = SQLiteSession(session_id=pending["session_id"], db_path=SESSIONS_DB_PATH)
    result = await Runner.run(agent, state, session=session)
    return await _settle(
        result, session_id=pending["session_id"], team_id=pending["team_id"],
        agent_kind=pending["agent_kind"],
    )


@app.get("/approvals")
async def list_pending_approvals() -> list[dict]:
    out = []
    for request_id, pending in PENDING.items():
        team = teams_runtime[pending["team_id"]]["meta"]
        out.append({
            "request_id": request_id,
            "team_id": team["id"],
            "team_name": team["name"],
            "team_icon": team["icon"],
            "actions": [a.model_dump() for a in _build_actions(pending["items"], pending["cr_ids"])],
        })
    return out


@app.get("/change-requests")
async def change_request_history() -> list[dict]:
    return list_decided_change_requests()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "teams": len(teams_runtime), "pending_approvals": len(PENDING)}
