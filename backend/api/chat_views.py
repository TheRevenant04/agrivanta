from django.http import StreamingHttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from llm import LLMError

from .chat import prepare_chat, stream_chat


class ChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        question = request.data.get("question")
        if not isinstance(question, str) or not question.strip():
            return Response(
                {"detail": "A non-empty question is required."}, status=400
            )
        question = question.strip()
        if len(question) > 4000:
            return Response(
                {"detail": "The question must be 4000 characters or fewer."},
                status=400,
            )

        try:
            execution = prepare_chat(request.user, question)
        except LLMError:
            return Response(
                {"detail": "The chat service is temporarily unavailable."},
                status=503,
            )

        response = StreamingHttpResponse(
            stream_chat(execution), content_type="application/x-ndjson"
        )
        response["Cache-Control"] = "no-store"
        response["X-Accel-Buffering"] = "no"
        return response
