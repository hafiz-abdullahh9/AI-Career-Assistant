"""
Shared pytest fixtures and configuration for Member 3 tests.
"""

import sys
import os
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.fixtures.sample_profiles import (
    full_profile,
    minimal_profile,
    empty_skills_profile,
    senior_engineer_profile,
    data_scientist_profile,
    career_changer_profile,
    fresh_graduate_profile,
)
from tests.fixtures.sample_job_listings import (
    software_engineer_listing,
    data_scientist_listing,
    senior_manager_listing,
    remote_internship_listing,
    no_skills_listing,
    rejected_listing,
    flagged_listing,
    frontend_developer_listing,
    devops_engineer_listing,
    data_analyst_listing,
    batch_listings_20,
)


# ---- User Profile Fixtures ----

@pytest.fixture
def profile_full():
    return full_profile()

@pytest.fixture
def profile_minimal():
    return minimal_profile()

@pytest.fixture
def profile_empty_skills():
    return empty_skills_profile()

@pytest.fixture
def profile_senior():
    return senior_engineer_profile()

@pytest.fixture
def profile_data_scientist():
    return data_scientist_profile()

@pytest.fixture
def profile_career_changer():
    return career_changer_profile()

@pytest.fixture
def profile_fresh_graduate():
    return fresh_graduate_profile()


# ---- Job Listing Fixtures ----

@pytest.fixture
def job_swe():
    return software_engineer_listing()

@pytest.fixture
def job_data_scientist():
    return data_scientist_listing()

@pytest.fixture
def job_senior_manager():
    return senior_manager_listing()

@pytest.fixture
def job_internship():
    return remote_internship_listing()

@pytest.fixture
def job_no_skills():
    return no_skills_listing()

@pytest.fixture
def job_rejected():
    return rejected_listing()

@pytest.fixture
def job_flagged():
    return flagged_listing()

@pytest.fixture
def job_frontend():
    return frontend_developer_listing()

@pytest.fixture
def job_devops():
    return devops_engineer_listing()

@pytest.fixture
def job_data_analyst():
    return data_analyst_listing()

@pytest.fixture
def jobs_batch():
    return batch_listings_20()


# ---- Utility Fixtures ----

@pytest.fixture
def temp_output_dir(tmp_path):
    """Temporary directory for generated documents."""
    resumes = tmp_path / "resumes"
    cover_letters = tmp_path / "cover_letters"
    resumes.mkdir()
    cover_letters.mkdir()
    return tmp_path
