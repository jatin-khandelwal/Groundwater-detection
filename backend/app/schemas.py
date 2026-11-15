from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class PredictRequest(BaseModel):
    district_name: str | None = Field(default=None, min_length=1)
    block_name: str | None = Field(default=None, min_length=1)
    site_id: str | None = None
    latitude: float | None = Field(default=None, ge=23, le=30.5)
    longitude: float | None = Field(default=None, ge=69, le=78.5)
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2005, le=2100)

    @model_validator(mode="after")
    def validate_location(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        if not self.site_id and not self.district_name:
            raise ValueError("Provide district_name or site_id")
        if self.site_id and (self.latitude is not None or self.longitude is not None):
            raise ValueError("Use site_id or explicit coordinates, not both")
        return self


class AdvisoryRequest(BaseModel):
    district_name: str = Field(min_length=1)
    block_name: str = Field(min_length=1)
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2005, le=2100)


class PredictionResponse(BaseModel):
    model_version: str
    prediction_m: float
    interval: dict
    risk: str
    confidence: str
    inputs_used: dict
    warnings: list[str]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    database_ready: bool
    model_version: str
    model_error: str | None = None
