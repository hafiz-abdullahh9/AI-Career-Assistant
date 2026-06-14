from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import User, UserSkill, Job, SkillGapAnalysis, InterviewSession
from .serializers import (
    UserSerializer, UserCreateSerializer,
    UserSkillSerializer, UserSkillCreateSerializer,
    JobSerializer, JobCreateSerializer,
    SkillGapAnalysisSerializer, SkillGapRequestSerializer,
    InterviewSessionSerializer, InterviewStartRequestSerializer,
    AnswerSubmitRequestSerializer
)
from .services import (
    analyze_skill_gap, start_interview_session,
    submit_interview_response, evaluate_interview_session
)

# --- User & Skills View Endpoints ---

@api_view(['POST'])
def create_user(request):
    serializer = UserCreateSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        if User.objects.filter(email=email).exists():
            return Response({"detail": "Email already registered"}, status=status.HTTP_400_BAD_REQUEST)
        
        db_user = User.objects.create(
            email=email,
            first_name=serializer.validated_data['first_name'],
            last_name=serializer.validated_data['last_name']
        )
        return Response(UserSerializer(db_user).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST', 'GET'])
def user_skills(request, user_id):
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        serializer = UserSkillCreateSerializer(data=request.data)
        if serializer.is_valid():
            db_skill = UserSkill.objects.create(
                user=user,
                skill_name=serializer.validated_data['skill_name'],
                proficiency_level=serializer.validated_data['proficiency_level'],
                years_experience=serializer.validated_data['years_experience']
            )
            return Response(UserSkillSerializer(db_skill).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    elif request.method == 'GET':
        skills = UserSkill.objects.filter(user=user)
        return Response(UserSkillSerializer(skills, many=True).data)


# --- Jobs View Endpoints ---

@api_view(['POST', 'GET'])
def jobs_list(request):
    if request.method == 'POST':
        serializer = JobCreateSerializer(data=request.data)
        if serializer.is_valid():
            db_job = Job.objects.create(
                title=serializer.validated_data['title'],
                company_name=serializer.validated_data['company_name'],
                description=serializer.validated_data['description'],
                required_skills=serializer.validated_data['required_skills'],
                location=serializer.validated_data['location'],
                salary_min=serializer.validated_data.get('salary_min'),
                salary_max=serializer.validated_data.get('salary_max')
            )
            return Response(JobSerializer(db_job).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    elif request.method == 'GET':
        jobs = Job.objects.all()
        return Response(JobSerializer(jobs, many=True).data)


# --- Skill Gap View Endpoints ---

@api_view(['POST'])
def run_analysis(request):
    serializer = SkillGapRequestSerializer(data=request.data)
    if serializer.is_valid():
        try:
            analysis = analyze_skill_gap(
                user_id=serializer.validated_data['user_id'],
                job_id=serializer.validated_data['job_id']
            )
            return Response(SkillGapAnalysisSerializer(analysis).data)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def analysis_history(request, user_id):
    user = get_object_or_404(User, id=user_id)
    history = SkillGapAnalysis.objects.filter(user=user)
    return Response(SkillGapAnalysisSerializer(history, many=True).data)


@api_view(['GET'])
def get_analysis_report(request, analysis_id):
    analysis = get_object_or_404(SkillGapAnalysis, id=analysis_id)
    return Response(SkillGapAnalysisSerializer(analysis).data)


# --- Interview Prep View Endpoints ---

@api_view(['POST'])
def start_interview(request):
    serializer = InterviewStartRequestSerializer(data=request.data)
    if serializer.is_valid():
        try:
            db_session = start_interview_session(
                user_id=serializer.validated_data['user_id'],
                job_id=serializer.validated_data['job_id']
            )
            return Response(InterviewSessionSerializer(db_session).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST', 'GET'])
def interview_session_detail(request, session_id):
    db_session = get_object_or_404(InterviewSession, id=session_id)
    
    if request.method == 'GET':
        return Response(InterviewSessionSerializer(db_session).data)
        
    elif request.method == 'POST':
        serializer = AnswerSubmitRequestSerializer(data=request.data)
        if serializer.is_valid():
            try:
                updated_session = submit_interview_response(
                    session_id=session_id,
                    question_index=serializer.validated_data['question_index'],
                    answer=serializer.validated_data['answer']
                )
                return Response(InterviewSessionSerializer(updated_session).data)
            except ValueError as e:
                return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def evaluate_interview(request, session_id):
    try:
        updated_session = evaluate_interview_session(session_id=session_id)
        return Response(InterviewSessionSerializer(updated_session).data)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
