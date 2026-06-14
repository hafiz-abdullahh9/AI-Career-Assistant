"""
Sample verified job listings for testing Member 3 agents.
Each listing represents a different testing scenario.
"""

from typing import List

from models.matching_models import VerifiedJobListing


def software_engineer_listing() -> VerifiedJobListing:
    """Standard SWE role — Python/AWS/Docker. Good match for full_profile."""
    return VerifiedJobListing(
        job_id="job-001",
        company_name="InnovateTech Solutions",
        job_title="Senior Software Engineer",
        description=(
            "We are looking for a Senior Software Engineer to join our platform team. "
            "You will design and build scalable microservices, mentor junior engineers, "
            "and drive best practices across the engineering organization. "
            "Experience with cloud infrastructure and containerization is essential. "
            "You'll work in an agile environment with a focus on quality and continuous delivery."
        ),
        required_skills=["Python", "AWS", "Docker", "PostgreSQL", "REST API"],
        preferred_skills=["Kubernetes", "Terraform", "CI/CD"],
        location="San Francisco, CA",
        salary="$180,000 - $220,000",
        job_type="full-time",
        experience_level="senior",
        application_deadline="2026-07-15",
        contact_info="careers@innovatetech.com",
        application_url="https://innovatetech.com/careers/senior-swe",
        posted_date="2026-06-01",
        verified_status="verified",
        source_platform="linkedin",
    )


def data_scientist_listing() -> VerifiedJobListing:
    """ML-focused role — cross-skill matching test with data_scientist_profile."""
    return VerifiedJobListing(
        job_id="job-002",
        company_name="DataMind AI",
        job_title="Machine Learning Engineer",
        description=(
            "Join our ML team to build and deploy production machine learning models. "
            "You'll work on recommendation systems, NLP, and computer vision projects. "
            "We're looking for someone with strong Python skills and experience with "
            "deep learning frameworks. Experience with MLOps and model deployment is a plus."
        ),
        required_skills=["Python", "Machine Learning", "TensorFlow", "SQL", "Deep Learning"],
        preferred_skills=["PyTorch", "Natural Language Processing", "Docker", "Kubernetes"],
        location="New York, NY",
        salary="$160,000 - $200,000",
        job_type="full-time",
        experience_level="mid",
        application_deadline="2026-07-30",
        contact_info="hr@datamind.ai",
        application_url="https://datamind.ai/jobs/ml-engineer",
        posted_date="2026-06-05",
        verified_status="verified",
        source_platform="indeed",
    )


def senior_manager_listing() -> VerifiedJobListing:
    """Leadership role, 10+ years required — experience-weighted test."""
    return VerifiedJobListing(
        job_id="job-003",
        company_name="Enterprise Corp",
        job_title="VP of Engineering",
        description=(
            "We're seeking a VP of Engineering to lead our 50-person engineering department. "
            "You'll set technical strategy, hire and develop engineering leaders, and drive "
            "the technical roadmap. 10+ years of software engineering experience and 5+ years "
            "of engineering leadership required."
        ),
        required_skills=["Leadership", "System Design", "Agile", "Microservices", "Cloud Computing"],
        preferred_skills=["Kubernetes", "AWS", "Google Cloud", "Project Management"],
        location="Seattle, WA",
        salary="$250,000 - $350,000",
        job_type="full-time",
        experience_level="senior",
        application_deadline="2026-08-01",
        contact_info="executive-recruiting@enterprise.com",
        application_url="https://enterprise.com/careers/vp-engineering",
        posted_date="2026-06-10",
        verified_status="verified",
        source_platform="linkedin",
    )


def remote_internship_listing() -> VerifiedJobListing:
    """Remote internship, entry-level — location + preference test."""
    return VerifiedJobListing(
        job_id="job-004",
        company_name="StartupLaunch",
        job_title="Software Engineering Intern",
        description=(
            "Exciting remote internship opportunity for aspiring software engineers. "
            "You'll work on real features for our web application using Python and JavaScript. "
            "Learn from experienced mentors in a supportive, fast-paced environment. "
            "No prior professional experience required."
        ),
        required_skills=["Python", "Git"],
        preferred_skills=["JavaScript", "HTML", "CSS", "SQL"],
        location="Remote",
        salary="$30/hour",
        job_type="internship",
        experience_level="entry",
        application_deadline="2026-07-01",
        contact_info="interns@startuplaunch.com",
        application_url="https://startuplaunch.com/internships",
        posted_date="2026-06-03",
        verified_status="verified",
        source_platform="indeed",
    )


def no_skills_listing() -> VerifiedJobListing:
    """Listing with empty required_skills — edge case handling."""
    return VerifiedJobListing(
        job_id="job-005",
        company_name="GeneralCo",
        job_title="General Associate",
        description="Looking for a general associate to join our team.",
        required_skills=[],
        preferred_skills=None,
        location="Chicago, IL",
        salary=None,
        job_type="full-time",
        experience_level=None,
        application_deadline=None,
        contact_info="hr@generalco.com",
        application_url=None,
        posted_date="2026-06-07",
        verified_status="verified",
        source_platform="indeed",
    )


def rejected_listing() -> VerifiedJobListing:
    """Rejected listing — should be filtered out during matching."""
    return VerifiedJobListing(
        job_id="job-006",
        company_name="SuspiciousCo",
        job_title="Software Engineer",
        description="Work from home and earn $500/day!!",
        required_skills=["Python"],
        location="Anywhere",
        posted_date="2026-06-01",
        verified_status="rejected",
        source_platform="indeed",
    )


