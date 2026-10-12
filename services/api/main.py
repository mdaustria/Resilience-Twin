"""Local API bootstrap. Task 1.2 adds the synthetic simulation use case."""

from fastapi import FastAPI
from pydantic import BaseModel


class BootstrapStatus(BaseModel):
    status: str
    schema_version: str


app = FastAPI(title="Resilience Twin local API", version="bootstrap.v1")


@app.get("/api/v1/bootstrap", response_model=BootstrapStatus)
def bootstrap_status() -> BootstrapStatus:
    return BootstrapStatus(status="ready", schema_version="bootstrap.v1")
