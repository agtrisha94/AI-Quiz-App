from rest_framework.routers import DefaultRouter
from .views import QuizViewSet, QuizSubmissionViewSet

router = DefaultRouter()
router.register(r'quizzes', QuizViewSet, basename='quiz')
router.register(r'submissions', QuizSubmissionViewSet, basename='submission')

urlpatterns = router.urls