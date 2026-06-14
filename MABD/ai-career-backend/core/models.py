from django.db import models

class User(models.Model):
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"


class UserSkill(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='skills')
    skill_name = models.CharField(max_length=100, db_index=True)
    proficiency_level = models.CharField(max_length=50)  # Beginner, Intermediate, Expert
    years_experience = models.FloatField(default=0.0)

    def __str__(self):
        return f"{self.user.first_name} - {self.skill_name} ({self.proficiency_level})"


class Job(models.Model):
    title = models.CharField(max_length=200, db_index=True)
    company_name = models.CharField(max_length=200, db_index=True)
    description = models.TextField()
    required_skills = models.JSONField(default=list)  # list of strings e.g. ["Python", "FastAPI"]
    location = models.CharField(max_length=150)
    salary_min = models.FloatField(null=True, blank=True)
    salary_max = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} at {self.company_name}"


class SkillGapAnalysis(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='analyses')
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='analyses')
    missing_skills = models.JSONField(default=list)  # list of dicts
    proficiency_gap = models.JSONField(default=list)  # list of dicts
    learning_roadmap = models.JSONField(default=list)  # list of dicts
    salary_projection = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Skill Gap for {self.user.email} - Job {self.job.id}"


class InterviewSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='interviews')
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='interviews')
    question_set = models.JSONField(default=list)  # list of strings
    responses = models.JSONField(default=list)  # list of strings
    feedback = models.JSONField(default=dict)  # dict containing details
    score = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=50, default='started')  # started, completed, evaluated
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Interview {self.id} for {self.user.email} (Status: {self.status})"
