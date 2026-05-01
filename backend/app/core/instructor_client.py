import os
from typing import Type, TypeVar, Optional
import instructor
import litellm
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)

class InstructorOllamaClient:
    """Wrapper for Ollama using Instructor for structured outputs.

    Uses LiteLLM as adapter since Instructor doesn't support Ollama directly.
    """

    def __init__(
        self,
        model: str = "llama3.2",
        base_url: Optional[str] = None,
        max_retries: int = 3
    ):
        """Initialize Instructor client with Ollama backend via LiteLLM.

        Uses a dummy 'api_key' as LiteLLM requires an API key,
        even though Ollama doesn't use one.
        """
        # Use env var or default localhost
        self.base_url = base_url or os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        self.model = model
        self.max_retries = max_retries

        # Create a LiteLLM completion function
        def ollama_completion(**kwargs):
            # Create a copy of kwargs and merge default params
            default_params = {
                "model": self.model,
                "base_url": self.base_url,
                "api_key": "ollama"  # Dummy key for LiteLLM requirement
            }
            # Merge default params, ensuring passed kwargs take precedence
            kwargs = {**default_params, **kwargs}

            try:
                # Use litellm to call Ollama
                return litellm.completion(**kwargs)
            except Exception as e:
                # Provide meaningful error for network or model failures
                raise RuntimeError(f"Ollama API call failed: {str(e)}") from e

        # Create Instructor client using LiteLLM adapter
        self.client = instructor.from_litellm(
            completion=ollama_completion,
            mode=instructor.Mode.JSON
        )

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        temperature: float = 0.7,
        **kwargs
    ) -> T:
        """Generate structured output validated against Pydantic model.

        Args:
            prompt: Input prompt
            response_model: Pydantic model to validate against
            temperature: Model temperature (0.0-1.0)

        Returns:
            Instance of response_model with validated data

        Raises:
            ValueError: If model validation fails
            RuntimeError: If network or API errors occur
        """
        try:
            return await self.client.acreate(
                model=self.model,
                response_model=response_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_retries=self.max_retries,
                base_url=self.base_url,
                **kwargs
            )
        except ValueError as ve:
            # Catch and re-raise validation errors with context
            raise ValueError(f"Model validation failed: {str(ve)}") from ve
        except Exception as e:
            # Wrap other exceptions with context
            raise RuntimeError(f"Structured generation failed: {str(e)}") from e

    def generate_structured_sync(
        self,
        prompt: str,
        response_model: Type[T],
        temperature: float = 0.7,
        **kwargs
    ) -> T:
        """Sync version of generate_structured.

        Args:
            prompt: Input prompt
            response_model: Pydantic model to validate against
            temperature: Model temperature (0.0-1.0)

        Returns:
            Instance of response_model with validated data

        Raises:
            ValueError: If model validation fails
            RuntimeError: If network or API errors occur
        """
        try:
            return self.client.create(
                model=self.model,
                response_model=response_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_retries=self.max_retries,
                base_url=self.base_url,
                **kwargs
            )
        except ValueError as ve:
            # Catch and re-raise validation errors with context
            raise ValueError(f"Model validation failed: {str(ve)}") from ve
        except Exception as e:
            # Wrap other exceptions with context
            raise RuntimeError(f"Structured generation failed: {str(e)}") from e