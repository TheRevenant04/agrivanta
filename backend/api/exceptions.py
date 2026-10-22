from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class ApiError(APIException):
    """A contract error: `{detail, field?}` with an explicit status code."""

    def __init__(self, detail, status_code=status.HTTP_400_BAD_REQUEST, field=None):
        self.status_code = status_code
        self.detail = detail
        self.field = field
        super().__init__(detail)


def api_exception_handler(exc, context):
    if isinstance(exc, ApiError):
        payload = {"detail": str(exc.detail)}
        if exc.field:
            payload["field"] = exc.field
        return Response(payload, status=exc.status_code)

    response = drf_exception_handler(exc, context)

    if response is not None and response.status_code == status.HTTP_404_NOT_FOUND:
        response.data = {"detail": "Not found."}

    return response
