import os
import re
import time
import base64
import asyncio
import argparse
from bs4 import BeautifulSoup
from selenium_driverless.types.by import By
from utils.exposed_promise import create_exposed_promise
from utils.file_download_script import file_download_script
from utils import start_driver, move_mouse_around_element, type_with_delay, wait_for_element, race, click_and_check
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
    p_type = "PJ"
elif args.type.lower() == "cpf":
    p_type = "PF"
else:
    print("Invalid document type, must be CNPJ or CPF")
    exit()

url = f"https://solucoes.receita.fazenda.gov.br/Servicos/CertidaoInternet/{p_type}/Emitir"
emit_url = f"https://solucoes.receita.fazenda.gov.br/Servicos/certidaointernet/{p_type}/Emitir/Verificar"
result_url = f"https://solucoes.receita.fazenda.gov.br/Servicos/certidaointernet/{p_type}/Emitir/ResultadoEmissao/"
processing_url = f"https://solucoes.receita.fazenda.gov.br/Servicos/certidaointernet/{p_type}/Emitir/EmProcessamento"
result_html = None


async def on_request(data: InterceptedRequest):
    if "jquery.filedownload" in data.request.url:
        await data.continue_request(intercept_response=True)
    elif emit_url in data.request.url or result_url in data.request.url or processing_url in data.request.url:
        await data.continue_request(intercept_response=True)
    else:
        await data.resume()


def handle_console_event(message, wait_pdf_download):
    if (
        message.get("type", "") == "error"
        and "PDF DOWNLOADED" in message.get("args", [{}])[0].get("value", "")
        and not wait_pdf_download.is_resolved()
    ):
        wait_pdf_download.resolve("pdf_downloaded")


async def submit_and_verify(driver, verify_url=True):
    retries = 0

    while retries < 10:
        try:
            retries += 1
            current_url = await driver.current_url
            input_element = await driver.find_element(By.CSS_SELECTOR, "#NI")

            await input_element.clear()
            await move_mouse_around_element(driver, input_element, num_movements=1)
            await type_with_delay(driver, input_element, doc)

            submit_element = await driver.find_element(By.CSS_SELECTOR, "#validar")

            await submit_element.click()
            await driver.sleep(5)

            new_url = await driver.current_url

            if current_url == new_url:
                is_invalid_doc = await driver.find_elements(By.CSS_SELECTOR, "#mensagem")
                text = await is_invalid_doc[0].text
                if "inválido" in text:
                    return "doc_invalid"

            if not verify_url:
                return

            if new_url != current_url:
                return

            await driver.refresh()
            await driver.sleep(2)
        except Exception:
            await driver.refresh()
            await driver.sleep(5)

    if retries >= 10:
        raise Exception("Failed to submit the form after multiple attempts")


async def handle_page_errors(
    driver, wait_pdf_download, wait_result_page_processing, wait_processing_page_loaded, wait_emit_page_processing
):
    await driver.sleep(2)
    retries = 0

    while retries < 10:
        try:
            if (
                wait_pdf_download.is_resolved()
                or wait_result_page_processing.is_resolved()
                or wait_processing_page_loaded.is_resolved()
            ):
                return

            content = await driver.page_source

            if wait_emit_page_processing.is_resolved():
                if "O número informado não consta" in content:
                    return

            if (
                "ERR_CONNECTION_RESET" not in content
                and "Connection reset" not in content
                and "This site can't be reached" not in content
            ):
                break

            print("Connection error, retrying...")
            retries += 1
            await driver.refresh()
            await driver.sleep(5)
        except Exception:
            pass

    if retries >= 10:
        raise Exception("Failed to load page")


async def handle_result_page_errors(driver, wait_pdf_download, wait_result_page_processing, wait_emit_page_processing):
    await driver.sleep(3)
    retries = 0

    while retries < 10:
        retries += 1

        if wait_pdf_download.is_resolved() or wait_result_page_processing.is_resolved():
            return

        if wait_emit_page_processing.is_resolved():
            content = await driver.page_source
            if "O número informado não consta" in content:
                return

        current_url = await driver.current_url

        if retries >= 2 and (url in current_url or emit_url in current_url):
            has_input = await driver.find_elements(By.CSS_SELECTOR, "#NI")
            if has_input:
                has_dialog_button = await driver.find_elements(By.CSS_SELECTOR, "#dialog-message + div button")
                if has_dialog_button:
                    await has_dialog_button[0].click()
                    await driver.sleep(0.5)
                await submit_and_verify(driver, verify_url=False)
                await driver.sleep(6)

        print("Result page error, retrying...")
        await driver.refresh()
        await driver.sleep(5)

    if retries >= 10:
        raise Exception("Failed to download PDF")


