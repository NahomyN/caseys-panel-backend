from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Casey's Panel HIPAA API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
def health_check():
    return {"ok": True, "message": "HIPAA Backend Online", "status": "operational"}

@app.get("/")
def root():
    return {"service": "Casey's Panel HIPAA API", "version": "1.0.0", "status": "running"}

@app.post("/api/v1/workflow/process-notes")
def process_notes():
    return {"status": "success", "message": "Notes processed successfully", "workflowId": "casey-001"}

@app.post("/api/v1/workflows/{case_id}/start")
def start_workflow(case_id: str):
    return {"status": "success", "message": "Workflow started", "workflowId": f"casey-{case_id}", "caseId": case_id}

@app.get("/api/v1/auth/google-client-id")
def get_google_client_id():
    return {"clientId": "153410214288-poq46sd9781qukuhsgc9313u8lh57ti1.apps.googleusercontent.com"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)
