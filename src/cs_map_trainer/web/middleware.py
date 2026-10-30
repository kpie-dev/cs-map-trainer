from django.utils.cache import add_never_cache_headers


class PrivateResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        private = request.user.is_authenticated or request.path.startswith("/accounts/")
        response = self.get_response(request)
        if private:
            add_never_cache_headers(response)
        return response