async def is_result_page(driver, timeout=30):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            url = await driver.current_url
            if result_url in url or processing_url in url or emit_url in url:
                if emit_url not in url:
                    return "result_page"
                try:
                    await driver.sleep(1)
                    link_exists = await driver.find_elements(By.CSS_SELECTOR, "a[href*='Emitir/EmProcessamento']")
                    if link_exists:
                        return "emit_page"
                    else:
                        return "result_page"
                except Exception:
                    return "result_page"
            await driver.sleep(1)
        except Exception:
            pass


def extract_message(text):
    text_clear = text.strip()
    rows = text_clear.split("\n")
    rows_with_content = [row.strip() for row in rows if row.strip()]
    if rows_with_content:
        return rows_with_content[-1]
    else:
        return "No message found."


def extract_message_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    message_element = soup.css.select("#rfb-main-container > div")
    if message_element:
        text = message_element[0].text.strip()
        message = extract_message(text)
        return message
    else:
        return "No message found."


async def get_result_infos(
    driver, wait_pdf_download, wait_result_page_processing, wait_emit_page_processing, result=None
):
    global result_html
    print("Getting result infos...")
    await handle_result_page_errors(driver, wait_pdf_download, wait_result_page_processing, wait_emit_page_processing)

    if wait_pdf_download.is_resolved():
        print("pdf promise resolved...")
        result = await handle_pdf_download()
        return result

    if wait_result_page_processing.is_resolved():
        print("result page promise resolved...")
        if result_html:
            message = extract_message_from_html(result_html)
        else:
            await wait_for_element(driver, By.CSS_SELECTOR, "#rfb-main-container > div", "none")
            main_container = await driver.find_element(By.CSS_SELECTOR, "#rfb-main-container > div")
            text = await main_container.text
            message = extract_message(text)

        return {
            "document": doc,
            "obs": message,
            "file": None,
        }

    if wait_emit_page_processing.is_resolved():
        print("emit page promise resolved...")
        main_container = await driver.find_element(By.CSS_SELECTOR, "#rfb-main-container > div")
        text = await main_container.text
        message = extract_message(text)

        return {
            "document": doc,
            "obs": message,
            "file": None,
        }

    return result


async def configure_cdp(driver, wait_pdf_download):
    await driver.execute_cdp_cmd("Runtime.enable", {})
    await driver.execute_cdp_cmd("Page.enable", {})
    await driver.execute_cdp_cmd("DOM.enable", {})
    await driver.execute_cdp_cmd("Console.enable", {})
    await driver.execute_cdp_cmd("Network.enable", {})
    await driver.execute_cdp_cmd("Network.setBypassServiceWorker", {"bypass": True})
    await driver.add_cdp_listener(
        "Runtime.consoleAPICalled", lambda message: handle_console_event(message, wait_pdf_download)
    )


async def solve_image_captcha(driver):
    # image_selector = "img[alt='Red dot']"
    # captcha_input = "input[id='ans'][name='answer']"
    # captcha_submit_button = "button[id='jar'][type='button']"
    # Call yor favorite captcha resolver here
    print("Solving captcha...")


async def handle_pdf_download():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    downloads_dir = os.path.join(current_dir, "downloads")

    files = [f for f in os.listdir(downloads_dir) if os.path.isfile(os.path.join(downloads_dir, f))]

    if not files:
        raise Exception("No files found in the downloads folder")

    latest_file = max(files, key=lambda f: os.path.getmtime(os.path.join(downloads_dir, f)))
    file_path = os.path.join(downloads_dir, latest_file)

    with open(file_path, "rb") as file:
        file_content = file.read()
        file_base64 = base64.b64encode(file_content).decode("utf-8")

    result = {
        "document": doc,
        "obs": "A certidão foi emitida com sucesso",
        "file": file_base64,
    }

    return result


