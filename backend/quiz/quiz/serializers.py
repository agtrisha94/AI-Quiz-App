from rest_framework import serializers
from django.utils import timezone
from .models import Quiz, Question, Option, QuizSubmission, Answer

# ---------- Read serializers ----------

class OptionStudentSerializer(serializers.ModelSerializer):
    # Hide is_correct from students
    class Meta:
        model = Option
        fields = ["id", "option_text"]

class OptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = ["id", "option_text", "is_correct"]

class QuestionReadSerializer(serializers.ModelSerializer):
    options = OptionStudentSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ["id", "question_text", "question_type", "points", "options"]

class QuestionTeacherReadSerializer(serializers.ModelSerializer):
    options = OptionSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ["id", "question_text", "question_type", "points", "options"]

class QuizReadStudentSerializer(serializers.ModelSerializer):
    questions = QuestionReadSerializer(many=True, read_only=True)

    class Meta:
        model = Quiz
        fields = ["id", "lesson", "title", "description", "start_time", "end_time", "duration", "is_published", "questions"]

class QuizReadTeacherSerializer(serializers.ModelSerializer):
    questions = QuestionTeacherReadSerializer(many=True, read_only=True)

    class Meta:
        model = Quiz
        fields = ["id", "lesson", "title", "description", "start_time", "end_time", "duration", "is_published", "questions"]

# ---------- Write serializers (nested) ----------

class OptionWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = ["id", "option_text", "is_correct"]

class QuestionWriteSerializer(serializers.ModelSerializer):
    options = OptionWriteSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = ["id", "question_text", "question_type", "points", "options"]

    def validate(self, attrs):
        options = self.initial_data.get("options", [])
        qtype = attrs.get("question_type", self.instance.question_type if self.instance else None)
        if qtype in ("mcq", "truefalse"):
            if not options:
                raise serializers.ValidationError("MCQ/True-False question must include options.")
            if not any(opt.get("is_correct") for opt in options):
                raise serializers.ValidationError("At least one option must be marked correct.")
        return attrs

class QuizWriteSerializer(serializers.ModelSerializer):
    questions = QuestionWriteSerializer(many=True, required=False)

    class Meta:
        model = Quiz
        fields = ["id", "lesson", "title", "description", "start_time", "end_time", "duration", "is_published", "questions"]

    def validate(self, attrs):
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start and end and end <= start:
            raise serializers.ValidationError("end_time must be after start_time.")
        return attrs

    def create(self, validated_data):
        questions_data = validated_data.pop("questions", [])
        quiz = Quiz.objects.create(**validated_data)

        for qd in questions_data:
            options_data = qd.pop("options", [])
            question = Question.objects.create(quiz=quiz, **qd)
            if options_data:
                Option.objects.bulk_create([Option(question=question, **od) for od in options_data])
        return quiz

    def update(self, instance, validated_data):
        questions_data = validated_data.pop("questions", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()

        if questions_data is not None:
            # replace-all semantics for simplicity
            instance.questions.all().delete()
            for qd in questions_data:
                options_data = qd.pop("options", [])
                question = Question.objects.create(quiz=instance, **qd)
                if options_data:
                    Option.objects.bulk_create([Option(question=question, **od) for od in options_data])
        return instance

# ---------- Submission serializers ----------

class AnswerWriteSerializer(serializers.ModelSerializer):
    selected_options = serializers.PrimaryKeyRelatedField(queryset=Option.objects.all(), many=True, required=False)

    class Meta:
        model = Answer
        fields = ["id", "question", "selected_options", "text_answer"]

class QuizSubmissionWriteSerializer(serializers.ModelSerializer):
    answers = AnswerWriteSerializer(many=True)

    class Meta:
        model = QuizSubmission
        fields = ["id", "quiz", "answers"]

    def validate(self, attrs):
        quiz = attrs["quiz"]
        now = timezone.now()
        if not quiz.is_published:
            raise serializers.ValidationError("Quiz is not published.")
        if quiz.start_time and now < quiz.start_time:
            raise serializers.ValidationError("Quiz has not started yet.")
        if quiz.end_time and now > quiz.end_time:
            raise serializers.ValidationError("Quiz has ended.")
        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        quiz = validated_data["quiz"]
        answers_data = validated_data.pop("answers")

        submission, created = QuizSubmission.objects.get_or_create(quiz=quiz, user=user)
        # reset old answers
        submission.answers.all().delete()

        total_possible = 0.0
        for ad in answers_data:
            q = ad["question"]
            selected_opts = ad.get("selected_options", [])
            text = ad.get("text_answer", "")
            ans = Answer.objects.create(submission=submission, question=q, text_answer=text)
            if selected_opts:
                ans.selected_options.set(selected_opts)
            if q.question_type in ("mcq", "truefalse"):
                ans.auto_grade_mcq()
            total_possible += q.points

        submission.submitted_at = timezone.now()
        submission.status = "submitted"
        submission.calculate_totals()
        submission.save()
        return submission

class AnswerReadSerializer(serializers.ModelSerializer):
    selected_options = OptionStudentSerializer(many=True, read_only=True)
    question = QuestionReadSerializer(read_only=True)

    class Meta:
        model = Answer
        fields = ["id", "question", "selected_options", "text_answer", "points_earned"]

class QuizSubmissionReadSerializer(serializers.ModelSerializer):
    answers = AnswerReadSerializer(many=True, read_only=True)

    class Meta:
        model = QuizSubmission
        fields = ["id", "quiz", "submitted_at", "graded_at", "status", "total_points_earned", "total_points_possible", "percentage", "answers"]
