# Design Specification: Medical RAG Fix and Running Plan

This document specifies the updates required to fix the decommissioned model error, correct API response serialization, and run the FastAPI application.

## 1. Problem Statement
The current Medical RAG application fails to query the LLM because:
1. Groq has decommissioned the `mixtral-8x7b-32768` model, returning a `400 Bad Request` error.
2. The `/get_response` endpoint returns double-serialized JSON via `Response(jsonable_encoder(json.dumps(...)))` with a text/plain or default content type, causing Javascript `response.json()` to parse it into a string instead of an object, rendering all fields `undefined` on the frontend.
3. The default port `8000` is currently in use by another application.

## 2. Proposed Changes

### 2.1 Model Upgrade
Update `app.py` to use `llama-3.3-70b-versatile` as the ChatGroq model.

### 2.2 Endpoint Response Fix
Modify `/get_response` to return the dict directly. FastAPI will automatically serialize it using the appropriate `JSONResponse` class, ensuring the correct `application/json` Content-Type header.

### 2.3 Port Configuration
Run the app on port `8001` to avoid conflicting with the existing process on `8000`.

## 3. Verification Plan
1. Use `fastapi.testclient.TestClient` to perform automated API testing on `/get_response`.
2. Start the uvicorn server on port `8001`.
3. Provide the local link to the user.
