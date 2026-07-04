import time
import uuid
from typing import Dict, List
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

app = FastAPI(redirect_slashes=False)

# Assigned Configuration Values
ALLOWED_ORIGIN = "https://app-eni6y1.example.com"
BUCKET_SIZE = 14
WINDOW_SIZE = 10.0  # seconds
MY_EMAIL = "24f3000591@ds.study.iitm.ac.in"  # Replace with your logged-in email address

# Strict In-Memory Sliding-Window Rate Limiter
rate_limit_store: Dict[str, List[float]] = {}

# --- Global HTTP Exception Override ---
# This ensures that if any HTTPException (like a 429) occurs, the X-Request-ID 
# and CORS headers are explicitly preserved in the generated error response.
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    origin = request.headers.get("origin")
    
    headers = dict(exc.headers) if exc.headers else {}
    headers["X-Request-ID"] = request_id
    
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers
    )


# --- Unified Middleware Pipeline ---
@app.middleware("http")
async def unified_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    
    # 1. Handle preflight OPTIONS requests immediately
    if request.method == "OPTIONS":
        response = Response(status_code=status.HTTP_200_OK)
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "X-Request-ID, X-Client-Id, Content-Type, Authorization"
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    # 2. Resolve and capture Request ID early
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    
    # Cache it in request state so it is accessible globally
    request.state.request_id = request_id

    # 3. Rate Limiting Check
    client_id = request.headers.get("X-Client-Id")
    if client_id:
        now = time.time()
        timestamps = rate_limit_store.get(client_id, [])
        timestamps = [t for t in timestamps if now - t < WINDOW_SIZE]
        
        if len(timestamps) >= BUCKET_SIZE:
            rate_limit_store[client_id] = timestamps
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": "5"}
            )
            
        timestamps.append(now)
        rate_limit_store[client_id] = timestamps

    # 4. Proceed to execute endpoint route
    response = await call_next(request)
    
    # 5. Enforce output headers right before sending back to the client
    response.headers["X-Request-ID"] = request_id
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        
    return response


# --- Endpoints ---

@app.get("/ping")
async def ping(request: Request, response: Response):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    
    # Redundant assurance: write directly to route context headers
    response.headers["X-Request-ID"] = request_id
    
    return {
        "email": MY_EMAIL,
        "request_id": request_id
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
