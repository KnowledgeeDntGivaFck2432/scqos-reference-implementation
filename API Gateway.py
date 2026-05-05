"""
SCQOS API GATEWAY ADAPTER
Trunk — First Real Enforcement Spine

Flow:
External HTTP request -> SC Universal State Packet -> Nine Gates -> ADMIT or DENY -> API runs or blocks

Put this file beside your kernel and root adapter files.

Dependencies:
    scqos_root_adapter.py
    scqos_reference_implementation.py / scqos_kernel.py / scqos.py / main.py

Optional HTTP server:
    pip install flask
    pip install fastapi uvicorn

Run standalone demo:
    python scqos_api_gateway_adapter.py

Run Flask gateway:
    SCQOS_GATEWAY_MODE=flask python scqos_api_gateway_adapter.py

Run FastAPI gateway:
    SCQOS_GATEWAY_MODE=fastapi python scqos_api_gateway_adapter.py
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------
# LOAD ROOT ADAPTER
# ---------------------------------------------------------------------

def load_root_adapter():
    preferred = os.getenv("SCQOS_ROOT_MODULE")
    candidates = []

    if preferred:
        candidates.append(preferred)

    candidates.extend([
        "scqos_root_adapter",
        "Root_Adapter",
    ])

    last_error: Optional[Exception] = None

    for name in candidates:
        try:
            module = importlib.import_module(name)
            required = [
                "SCQOSRootAdmissionAdapter",
                "SCUniversalStatePacket",
                "SCAdmissionProof",
                "AdmissionDecision",
                "ExternalSystemType",
            ]
            missing = [item for item in required if not hasattr(module, item)]
            if missing:
                raise ImportError(f"{name} missing required symbols: {missing}")
            return module
        except Exception as error:
            last_error = error

    raise ImportError(
        "Could not load SCQOS root adapter. Put this file beside scqos_root_adapter.py "
        f"or set SCQOS_ROOT_MODULE. Last error: {last_error}"
    )


ROOT = load_root_adapter()

AdmissionDecision = ROOT.AdmissionDecision
ExternalSystemType = ROOT.ExternalSystemType
SCAdmissionProof = ROOT.SCAdmissionProof
SCQOSRootAdmissionAdapter = ROOT.SCQOSRootAdmissionAdapter


# ---------------------------------------------------------------------
# REQUEST / RESPONSE SHAPES
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class GatewayRequest:
    """
    Normalized inbound HTTP request.

    Framework specific adapters translate their native request objects
    into this shape before SC sees anything.
    """

    method: str
    path: str
    headers: Dict[str, str]
    query: Dict[str, str]
    body: bytes
    remote_addr: str
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    received_at: float = field(default_factory=time.time)

    def body_hash(self) -> str:
        return hashlib.sha3_512(self.body).hexdigest()

    def actor(self) -> str:
        for h in ("x-actor-id", "x-user-id", "x-api-key", "authorization"):
            v = self.headers.get(h, "").strip()
            if v:
                return v[:128]
        return f"anonymous@{self.remote_addr}"

    def canonical(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "method": self.method,
            "path": self.path,
            "query": self.query,
            "body_hash": self.body_hash(),
            "remote_addr": self.remote_addr,
            "received_at": self.received_at,
        }


@dataclass(frozen=True)
class GatewayResponse:
    admitted: bool
    status_code: int
    body: Dict[str, Any]
    proof: Optional[SCAdmissionProof]
    request_id: str
    latency_ms: float

    def to_json(self) -> str:
        out: Dict[str, Any] = {
            "admitted": self.admitted,
            "status_code": self.status_code,
            "request_id": self.request_id,
            "latency_ms": round(self.latency_ms, 3),
            "body": self.body,
        }
        if self.proof:
            out["sc_proof"] = {
                "decision": self.proof.decision.value,
                "final_proof": self.proof.final_proof,
                "module_id": self.proof.module_id,
                "packet_id": self.proof.packet_id,
                "reason": self.proof.reason,
            }
        return json.dumps(out, indent=2, sort_keys=True)


# ---------------------------------------------------------------------
# ROUTE REGISTRY
# ---------------------------------------------------------------------

@dataclass
class RouteRule:
    path_prefix: str
    handler: Callable[[GatewayRequest, SCAdmissionProof], Dict[str, Any]]
    methods: List[str] = field(default_factory=list)
    require_actor: bool = False
    description: str = ""


class RouteRegistry:
    def __init__(self) -> None:
        self._rules: List[RouteRule] = []

    def register(
        self,
        path_prefix: str,
        handler: Callable[[GatewayRequest, SCAdmissionProof], Dict[str, Any]],
        methods: Optional[List[str]] = None,
        require_actor: bool = False,
        description: str = "",
    ) -> None:
        self._rules.append(RouteRule(
            path_prefix=path_prefix,
            handler=handler,
            methods=[m.upper() for m in (methods or [])],
            require_actor=require_actor,
            description=description,
        ))

    def match(self, request: GatewayRequest) -> Optional[RouteRule]:
        for rule in self._rules:
            if not request.path.startswith(rule.path_prefix):
                continue
            if rule.methods and request.method.upper() not in rule.methods:
                continue
            return rule
        return None


# ---------------------------------------------------------------------
# GATEWAY
# ---------------------------------------------------------------------

class SCQOSApiGateway:
    """
    API Gateway Adapter — the trunk.

    Every inbound request is forced through the SC nine-gate root
    before any handler is called.
    """

    def __init__(
        self,
        node_id: Optional[str] = None,
        session_id: Optional[str] = None,
        observer_id: str = "scqos_gateway_observer",
        substrate_id: str = "scqos_gateway_substrate",
        enforce_substrate: Optional[bool] = None,
        include_proof_in_response: bool = True,
        denied_status_code: int = 403,
    ):
        self.root = SCQOSRootAdmissionAdapter(
            node_id=node_id or os.getenv("SCQOS_NODE_ID", "node-alpha"),
            session_id=session_id or f"scqos_gateway_{uuid.uuid4().hex}",
            observer_id=observer_id,
            substrate_id=substrate_id,
            enforce_substrate=enforce_substrate,
        )
        self.routes = RouteRegistry()
        self.include_proof_in_response = include_proof_in_response
        self.denied_status_code = denied_status_code
        self._request_log: List[Dict[str, Any]] = []

    def register_route(
        self,
        path_prefix: str,
        handler: Callable[[GatewayRequest, SCAdmissionProof], Dict[str, Any]],
        methods: Optional[List[str]] = None,
        require_actor: bool = False,
        description: str = "",
    ) -> None:
        self.routes.register(path_prefix, handler, methods, require_actor, description)

    def _build_packet(self, request: GatewayRequest):
        return self.root.make_packet(
            system_type=ExternalSystemType.API_REQUEST.value,
            action=f"{request.method}:{request.path}",
            actor=request.actor(),
            source=request.remote_addr,
            target=request.path,
            declared_objective="verify_access",
            payload=request.canonical(),
            external_reference=request.request_id,
            external_signature=request.body_hash(),
        )

    def handle(self, request: GatewayRequest) -> GatewayResponse:
        start = time.monotonic()

        rule = self.routes.match(request)
        if rule is None:
            return GatewayResponse(
                admitted=False,
                status_code=404,
                body={"error": "no route matched", "path": request.path},
                proof=None,
                request_id=request.request_id,
                latency_ms=(time.monotonic() - start) * 1000,
            )

        if rule.require_actor and request.actor().startswith("anonymous@"):
            return GatewayResponse(
                admitted=False,
                status_code=401,
                body={"error": "actor required", "path": request.path},
                proof=None,
                request_id=request.request_id,
                latency_ms=(time.monotonic() - start) * 1000,
            )

        packet = self._build_packet(request)
        proof = self.root.admit(packet)
        admitted = proof.decision == AdmissionDecision.ADMIT

        self._log(request, proof, admitted)

        if not admitted:
            return GatewayResponse(
                admitted=False,
                status_code=self.denied_status_code,
                body={"error": "SC denied execution", "reason": proof.reason},
                proof=proof if self.include_proof_in_response else None,
                request_id=request.request_id,
                latency_ms=(time.monotonic() - start) * 1000,
            )

        try:
            result = rule.handler(request, proof)
            return GatewayResponse(
                admitted=True,
                status_code=200,
                body=result,
                proof=proof if self.include_proof_in_response else None,
                request_id=request.request_id,
                latency_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as error:
            return GatewayResponse(
                admitted=True,
                status_code=500,
                body={"error": "handler error", "detail": str(error)},
                proof=proof if self.include_proof_in_response else None,
                request_id=request.request_id,
                latency_ms=(time.monotonic() - start) * 1000,
            )

    def _log(self, request: GatewayRequest, proof: SCAdmissionProof, admitted: bool) -> None:
        self._request_log.append({
            "timestamp": time.time(),
            "request_id": request.request_id,
            "method": request.method,
            "path": request.path,
            "actor": request.actor(),
            "admitted": admitted,
            "proof": proof.final_proof,
            "reason": proof.reason,
        })

    def report(self) -> None:
        total = len(self._request_log)
        admitted = sum(1 for r in self._request_log if r["admitted"])
        denied = total - admitted

        print("\nSCQOS API GATEWAY REPORT")
        print("=" * 88)
        print(f"  Total requests : {total}")
        print(f"  Admitted       : {admitted}")
        print(f"  Denied         : {denied}")
        print("-" * 88)
        print(f"  {'REQUEST ID':32s} {'METHOD':6s} {'PATH':30s} {'DECISION':8s} PROOF")
        print("-" * 88)

        for entry in self._request_log:
            decision = "ADMIT" if entry["admitted"] else "DENY"
            proof = entry["proof"] or "—"
            print(
                f"  {entry['request_id'][:32]:32s} "
                f"{entry['method']:6s} "
                f"{entry['path']:30s} "
                f"{decision:8s} "
                f"{proof}"
            )
        print("=" * 88)


# ---------------------------------------------------------------------
# FRAMEWORK BRIDGES
# ---------------------------------------------------------------------

class FlaskBridge:
    def __init__(self, gateway: SCQOSApiGateway) -> None:
        self.gateway = gateway

    def handle_flask_request(self):
        try:
            from flask import request as flask_request, Response
        except ImportError as error:
            raise RuntimeError("Flask not installed. pip install flask") from error

        gr = GatewayRequest(
            method=flask_request.method,
            path=flask_request.path,
            headers={k.lower(): v for k, v in flask_request.headers.items()},
            query=dict(flask_request.args),
            body=flask_request.get_data(),
            remote_addr=flask_request.remote_addr or "unknown",
        )
        gw_response = self.gateway.handle(gr)
        return Response(
            gw_response.to_json(),
            status=gw_response.status_code,
            mimetype="application/json",
        )


class FastApiBridge:
    def __init__(self, gateway: SCQOSApiGateway) -> None:
        self.gateway = gateway

    async def handle_fastapi_request(self, request: Any):
        try:
            from fastapi.responses import JSONResponse
        except ImportError as error:
            raise RuntimeError("FastAPI not installed. pip install fastapi uvicorn") from error

        body = await request.body()
        gr = GatewayRequest(
            method=request.method,
            path=request.url.path,
            headers=dict(request.headers),
            query=dict(request.query_params),
            body=body,
            remote_addr=request.client.host if request.client else "unknown",
        )
        gw_response = self.gateway.handle(gr)
        return JSONResponse(
            content=json.loads(gw_response.to_json()),
            status_code=gw_response.status_code,
        )


# ---------------------------------------------------------------------
# DEMO HANDLERS
# ---------------------------------------------------------------------

def handler_health(request: GatewayRequest, proof: SCAdmissionProof) -> Dict[str, Any]:
    return {
        "status": "healthy",
        "sc_proof": proof.final_proof,
        "admitted_at": proof.admitted_at,
    }


def handler_echo(request: GatewayRequest, proof: SCAdmissionProof) -> Dict[str, Any]:
    return {
        "echo": {
            "method": request.method,
            "path": request.path,
            "actor": request.actor(),
            "body_hash": request.body_hash(),
            "query": request.query,
        },
        "sc_proof": proof.final_proof,
    }


def handler_execute(request: GatewayRequest, proof: SCAdmissionProof) -> Dict[str, Any]:
    return {
        "executed": True,
        "action": f"{request.method}:{request.path}",
        "actor": request.actor(),
        "sc_proof": proof.final_proof,
        "module_id": proof.module_id,
        "message": "SC admitted this request. Execution authorized.",
    }


# ---------------------------------------------------------------------
# DEMO
# ---------------------------------------------------------------------

def demo() -> None:
    print("=" * 88)
    print(" SCQOS API GATEWAY ADAPTER — TRUNK DEMO")
    print(" External request -> SC packet -> Nine Gates -> ADMIT or DENY -> Handler")
    print("=" * 88)

    gateway = SCQOSApiGateway(include_proof_in_response=True)

    gateway.register_route("/health", handler_health, methods=["GET"], description="Health check")
    gateway.register_route("/echo", handler_echo, methods=["GET", "POST"], description="Echo")
    gateway.register_route(
        "/execute",
        handler_execute,
        methods=["POST"],
        require_actor=True,
        description="Protected execution endpoint",
    )

    test_requests = [
        GatewayRequest(
            method="GET",
            path="/health",
            headers={},
            query={},
            body=b"",
            remote_addr="127.0.0.1",
        ),
        GatewayRequest(
            method="POST",
            path="/echo",
            headers={"content-type": "application/json"},
            query={"debug": "true"},
            body=b'{"hello": "scqos"}',
            remote_addr="10.0.0.1",
        ),
        GatewayRequest(
            method="POST",
            path="/execute",
            headers={"x-actor-id": "scqos_architect", "content-type": "application/json"},
            query={},
            body=b'{"action": "deploy"}',
            remote_addr="10.0.0.2",
        ),
        GatewayRequest(
            method="POST",
            path="/execute",
            headers={},
            query={},
            body=b'{"action": "deploy"}',
            remote_addr="192.168.1.99",
        ),
        GatewayRequest(
            method="DELETE",
            path="/unknown/route",
            headers={},
            query={},
            body=b"",
            remote_addr="1.2.3.4",
        ),
    ]

    for req in test_requests:
        response = gateway.handle(req)
        status = "ADMIT" if response.admitted else "DENY "
        print(f"\n[{status}] {req.method} {req.path}")
        print(f"  status_code : {response.status_code}")
        print(f"  latency_ms  : {response.latency_ms:.2f}")
        if response.proof and response.proof.final_proof:
            print(f"  sc_proof    : {response.proof.final_proof}")
        body_preview = json.dumps(response.body)[:120]
        print(f"  body        : {body_preview}")

    print()
    gateway.report()


# ---------------------------------------------------------------------
# FLASK / FASTAPI ENTRY POINTS
# ---------------------------------------------------------------------

def run_flask() -> None:
    try:
        from flask import Flask
    except ImportError:
        print("Flask not installed. pip install flask")
        return

    gateway = SCQOSApiGateway()
    gateway.register_route("/health", handler_health, methods=["GET"])
    gateway.register_route("/echo", handler_echo, methods=["GET", "POST"])
    gateway.register_route("/execute", handler_execute, methods=["POST"], require_actor=True)

    bridge = FlaskBridge(gateway)
    app = Flask(__name__)

    @app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    def catch_all(path):
        return bridge.handle_flask_request()

    @app.route("/", methods=["GET"])
    def root():
        return bridge.handle_flask_request()

    print("SCQOS API Gateway running on http://0.0.0.0:8000 (Flask)")
    app.run(host="0.0.0.0", port=8000, debug=False)


def run_fastapi() -> None:
    try:
        import uvicorn
        from fastapi import FastAPI, Request
    except ImportError:
        print("FastAPI/uvicorn not installed. pip install fastapi uvicorn")
        return

    gateway = SCQOSApiGateway()
    gateway.register_route("/health", handler_health, methods=["GET"])
    gateway.register_route("/echo", handler_echo, methods=["GET", "POST"])
    gateway.register_route("/execute", handler_execute, methods=["POST"], require_actor=True)

    bridge = FastApiBridge(gateway)
    app = FastAPI(title="SCQOS API Gateway")

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def catch_all(request: Request):
        return await bridge.handle_fastapi_request(request)

    print("SCQOS API Gateway running on http://0.0.0.0:8000 (FastAPI)")
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    mode = os.getenv("SCQOS_GATEWAY_MODE", "demo").lower()

    if mode == "flask":
        run_flask()
    elif mode == "fastapi":
        run_fastapi()
    else:
        demo()
