class CareerAssistantException(Exception):
    """Base exception class for AGENT 02 — AI-Based Career Assistant System"""
    pass

class OrchestrationError(CareerAssistantException):
    """Raised when there is an issue coordinating agent transitions or pipeline state"""
    pass

class AgentExecutionError(CareerAssistantException):
    """Raised when a specialist agent fails during its task execution"""
    def __init__(self, agent_name: str, message: str, stage: str):
        super().__init__(f"Agent {agent_name} failed at stage {stage}: {message}")
        self.agent_name = agent_name
        self.stage = stage

class IntegrityCheckFailed(CareerAssistantException):
    """Raised by ProfileIntegrityMonitor when document contents diverge from profile truth"""
    pass

class PIIScrubbingError(CareerAssistantException):
    """Raised when the CV/PII scrubber encounters a validation error"""
    pass

class DatabaseException(CareerAssistantException):
    """Raised when PostgreSQL operations fail"""
    pass

class CacheException(CareerAssistantException):
    """Raised when Redis caching operations fail"""
    pass

class SecurityException(CareerAssistantException):
    """Raised when token decryption or encryption checks fail"""
    pass
