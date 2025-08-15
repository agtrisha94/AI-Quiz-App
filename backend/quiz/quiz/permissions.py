from rest_framework import permissions

class IsInstructorOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow instructors or admins to access certain views.
    """

    def has_permission(self, request, view):
        # Allow access if the user is authenticated and is an instructor or admin
        return request.user.is_authenticated and request.user.role in ['instructor', 'admin']


class CanGradeQuiz(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        # Allow access if the user is an admin or relevant instructor
        if request.user.role == 'admin':
            return True

        if request.user.role == 'instructor':
            if hasattr(obj, 'created_by'):  # Quiz object
                return obj.created_by == request.user
            elif hasattr(obj, 'quiz'):  # QuizSubmission object
                return obj.quiz.created_by == request.user
            elif hasattr(obj, 'submission'):  # Answer object
                return obj.submission.quiz.created_by == request.user

        return False