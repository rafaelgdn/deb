import asyncio
from .exposed_promise import create_exposed_promise
from .__init__ import start_driver
from selenium_driverless.scripts.network_interceptor import (
    NetworkInterceptor,
    InterceptedRequest,
    RequestPattern,
)


async def on_request(data: InterceptedRequest, pdf_exposed_promise):
    print(f"Method: {data.request.method}, headers: {data.request.headers}")
    if (
        data.request.method == "GET"
        and "Content-Type" in data.request.headers
        and "pdf" in data.request.headers["Content-Type"].lower()
    ):
        print("PDF found!")
        pdf_exposed_promise.resolve()
        await data.resume()
    else:
        await data.resume()


async def intercept_request(func):
    driver = await start_driver()
    pdf_exposed_promise = create_exposed_promise()

    async def on_request_with_promise(request):
        await on_request(request, pdf_exposed_promise)

    async with NetworkInterceptor(driver, on_request=on_request_with_promise, patterns=[RequestPattern.AnyRequest]):
        await func(driver, pdf_exposed_promise)
