import asyncio


class ResolvablePromise:
    def __init__(self):
        self.future = asyncio.Future()
        self._is_resolved = False

    def resolve(self, value=None):
        self.future.set_result(value)
        self._is_resolved = True

    def reject(self, error):
        self.future.set_exception(error)
        self._is_resolved = True

    def is_resolved(self):
        return self._is_resolved

    def __await__(self):
        return self.future.__await__()


def create_exposed_promise():
    return ResolvablePromise()
