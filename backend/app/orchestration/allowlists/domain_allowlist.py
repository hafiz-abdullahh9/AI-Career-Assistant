from urllib.parse import urlparse

TRUSTED_DOMAINS = {
    "greenhouse.io",
    "lever.co",
    "workday.com",
    "taleo.net",
    "icims.com",
    "successfactors.com",
    "bamboohr.com",
    "smartrecruiters.com",
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "monster.com"
}


class DomainAllowlist:
    """
    Enforces a strict domain allowlist for web automation targets.
    Denies by default.
    """

    @classmethod
    def is_url_allowed(cls, url: str) -> bool:
        """
        Verify if the given URL is allowed for automation.
        Local file paths (file://) and localhost/127.0.0.1 are allowed for testing.
        """
        if not url:
            return False

        parsed = urlparse(url)
        scheme = parsed.scheme.lower()

        # Allow local files (for mock testing/sandbox forms)
        if scheme == "file":
            return True

        domain = parsed.netloc.lower()
        # Remove port if present
        if ":" in domain:
            domain = domain.split(":")[0]

        # Allow localhost / loopback for local environment testing
        if domain in ("localhost", "127.0.0.1"):
            return True

        # Strip 'www.' prefix if present
        if domain.startswith("www."):
            domain = domain[4:]

        # Check domain suffix matching
        for trusted in TRUSTED_DOMAINS:
            if domain == trusted or domain.endswith("." + trusted):
                return True

        return False
