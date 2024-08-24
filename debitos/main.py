from utils import move_mouse_around_element, type_with_delay, wait_for_element, race
from utils.intercept_request import intercept_request
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


async def main(driver, pdf_exposed_promise):
    await driver.get(url, wait_load=True)
    await driver.sleep(0.5)

    input_element = await driver.find_element(By.CSS_SELECTOR, "#NI")

    await move_mouse_around_element(driver, input_element)
    await type_with_delay(driver, input_element, doc)

    submit_element = await driver.find_element(By.CSS_SELECTOR, "#validar")

    await move_mouse_around_element(driver, submit_element)
    await submit_element.click()
    await driver.sleep(10)

    element = await race(
        wait_for_element(driver, By.CSS_SELECTOR, "a[href*='Emitir/EmProcessamento']"),
        wait_for_element(driver, By.CSS_SELECTOR, "input[type='button'][value='Nova consulta']"),
    )

    if element.tag_name == "a":
        await element.click()
        element = await wait_for_element(driver, By.CSS_SELECTOR, "input[type='button'][value='Nova consulta']")

    print(element.text)

    await driver.sleep(999999)


asyncio.run(intercept_request(main))
