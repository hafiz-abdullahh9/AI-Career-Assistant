from urllib.parse import urlparse
from typing import Dict, Any, Optional, Type
import structlog

from app.integrations.adapters.base_adapter import BaseIntegrationAdapter
from app.integrations.adapters.greenhouse import GreenhouseAdapter
from app.integrations.adapters.lever import LeverAdapter
from app.integrations.adapters.generic import GenericAdapter

logger = structlog.get_logger(__name__)

class AdapterRegistry:
    """
    Registry for dynamic integration adapters discovery.
    Maps target URLs to the best fit platform adapter.
    """

    ADAPTER_CLASSES = [
        GreenhouseAdapter,
        LeverAdapter
    ]

    @classmethod
    def get_adapter(cls, url: str, custom_selectors: Optional[Dict[str, str]] = None) -> BaseIntegrationAdapter:
        """
        Returns the appropriate adapter instance for the given URL.
        Falls back to GenericAdapter if no platform matches.
        """
        parsed_url = urlparse(url)
        # Handle file URLs (sandbox testing) differently: we check the filename or url query param
        domain = parsed_url.netloc.lower()
        path = parsed_url.path.lower()
        
        # Check domain allowlists
        for adapter_cls in cls.ADAPTER_CLASSES:
            instance = adapter_cls()
            # If domain matches, or for file sandbox templates, the filename matches the domain keywords
            for sd in instance.supported_domains:
                if sd in domain or (parsed_url.scheme == "file" and sd.split(".")[0] in path):
                    logger.info("integrations.registry.matched_adapter", adapter=adapter_cls.__name__, url=url)
                    return instance

        logger.info("integrations.registry.fallback_generic", url=url)
        return GenericAdapter(custom_selectors=custom_selectors)
