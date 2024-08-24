from utils import start_driver, move_mouse_around_element, type_with_delay, wait_for_element, race
from utils.fileDownloadScript import fileDownloadScript
from selenium_driverless.scripts.network_interceptor import NetworkInterceptor, InterceptedRequest
from selenium_driverless.types.by import By
import re
import asyncio
import argparse

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
elif args.type.lower() == "cpf":
    url = "https://solucoes.receita.fazenda.gov.br/Servicos/CertidaoInternet/PF/Emitir"
else:
    print("Invalid document type, must be CNPJ or CPF")
    exit()


async def on_request(data: InterceptedRequest):
    await data.resume()


def handle_console_event(message):
    print(f"###########  {message} \n")
    if message.get("type", "") == "error" and "PDF DOWNLOADED" in message.get("args", [])[0].get("value", ""):
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


async def get_page_response(driver, submit_element):
    await move_mouse_around_element(driver, submit_element, num_movements=1)
    await submit_element.click()
    await driver.sleep(10)

    element = await driver.find_element(By.CSS_SELECTOR, "a[href*='Emitir/EmProcessamento']")
    await element.click()

    # element = await race(
    #     wait_for_element(driver, By.CSS_SELECTOR, "a[href*='Emitir/EmProcessamento']"),
    #     wait_for_element(driver, By.CSS_SELECTOR, "input[type='button'][value='Nova consulta']"),
    # )

    # if element.tag_name == "a":
    #     await element.click()
    #     element = await wait_for_element(driver, By.CSS_SELECTOR, "input[type='button'][value='Nova consulta']")

    # print(element.text)

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

    async with NetworkInterceptor(
        driver,
        on_request=on_request,
        patterns=[{"resquestStage": "Response", "urlPattern": "*certidaointernet/Scripts/jquery.filedownload*"}],
    ) as interceptor:
        asyncio.ensure_future(get_page_response(driver, submit_element))

        async for data in interceptor:
            if "jquery.filedownload" in data.request.url:
                await driver.execute_script(fileDownloadScript)


asyncio.run(main())
