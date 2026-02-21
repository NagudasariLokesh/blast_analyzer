class _App:
    def route(self, _path):
        def decorator(func):
            return func

        return decorator


app = _App()
