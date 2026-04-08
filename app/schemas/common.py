from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str


class HealthResponse(BaseModel):
    status: str
    app_name: str
    env: str
