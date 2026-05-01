from typing import Optional, List
from pydantic import BaseModel, Field


class TeesheetInitOutput(BaseModel):
    """Output schema for brs_teesheet_init command."""
    success: bool = Field(description="Whether initialization succeeded")
    database_name: str = Field(description="Name of created database")
    stdout: str = Field(description="Raw stdout from CLI command")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class SuperuserCreateOutput(BaseModel):
    """Output schema for brs_create_superuser command."""
    success: bool = Field(description="Whether superuser creation succeeded")
    user_id: Optional[int] = Field(default=None, description="Created user ID")
    email: str = Field(description="Superuser email address")
    stdout: str = Field(description="Raw stdout from CLI command")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class ConfigValidateOutput(BaseModel):
    """Output schema for brs_config_validate command."""
    success: bool = Field(description="Whether configuration is valid")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    stdout: str = Field(description="Raw stdout from CLI command")