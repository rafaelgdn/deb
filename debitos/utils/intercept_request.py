import os
from .exposed_promise import create_exposed_promise
from .__init__ import start_driver
from selenium_driverless.scripts.network_interceptor import (
    NetworkInterceptor,
    InterceptedRequest,
)


async def on_request(data: InterceptedRequest, pdf_exposed_promise):
    if "certidaointernet/Scripts/certidao.emissao.js" in data.request.url:
        print("⬇️  PDF download has been successfully started ⬇️")
        pdf_exposed_promise.resolve()
        await data.resume()
    else:
        await data.resume()


async def intercept_request(func):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    current_dir_abspath = os.path.abspath(current_dir)
    downloads_dir = os.path.join(current_dir_abspath, "..", "downloads")
    downloads_dir_abspath = os.path.abspath(downloads_dir)

    pdf_exposed_promise = create_exposed_promise()
    driver = await start_driver(downloads_dir=downloads_dir_abspath)
    await driver.set_download_behaviour("allow", path=downloads_dir_abspath)

    async def on_request_with_promise(request):
        await on_request(request, pdf_exposed_promise)

    async with NetworkInterceptor(
        driver,
        on_request=on_request_with_promise,
        patterns=[{"resquestStage": "Request", "urlPattern": "*certidaointernet/Scripts/certidao.emissao.js*"}],
    ):
        await func(driver, pdf_exposed_promise)
