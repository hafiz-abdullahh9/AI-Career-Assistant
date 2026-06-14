from rest_framework import serializers
from .models import User, UserSkill, Job, SkillGapAnalysis, InterviewSession

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'

class UserCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)

class UserSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSkill
        fields = '__all__'

class UserSkillCreateSerializer(serializers.Serializer):
    skill_name = serializers.CharField(max_length=100)
    proficiency_level = serializers.CharField(max_length=50)
    years_experience = serializers.FloatField(default=0.0)

class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = '__all__'

class JobCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    company_name = serializers.CharField(max_length=200)
    description = serializers.CharField()
    required_skills = serializers.JSONField(default=list)
    location = serializers.CharField(max_length=150)
    salary_min = serializers.FloatField(required=False, allow_null=True)
    salary_max = serializers.FloatField(required=False, allow_null=True)

class SkillGapAnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = SkillGapAnalysis
        fields = '__all__'

class SkillGapRequestSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    job_id = serializers.IntegerField()

class InterviewSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterviewSession
        fields = '__all__'

class InterviewStartRequestSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    job_id = serializers.IntegerField()

class AnswerSubmitRequestSerializer(serializers.Serializer):
    question_index = serializers.IntegerField()
    answer = serializers.CharField()
