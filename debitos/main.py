import re
import asyncio
import argparse
from selenium_driverless.types.by import By
from utils.exposed_promise import create_exposed_promise
from utils.file_download_script import file_download_script
from utils import start_driver, move_mouse_around_element, type_with_delay, wait_for_element, race
from selenium_driverless.scripts.network_interceptor import (
    NetworkInterceptor,
    InterceptedRequest,
    RequestPattern,
    RequestStages,
)


parser = argparse.ArgumentParser(description="Certidao de debitos")
parser.add_argument("-d", "--doc", type=str, help="document number")
parser.add_argument("-t", "--type", type=str, help="document type: CNPJ or CPF")
args = parser.parse_args()

if args.doc:
    doc = re.sub(r"\D", "", args.doc)
else:
    print("Document number is required")
    exit()

if args.type.lower() == "cnpj":
    url = "https://solucoes.receita.fazenda.gov.br/Servicos/CertidaoInternet/PJ/Emitir"
    docType = "PJ"
elif args.type.lower() == "cpf":
    url = "https://solucoes.receita.fazenda.gov.br/Servicos/CertidaoInternet/PF/Emitir"
    docType = "PF"
else:
    print("Invalid document type, must be CNPJ or CPF")
    exit()

emit_url = f"https://solucoes.receita.fazenda.gov.br/Servicos/certidaointernet/{docType}/Emitir/Verificar"
result_url = f"https://solucoes.receita.fazenda.gov.br/Servicos/certidaointernet/{docType}/Emitir/ResultadoEmissao/"


async def on_request(data: InterceptedRequest):
    if "jquery.filedownload" in data.request.url:
        await data.continue_request(intercept_response=True)
    elif emit_url in data.request.url or result_url in data.request.url:
        await data.continue_request(intercept_response=True)
    else:
        await data.resume()


def handle_console_event(message):
    print(f"###########  {message} \n")
    if message.get("type", "") == "error" and "PDF DOWNLOADED" in message.get("args", [{}])[0].get("value", ""):
        print("Download started!!!!")


async def configure_cdp(driver):
    await driver.execute_cdp_cmd("Runtime.enable", {})
    await driver.execute_cdp_cmd("Page.enable", {})
    await driver.execute_cdp_cmd("DOM.enable", {})
    await driver.execute_cdp_cmd("Console.enable", {})
    await driver.execute_cdp_cmd("Network.enable", {})
    await driver.execute_cdp_cmd("Network.setBypassServiceWorker", {"bypass": True})
    await driver.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})
    await driver.add_cdp_listener("Runtime.consoleAPICalled", handle_console_event)


async def solve_image_captcha(driver):
    # image_selector = "img[alt='Red dot']"
    # captcha_input = "input[id='ans'][name='answer']"
    # captcha_submit_button = "button[id='jar'][type='button']"
    # Call yor favorite captcha resolver here
    print("Solving captcha...")


async def get_page_response(driver, submit_element, wait_emit_page_processing, wait_result_page_processing):
    await move_mouse_around_element(driver, submit_element, num_movements=1)
    await submit_element.click()
    print(1)
    await wait_emit_page_processing
    await driver.sleep(1)
    print(2)

    response = await race(
        wait_for_element(driver, By.CSS_SELECTOR, "input[id='ans'][name='answer']", "image_captcha"),
        wait_for_element(driver, By.CSS_SELECTOR, "a[href*='Emitir/EmProcessamento']", "emit_link"),
        wait_for_element(driver, By.CSS_SELECTOR, "input[type='button'][value='Nova consulta']", "finished"),
    )

    print(response)

    if response == "image_captcha":
        await solve_image_captcha(driver)

        response_after_captcha = await race(
            wait_for_element(driver, By.CSS_SELECTOR, "a[href*='Emitir/EmProcessamento']", "emit_link"),
            wait_for_element(driver, By.CSS_SELECTOR, "input[type='button'][value='Nova consulta']", "finished"),
        )

        if response_after_captcha == "emit_link":
            emit_link = await driver.find_element(By.CSS_SELECTOR, "a[href*='Emitir/EmProcessamento']")
            await emit_link.click()

    if response == "emit_link":
        emit_link = await driver.find_element(By.CSS_SELECTOR, "a[href*='Emitir/EmProcessamento']")
        await emit_link.click()

    print(3)
    await wait_result_page_processing
    await driver.sleep(1)
    print(4)

    await driver.sleep(999999)


async def main():
    driver = await start_driver()

    await configure_cdp(driver)

    await driver.get(url, wait_load=True)
    await driver.sleep(0.5)

    # This site can’t be reached

    input_element = await driver.find_element(By.CSS_SELECTOR, "#NI")

    await move_mouse_around_element(driver, input_element, num_movements=1)
    await type_with_delay(driver, input_element, doc)

    submit_element = await driver.find_element(By.CSS_SELECTOR, "#validar")
    wait_emit_page_processing = create_exposed_promise()
    wait_result_page_processing = create_exposed_promise()

    async with NetworkInterceptor(
        driver,
        on_request=on_request,
        patterns=[RequestPattern.AnyRequest],
    ) as interceptor:
        asyncio.ensure_future(
            get_page_response(driver, submit_element, wait_emit_page_processing, wait_result_page_processing)
        )

        async for data in interceptor:
            if "jquery.filedownload" in data.request.url:
                await driver.execute_script(file_download_script)

            if data.stage == RequestStages.Response:
                if emit_url in data.request.url:
                    body = await data.body
                    body_text = body.decode("utf-8", errors="ignore")
                    if "Consulta em processamento" not in body_text:
                        print("emit", 1)
                        wait_emit_page_processing.resolve()
                        print("emit", 2)

                if result_url in data.request.url:
                    body = await data.body
                    body_text = body.decode("utf-8", errors="ignore")
                    if "Consulta em processamento" not in body_text:
                        print("result", 1)
                        wait_result_page_processing.resolve()
                        print("result", 2)


asyncio.run(main())
