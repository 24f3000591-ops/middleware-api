import time
import uuid
from typing import Dict, List
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(redirect_slashes=False)

# Assigned Configuration Values
ALLOWED_ORIGIN = "https://app-eni6y1.example.com"
BUCKET_SIZE = 14
WINDOW_SIZE = 10.0  # seconds
MY_EMAIL = "24f3000591@ds.study.iitm.ac.in"  # Replace with your logged-in email address

# Strict In-Memory Sliding-Window Rate Limiter
rate_limit_store: Dict[str, List[float]] = {}

# --- 1. Catch-All Dynamic CORS Middleware ---
@app.middleware("http")
async def dynamic_cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    
    # Handle preflight OPTIONS requests immediately
    if request.method == "OPTIONS":
        response = Response(status_code=status.HTTP_200_OK)
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "X-Request-ID, X-Client-Id, Content-Type, Authorization"
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    response = await call_next(request)
    
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        
    return response


# --- 2. Request Context & Rate Limiter Pipeline ---
@app.middleware("http")
async def process_request_pipeline(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    # Resolve Request ID immediately
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    
    # Make request_id accessible globally via state
    request.state.request_id = request_id

    # Rate Limiting Logic
    client_id = request.headers.get("X-Client-Id")
    if client_id:
        now = time.time()
        timestamps = rate_limit_store.get(client_id, [])
        timestamps = [t for t in timestamps if now - t < WINDOW_SIZE]
        
        if len(timestamps) >= BUCKET_SIZE:
            rate_limit_store[client_id] = timestamps
            
            origin = request.headers.get("origin")
            headers = {
                "Retry-After": "5",
                "X-Request-ID": request_id  # Ensure request ID is present on 429 errors
            }
            if origin:
                headers["Access-Control-Allow-Origin"] = origin
                headers["Access-Control-Allow-Credentials"] = "true"
                
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers=headers
            )
            
        timestamps.append(now)
        rate_limit_store[client_id] = timestamps

    # Process the request down to the path operation
    response = await call_next(request)
    
    # Explicitly enforce injection into outbound response headers
    response.headers["X-Request-ID"] = request_id
    return response


# --- Endpoints ---

@app.get("/ping")
async def ping(request: Request, response: Response):
    # Retrieve the resolved request ID from the state layer
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    
    # Explicitly setting it directly on the route response payload and headers 
    # provides an absolute fallback guarantee.
    response.headers["X-Request-ID"] = request_id
    
    return {
        "email": MY_EMAIL,
        "request_id": request_id
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
