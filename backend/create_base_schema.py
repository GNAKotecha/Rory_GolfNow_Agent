"""Create base database schema from models."""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.db.session import Base, engine

# Import all models to register them with Base
from app.models.models import (
    User, Session, Message, WorkflowEvent, ToolCall, Approval,
    WorkflowClassification, UserPreference, WorkflowMemory,
    DomainKnowledge, FailedRun
)
from app.models.workflow import WorkflowTemplate, WorkflowRun, WorkflowStepExecution
from app.models.metrics import StepMetrics, LLMDecisionMetrics
from app.models.prompt_template import PromptTemplate, PromptTemplateVersion
from app.models.external_credential import ExternalCredential

def main():
    """Create all tables."""
    print("Creating database schema...")
    print(f"Database: {settings.database_url.split('@')[-1]}")
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    print("✅ Database schema created successfully!")
    print("\nCreated tables:")
    for table_name in sorted(Base.metadata.tables.keys()):
        print(f"  - {table_name}")

if __name__ == "__main__":
    main()
