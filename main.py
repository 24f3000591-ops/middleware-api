import time
import uuid
from collections import defaultdict
from fastapi import FastAPI, Request, Response, status

app = FastAPI()

ASSIGNED_ORIGIN = "https://app-eni6y1.example.com"
RATE_LIMIT_WINDOW = 14.0  
RATE_LIMIT_MAX_REQUESTS = 10

# In-memory sliding window store
client_buckets = defaultdict(list)

@app.middleware("http")
async def unified_api_stack(request: Request, call_next):
    # 1. Capture dynamic inbound matching details
    origin = request.headers.get("origin")
    
    # 2. Extract or spin up Request Context Tracking 
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    # 3. Short-circuit execute Browser Preflight CORS (OPTIONS) Protocol
    if request.method == "OPTIONS":
        response = Response(status_code=status.HTTP_200_OK)
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "X-Request-ID, X-Client-Id, Content-Type, Authorization, Accept"
            response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    # 4. Sliding Window Rate Limiting Enforcement
    response = None
    if request.url.path == "/ping":
        client_id = request.headers.get("X-Client-Id")
        if client_id:
            current_time = time.time()
            timestamps = client_buckets[client_id]
            
            # Wipe older entries outside the 10s boundary
            while timestamps and timestamps[0] < current_time - RATE_LIMIT_WINDOW:
                timestamps.pop(0)
                
            if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
                response = Response(
                    content='{"detail": "Too Many Requests"}',
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    media_type="application/json"
                )
            else:
                timestamps.append(current_time)

    # 5. Hand-off normal operational loop execution 
    if not response:
        response = await call_next(request)

    # 6. Apply outbox envelope headers to all paths (including 429 errors)
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
    elif request.url.path == "/ping":
        # Fallback security profile context if an explicit testing header wasn't populated
        response.headers["Access-Control-Allow-Origin"] = ASSIGNED_ORIGIN
        
    response.headers["X-Request-ID"] = request_id
    return response

# -----------------------------------------------------------------------------
# CORE ENDPOINT
# -----------------------------------------------------------------------------
@app.get("/ping")
async def ping(request: Request):
    return {
        "email": "24ds2000591@ds.study.iitm.ac.in",  
        "request_id": getattr(request.state, "request_id", "none")
    }
