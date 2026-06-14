"""
Sample user profiles for testing Member 3 agents.
Each profile represents a different testing scenario.
"""

from models.matching_models import EducationEntry, ExperienceEntry, UserProfile


def full_profile() -> UserProfile:
    """Complete profile with all fields populated — happy path tests."""
    return UserProfile(
        user_id="user-001",
        full_name="Sarah Chen",
        email="sarah.chen@example.com",
        phone="+1-555-123-4567",
        location="San Francisco, CA",
        summary="Experienced full-stack software engineer with 5 years of experience "
                "building scalable web applications. Passionate about clean code and "
                "mentoring junior developers.",
        skills=[
            "Python", "JavaScript", "React", "Node.js", "PostgreSQL",
            "Docker", "AWS", "Git", "REST API", "Agile",
        ],
        experience=[
            ExperienceEntry(
                title="Senior Software Engineer",
                company="TechCorp Inc.",
                location="San Francisco, CA",
                start_date="2022-01-15",
                end_date=None,
                description="Lead development of microservices architecture serving 2M+ users. "
                            "Improved API response times by 40% through query optimization. "
                            "Mentored 3 junior engineers.",
                skills_used=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"],
            ),
            ExperienceEntry(
                title="Software Engineer",
                company="StartupXYZ",
                location="San Francisco, CA",
                start_date="2019-06-01",
                end_date="2021-12-31",
                description="Built and maintained React frontend and Node.js backend for "
                            "e-commerce platform. Implemented CI/CD pipeline reducing deployment "
                            "time by 60%.",
                skills_used=["JavaScript", "React", "Node.js", "Git", "CI/CD"],
            ),
        ],
        education=[
            EducationEntry(
                degree="Bachelor of Science",
                institution="Stanford University",
                field_of_study="Computer Science",
                start_date="2015-09-01",
                end_date="2019-05-30",
                gpa=3.8,
            ),
        ],
        certifications=["AWS Certified Developer Associate", "Certified Scrum Master"],
        languages=["English", "Mandarin"],
        goals="Senior engineering role at a product-focused company",
        preferred_locations=["San Francisco", "Remote", "New York"],
        preferred_job_types=["full-time", "remote"],
        resume_raw_text="Sarah Chen - Software Engineer with 5 years experience in Python, "
                        "JavaScript, React, and cloud infrastructure...",
    )


def minimal_profile() -> UserProfile:
    """Profile with only required fields — edge case: minimal input."""
    return UserProfile(
        user_id="user-002",
        full_name="John Doe",
        email="john.doe@example.com",
        location="Austin, TX",
        skills=["Python"],
    )


def empty_skills_profile() -> UserProfile:
    """Profile with no skills listed — error handling test."""
    return UserProfile(
        user_id="user-003",
        full_name="Jane Smith",
        email="jane.smith@example.com",
        location="Chicago, IL",
        skills=[],
    )


def senior_engineer_profile() -> UserProfile:
    """Senior profile with 10+ years experience, 15+ skills — high match scenarios."""
    return UserProfile(
        user_id="user-004",
        full_name="Michael Rodriguez",
        email="m.rodriguez@example.com",
        phone="+1-555-987-6543",
        location="Seattle, WA",
        summary="Distinguished software engineer with 12 years of experience in "
                "distributed systems, cloud architecture, and team leadership.",
        skills=[
            "Python", "Java", "Go", "Kubernetes", "Docker",
            "AWS", "Google Cloud", "PostgreSQL", "Redis", "Kafka",
            "Microservices", "System Design", "CI/CD", "Terraform",
            "Leadership", "Agile",
        ],
        experience=[
            ExperienceEntry(
                title="Principal Engineer",
                company="MegaTech Corp",
                location="Seattle, WA",
                start_date="2020-03-01",
                end_date=None,
                description="Architected company-wide microservices migration. Led team of 8 engineers. "
                            "Reduced infrastructure costs by $2M annually through cloud optimization.",
                skills_used=["Python", "Kubernetes", "AWS", "System Design", "Leadership"],
            ),
            ExperienceEntry(
                title="Staff Engineer",
                company="CloudFirst Inc.",
                location="Seattle, WA",
                start_date="2016-01-15",
                end_date="2020-02-28",
                description="Designed and built real-time data pipeline processing 10B+ events daily. "
                            "Established engineering best practices and code review culture.",
                skills_used=["Java", "Kafka", "Google Cloud", "Go", "Terraform"],
            ),
            ExperienceEntry(
                title="Senior Software Engineer",
                company="DataDriven LLC",
                location="Portland, OR",
                start_date="2012-06-01",
                end_date="2015-12-31",
                description="Built core data processing engine. Implemented automated testing framework "
                            "achieving 95% code coverage.",
                skills_used=["Python", "PostgreSQL", "Redis", "Docker", "CI/CD"],
            ),
        ],
        education=[
            EducationEntry(
                degree="Master of Science",
                institution="University of Washington",
                field_of_study="Computer Science",
                start_date="2010-09-01",
                end_date="2012-05-30",
                gpa=3.9,
            ),
            EducationEntry(
                degree="Bachelor of Science",
                institution="UC Berkeley",
                field_of_study="Electrical Engineering and Computer Science",
                start_date="2006-09-01",
                end_date="2010-05-30",
                gpa=3.7,
            ),
        ],
        certifications=[
            "AWS Solutions Architect Professional",
            "Google Cloud Professional Architect",
            "Certified Kubernetes Administrator",
        ],
        languages=["English", "Spanish"],
        goals="VP of Engineering or CTO role at a growth-stage company",
        preferred_locations=["Seattle", "Remote", "San Francisco"],
        preferred_job_types=["full-time"],
        resume_raw_text="Michael Rodriguez - Distinguished Engineer with 12 years...",
    )


