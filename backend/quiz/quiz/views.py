from django.utils import timezone
from django.db.models import Prefetch
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

from .models import Quiz, Question, Option, QuizSubmission, Answer
from .serializers import (
    QuizReadStudentSerializer,
    QuizReadTeacherSerializer,
    QuizWriteSerializer,
    QuizSubmissionWriteSerializer,
    QuizSubmissionReadSerializer,
)
# Try to import project-specific permissions; fallback gracefully
try:
    from .permissions import IsInstructorOrAdmin, CanGradeQuiz
except Exception:  # pragma: no cover
    class IsInstructorOrAdmin(IsAuthenticated):
        pass
    class CanGradeQuiz(IsAuthenticated):
        pass

# ---- Quiz ViewSet ----

class QuizViewSet(viewsets.ModelViewSet):
    queryset = Quiz.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        # Read vs write
        if self.action in ["create", "update", "partial_update"]:
            return QuizWriteSerializer
        # Choose read serializer based on user role (very simple heuristic)
        if self.request and self.request.user and self.request.user.is_staff:
            return QuizReadTeacherSerializer
        return QuizReadStudentSerializer

    def get_queryset(self):
        qs = (
            Quiz.objects
            .select_related("lesson", "lesson__course")
            .prefetch_related(
                Prefetch("questions", queryset=Question.objects.prefetch_related("options"))
            )
        )
        # Optional filters
        lesson_id = self.request.query_params.get("lesson_id")
        is_published = self.request.query_params.get("is_published")
        if lesson_id:
            qs = qs.filter(lesson_id=lesson_id)
        if is_published is not None:
            if is_published.lower() in ("1", "true", "yes"):
                qs = qs.filter(is_published=True)
            elif is_published.lower() in ("0", "false", "no"):
                qs = qs.filter(is_published=False)
        return qs

    @action(detail=True, methods=["post"], permission_classes=[IsInstructorOrAdmin])
    def publish_quiz(self, request, pk=None):
        quiz = self.get_object()
        publish = request.data.get("is_published", True)
        quiz.is_published = bool(publish)
        quiz.save(update_fields=["is_published"])
        ser = self.get_serializer(quiz)
        return Response(ser.data)

# ---- Submissions ----

class QuizSubmissionViewSet(viewsets.ModelViewSet):
    queryset = QuizSubmission.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ["create"]:
            return QuizSubmissionWriteSerializer
        return QuizSubmissionReadSerializer

    def get_queryset(self):
        qs = (
            QuizSubmission.objects
            .select_related("quiz", "user")
            .prefetch_related(
                Prefetch("answers", queryset=Answer.objects.select_related("question").prefetch_related("selected_options"))
            )
        )
        # Students see only their submissions by default
        if not self.request.user.is_staff:
            qs = qs.filter(user=self.request.user)
        quiz_id = self.request.query_params.get("quiz")
        if quiz_id:
            qs = qs.filter(quiz_id=quiz_id)
        return qs

    @action(detail=True, methods=["post"], permission_classes=[CanGradeQuiz])
    def grade_submission(self, request, pk=None):
        submission = self.get_object()
        grades = request.data.get("grades", [])
        earned_map = {}
        for g in grades:
            ans_id = g.get("answer_id")
            pts = g.get("points_awarded", 0.0)
            if ans_id is not None:
                earned_map[ans_id] = float(pts)

        for ans in submission.answers.select_related("question").all():
            if ans.id in earned_map:
                # clamp to [0, question.points]
                pts = max(0.0, min(earned_map[ans.id], ans.question.points))
                ans.points_earned = pts
                ans.save()

        submission.graded_at = timezone.now()
        submission.status = "graded"
        submission.calculate_totals()
        submission.save()
        ser = self.get_serializer(submission)
        return Response(ser.data, status=status.HTTP_200_OK)
