from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone

class Course(models.Model):
    title = models.CharField(max_length=255)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.title

class Lesson(models.Model):
    title = models.CharField(max_length=255)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.course} • {self.title}"

class Quiz(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="quizzes")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    duration = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.lesson})"

    @property
    def is_active_now(self):
        now = timezone.now()
        if self.start_time and now < self.start_time:
            return False
        if self.end_time and now > self.end_time:
            return False
        return self.is_published

QUESTION_TYPES = (
    ("mcq", "Multiple Choice"),
    ("truefalse", "True/False"),
    ("subjective", "Subjective"),
)

class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default="mcq")
    points = models.FloatField(default=1.0, validators=[MinValueValidator(0.0)])

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Q{self.id} • {self.question_type} • {self.quiz}"

class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    option_text = models.CharField(max_length=1000)
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Opt{self.id} • Q{self.question_id}"

SUB_STATUS = (
    ("draft", "Draft"),
    ("submitted", "Submitted"),
    ("graded", "Graded"),
)

class QuizSubmission(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="submissions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_submissions")
    submitted_at = models.DateTimeField(null=True, blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=SUB_STATUS, default="draft")
    total_points_earned = models.FloatField(default=0.0, validators=[MinValueValidator(0.0)])
    total_points_possible = models.FloatField(default=0.0, validators=[MinValueValidator(0.0)])
    percentage = models.FloatField(default=0.0, validators=[MinValueValidator(0.0)])

    class Meta:
        ordering = ["-submitted_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["quiz", "user"], name="unique_quiz_submission_per_user")
        ]

    def __str__(self):
        return f"Submission u{self.user_id} • quiz {self.quiz_id} • {self.status}"

    def calculate_totals(self):
        self.total_points_possible = sum(a.question.points for a in self.answers.select_related("question").all())
        self.total_points_earned = sum(a.points_earned for a in self.answers.all())
        self.percentage = (self.total_points_earned / self.total_points_possible * 100.0) if self.total_points_possible else 0.0

class Answer(models.Model):
    submission = models.ForeignKey(QuizSubmission, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    selected_options = models.ManyToManyField(Option, blank=True, related_name="answers")
    text_answer = models.TextField(blank=True)
    points_earned = models.FloatField(default=0.0, validators=[MinValueValidator(0.0)])

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["submission", "question"], name="unique_answer_per_question_per_submission")
        ]

    def __str__(self):
        return f"Ans{self.id} • Sub{submission_id} • Q{self.question_id}"

    def auto_grade_mcq(self):
        if self.question.question_type not in ("mcq", "truefalse"):
            return
        correct_ids = set(self.question.options.filter(is_correct=True).values_list("id", flat=True))
        chosen_ids = set(self.selected_options.values_list("id", flat=True))
        self.points_earned = self.question.points if correct_ids == chosen_ids and len(chosen_ids) > 0 else 0.0
        self.save()