def data_scientist_profile() -> UserProfile:
    """Data science focused profile — cross-domain matching tests."""
    return UserProfile(
        user_id="user-005",
        full_name="Priya Sharma",
        email="priya.sharma@example.com",
        location="New York, NY",
        summary="Data scientist with expertise in machine learning and NLP. "
                "Published researcher with industry experience in recommendation systems.",
        skills=[
            "Python", "R", "Machine Learning", "Deep Learning",
            "TensorFlow", "PyTorch", "Natural Language Processing",
            "SQL", "Pandas", "NumPy", "Statistics",
            "Data Analysis", "Data Science",
        ],
        experience=[
            ExperienceEntry(
                title="Senior Data Scientist",
                company="AI Solutions Corp",
                location="New York, NY",
                start_date="2021-04-01",
                end_date=None,
                description="Developed recommendation engine increasing user engagement by 35%. "
                            "Built NLP pipeline for sentiment analysis of 1M+ customer reviews.",
                skills_used=["Python", "TensorFlow", "Natural Language Processing", "SQL"],
            ),
            ExperienceEntry(
                title="Data Scientist",
                company="DataViz Inc.",
                location="Boston, MA",
                start_date="2018-08-01",
                end_date="2021-03-31",
                description="Created predictive models for customer churn with 92% accuracy. "
                            "Automated reporting pipeline saving 20 hours per week.",
                skills_used=["Python", "R", "Machine Learning", "Pandas", "Statistics"],
            ),
        ],
        education=[
            EducationEntry(
                degree="Master of Science",
                institution="Columbia University",
                field_of_study="Data Science",
                start_date="2016-09-01",
                end_date="2018-05-30",
                gpa=3.95,
            ),
        ],
        certifications=["Google Professional Machine Learning Engineer"],
        languages=["English", "Hindi"],
        goals="Lead ML Engineer or Head of Data Science",
        preferred_locations=["New York", "Remote"],
        preferred_job_types=["full-time", "remote"],
        resume_raw_text="Priya Sharma - Senior Data Scientist with NLP expertise...",
    )


def career_changer_profile() -> UserProfile:
    """Switching from finance to tech — low match with partial overlap tests."""
    return UserProfile(
        user_id="user-006",
        full_name="David Park",
        email="david.park@example.com",
        location="Chicago, IL",
        summary="Former financial analyst transitioning to tech. "
                "Self-taught Python developer with strong analytical skills.",
        skills=[
            "Python", "SQL", "Excel", "Data Analysis",
            "Statistics", "Communication", "Problem Solving",
        ],
        experience=[
            ExperienceEntry(
                title="Financial Analyst",
                company="Morgan Capital",
                location="Chicago, IL",
                start_date="2019-07-01",
                end_date="2024-01-31",
                description="Performed financial modeling and data analysis for $500M portfolio. "
                            "Created automated reports using Python and Excel macros.",
                skills_used=["Excel", "SQL", "Data Analysis", "Python"],
            ),
        ],
        education=[
            EducationEntry(
                degree="Bachelor of Science",
                institution="Northwestern University",
                field_of_study="Finance",
                start_date="2015-09-01",
                end_date="2019-05-30",
                gpa=3.5,
            ),
        ],
        certifications=["CFA Level 2"],
        languages=["English", "Korean"],
        goals="Entry-level software developer or data analyst role",
        preferred_locations=["Chicago", "Remote"],
        preferred_job_types=["full-time", "internship"],
        resume_raw_text="David Park - Financial Analyst transitioning to technology...",
    )


def fresh_graduate_profile() -> UserProfile:
    """No work experience, only education — entry-level matching tests."""
    return UserProfile(
        user_id="user-007",
        full_name="Emily Watson",
        email="emily.watson@example.com",
        location="Boston, MA",
        summary="Recent CS graduate looking for entry-level positions.",
        skills=["Python", "Java", "HTML", "CSS", "Git", "SQL"],
        experience=[],
        education=[
            EducationEntry(
                degree="Bachelor of Science",
                institution="MIT",
                field_of_study="Computer Science",
                start_date="2020-09-01",
                end_date="2024-05-30",
                gpa=3.6,
            ),
        ],
        certifications=[],
        languages=["English"],
        goals="Entry-level software engineering role",
        preferred_locations=["Boston", "New York", "Remote"],
        preferred_job_types=["full-time", "internship"],
    )
