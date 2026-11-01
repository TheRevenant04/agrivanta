from rest_framework.authentication import TokenAuthentication


class BearerTokenAuthentication(TokenAuthentication):
    """DRF token auth using the `Authorization: Bearer <token>` scheme."""

    keyword = "Bearer"
