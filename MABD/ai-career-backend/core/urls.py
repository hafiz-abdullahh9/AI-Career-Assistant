from django.urls import path
from . import views

urlpatterns = [
    # User and Skills endpoints
    path('users/', views.create_user, name='create_user'),
    path('users/<int:user_id>/skills/', views.user_skills, name='user_skills'),

    # Jobs endpoints
    path('jobs/', views.jobs_list, name='jobs_list'),

    # Skill Gap Analysis endpoints
    path('analysis/run/', views.run_analysis, name='run_analysis'),
    path('analysis/history/<int:user_id>/', views.analysis_history, name='analysis_history'),
    path('analysis/<int:analysis_id>/report/', views.get_analysis_report, name='get_analysis_report'),

    # Interview Preparation endpoints
    path('interview/start/', views.start_interview, name='start_interview'),
    path('interview/<int:session_id>/', views.interview_session_detail, name='session_detail'),
    path('interview/<int:session_id>/evaluate/', views.evaluate_interview, name='evaluate_interview'),
]
