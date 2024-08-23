import asyncio


class ResolvablePromise:
    def __init__(self):
        self.future = asyncio.Future()

    def resolve(self, value=None):
        self.future.set_result(value)

    def reject(self, error):
        self.future.set_exception(error)

    def __await__(self):
        return self.future.__await__()


def create_exposed_promise():
    return ResolvablePromise()