async def get_page_response(
    driver,
    wait_emit_page_processing,
    wait_result_page_processing,
    wait_pdf_download,
    wait_page_response,
    wait_processing_page_loaded,
):
    verify_response = await submit_and_verify(driver)

    if verify_response == "doc_invalid":
        result = {
            "document": doc,
            "obs": "Documento inválido",
            "file": None,
        }
        wait_page_response.resolve(result)
        await driver.refresh()
        return

    await handle_page_errors(
        driver, wait_pdf_download, wait_result_page_processing, wait_processing_page_loaded, wait_emit_page_processing
    )

    first_response = await race(
        wait_for_element(driver, By.CSS_SELECTOR, "input[id='ans'][name='answer']", "image_captcha"),
        wait_emit_page_processing,
        is_result_page(driver),
    )

    if first_response == "result_page":
        result = await get_result_infos(
            driver, wait_pdf_download, wait_result_page_processing, wait_emit_page_processing
        )
        wait_page_response.resolve(result)
        return

    if first_response == "image_captcha":
        await solve_image_captcha(driver)
        captcha_response = await race(wait_emit_page_processing, is_result_page(driver))
        if captcha_response == "result_page":
            result = await get_result_infos(
                driver, wait_pdf_download, wait_result_page_processing, wait_emit_page_processing
            )
            wait_page_response.resolve(result)
            return

    await driver.sleep(1)

    second_response = await race(
        wait_for_element(driver, By.CSS_SELECTOR, "a[href*='Emitir/EmProcessamento']", "emit_link"),
        is_result_page(driver),
    )

    if second_response == "emit_link":
        await click_and_check("a[href*='Emitir/EmProcessamento']", driver)

    await handle_page_errors(
        driver, wait_pdf_download, wait_result_page_processing, wait_processing_page_loaded, wait_emit_page_processing
    )

    result = await get_result_infos(driver, wait_pdf_download, wait_result_page_processing, wait_emit_page_processing)
    wait_page_response.resolve(result)
    return


async def main():
    driver = await start_driver()

    wait_emit_page_processing = create_exposed_promise()
    wait_processing_page_loaded = create_exposed_promise()
    wait_result_page_processing = create_exposed_promise()
    wait_pdf_download = create_exposed_promise()
    wait_page_response = create_exposed_promise()

    await configure_cdp(driver, wait_pdf_download)

    await driver.get(url, wait_load=True)
    await driver.sleep(0.5)

    await handle_page_errors(
        driver, wait_pdf_download, wait_result_page_processing, wait_processing_page_loaded, wait_emit_page_processing
    )

    async with NetworkInterceptor(
        driver,
        on_request=on_request,
        patterns=[RequestPattern.AnyRequest],
    ) as interceptor:
        asyncio.ensure_future(
            get_page_response(
                driver,
                wait_emit_page_processing,
                wait_result_page_processing,
                wait_pdf_download,
                wait_page_response,
                wait_processing_page_loaded,
            )
        )

        async for data in interceptor:
            if "jquery.filedownload" in data.request.url:
                await driver.execute_script(file_download_script)

            try:
                if data.stage == RequestStages.Response:
                    if emit_url in data.request.url:
                        body = await data.body
                        body_text = body.decode("utf-8", errors="ignore")
                        if (
                            "ERR_CONNECTION_RESET" not in body_text
                            and "Connection reset" not in body_text
                            and "This site can't be reached" not in body_text
                            and "Consulta em processamento" not in body_text
                        ):
                            wait_emit_page_processing.resolve()
                            if "O número informado não consta" in body_text:
                                await data.resume()
                                await driver.sleep(2)
                                await wait_for_element(driver, By.CSS_SELECTOR, "#rfb-main-container > div", "none")
                                break

                    if processing_url in data.request.url:
                        body = await data.body
                        body_text = body.decode("utf-8", errors="ignore")
                        if (
                            "ERR_CONNECTION_RESET" not in body_text
                            and "Connection reset" not in body_text
                            and "This site can't be reached" not in body_text
                            and "Consulta em processamento" not in body_text
                        ):
                            wait_processing_page_loaded.resolve()

                    if result_url in data.request.url:
                        body = await data.body
                        body_text = body.decode("utf-8", errors="ignore")
                        if (
                            "ERR_CONNECTION_RESET" not in body_text
                            and "Connection reset" not in body_text
                            and "This site can't be reached" not in body_text
                            and "Consulta em processamento" not in body_text
                            and "main-container" in body_text
                        ):
                            global result_html
                            wait_result_page_processing.resolve()
                            result_html = body_text

                if wait_pdf_download.is_resolved():
                    break

                if wait_result_page_processing.is_resolved():
                    break

                if wait_page_response.is_resolved():
                    break
            except Exception:
                pass

    result = await wait_page_response
    await driver.quit()
    return result


final_response = asyncio.run(main())
print(final_response)
