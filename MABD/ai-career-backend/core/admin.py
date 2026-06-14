from django.contrib import admin
from .models import User, UserSkill, Job, SkillGapAnalysis, InterviewSession

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'email', 'first_name', 'last_name', 'created_at')
    search_fields = ('email', 'first_name', 'last_name')

@admin.register(UserSkill)
class UserSkillAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'skill_name', 'proficiency_level', 'years_experience')
    list_filter = ('proficiency_level',)
    search_fields = ('skill_name', 'user__email')

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'company_name', 'location', 'salary_min', 'salary_max', 'created_at')
    search_fields = ('title', 'company_name', 'location')

@admin.register(SkillGapAnalysis)
class SkillGapAnalysisAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'job', 'salary_projection', 'created_at')
    search_fields = ('user__email', 'job__title')

@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'job', 'score', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('user__email', 'job__title')