def flagged_listing() -> VerifiedJobListing:
    """Flagged for review listing — should be filtered out during matching."""
    return VerifiedJobListing(
        job_id="job-007",
        company_name="UnverifiedStartup",
        job_title="Full Stack Developer",
        description="Join our growing team.",
        required_skills=["JavaScript", "React", "Node.js"],
        location="Austin, TX",
        posted_date="2026-06-02",
        verified_status="flagged_for_review",
        source_platform="linkedin",
    )


def frontend_developer_listing() -> VerifiedJobListing:
    """Frontend role — tests related skill matching (React ↔ Frontend Development)."""
    return VerifiedJobListing(
        job_id="job-008",
        company_name="DesignFirst Inc.",
        job_title="Senior Frontend Developer",
        description=(
            "We're looking for a senior frontend developer to lead our UI team. "
            "You'll build beautiful, responsive web applications using modern JavaScript "
            "frameworks. Strong understanding of UI/UX principles required."
        ),
        required_skills=["JavaScript", "React", "CSS", "HTML", "Frontend Development"],
        preferred_skills=["TypeScript", "Next.js", "Figma", "UI/UX Design"],
        location="Remote",
        salary="$150,000 - $180,000",
        job_type="full-time",
        experience_level="senior",
        posted_date="2026-06-08",
        verified_status="verified",
        source_platform="linkedin",
    )


def devops_engineer_listing() -> VerifiedJobListing:
    """DevOps role — tests for Docker/Kubernetes/CI-CD synonym matching."""
    return VerifiedJobListing(
        job_id="job-009",
        company_name="CloudOps Ltd.",
        job_title="DevOps Engineer",
        description=(
            "Build and maintain CI/CD pipelines, manage Kubernetes clusters, "
            "and automate infrastructure using Terraform. "
            "Strong Linux and scripting skills required."
        ),
        required_skills=["Docker", "Kubernetes", "CI/CD", "Terraform", "Linux", "AWS"],
        preferred_skills=["Python", "Go", "Ansible"],
        location="Seattle, WA",
        salary="$160,000 - $190,000",
        job_type="full-time",
        experience_level="mid",
        posted_date="2026-06-09",
        verified_status="verified",
        source_platform="indeed",
    )


def data_analyst_listing() -> VerifiedJobListing:
    """Data analyst role — good match for career_changer_profile."""
    return VerifiedJobListing(
        job_id="job-010",
        company_name="AnalyticsFirst",
        job_title="Data Analyst",
        description=(
            "Seeking a data analyst to drive business insights through data analysis. "
            "You'll work with SQL, Python, and Excel to analyze large datasets, "
            "create dashboards, and present findings to stakeholders."
        ),
        required_skills=["SQL", "Python", "Excel", "Data Analysis", "Statistics"],
        preferred_skills=["Tableau", "Power BI", "Communication"],
        location="Chicago, IL",
        salary="$80,000 - $100,000",
        job_type="full-time",
        experience_level="mid",
        posted_date="2026-06-04",
        verified_status="verified",
        source_platform="linkedin",
    )


def batch_listings_20() -> List[VerifiedJobListing]:
    """A batch of 20 diverse job listings for ranking and top-N tests."""
    base_listings = [
        software_engineer_listing(),
        data_scientist_listing(),
        senior_manager_listing(),
        remote_internship_listing(),
        no_skills_listing(),
        frontend_developer_listing(),
        devops_engineer_listing(),
        data_analyst_listing(),
    ]

    # Generate additional diverse listings
    extra_listings = []
    extra_data = [
        ("job-011", "Backend Developer", ["Python", "Django", "PostgreSQL", "REST API"], "Austin, TX", "full-time"),
        ("job-012", "Full Stack Engineer", ["JavaScript", "React", "Node.js", "MongoDB"], "Remote", "full-time"),
        ("job-013", "Cloud Architect", ["AWS", "Kubernetes", "Terraform", "System Design"], "Seattle, WA", "full-time"),
        ("job-014", "QA Engineer", ["Testing", "Selenium", "Python", "CI/CD"], "Denver, CO", "full-time"),
        ("job-015", "Mobile Developer", ["React Native", "JavaScript", "Mobile Development"], "San Francisco, CA", "full-time"),
        ("job-016", "Data Engineer", ["Python", "Apache Spark", "Kafka", "SQL", "Data Engineering"], "New York, NY", "full-time"),
        ("job-017", "Security Engineer", ["Cybersecurity", "Python", "Linux", "Network Security"], "Washington, DC", "full-time"),
        ("job-018", "Product Manager", ["Agile", "Communication", "Leadership", "JIRA"], "Remote", "full-time"),
        ("job-019", "Junior Python Dev", ["Python", "Git", "SQL"], "Boston, MA", "full-time"),
        ("job-020", "ML Research Scientist", ["Machine Learning", "Deep Learning", "Python", "PyTorch", "Statistics"], "Remote", "full-time"),
        ("job-021", "Blockchain Developer", ["Blockchain", "Python", "Cryptography"], "Remote", "contract"),
        ("job-022", "Technical Writer", ["Technical Writing", "Git", "Python"], "Remote", "part-time"),
    ]

    for jid, title, skills, loc, jtype in extra_data:
        extra_listings.append(
            VerifiedJobListing(
                job_id=jid,
                company_name=f"Company-{jid}",
                job_title=title,
                description=f"We are hiring a {title} with strong skills in {', '.join(skills)}.",
                required_skills=skills,
                location=loc,
                job_type=jtype,
                experience_level="mid",
                posted_date="2026-06-10",
                verified_status="verified",
                source_platform="linkedin",
            )
        )

    return base_listings + extra_listings
