class AQAReviewError(Exception):
    """Base error with a message safe to show in the local UI."""


class InputError(AQAReviewError):
    pass


class AuthenticationError(AQAReviewError):
    pass


class ExternalServiceError(AQAReviewError):
    pass


class RepositoryError(AQAReviewError):
    pass


class ProviderError(AQAReviewError):
    pass


class ProviderRefusalError(ProviderError):
    pass
