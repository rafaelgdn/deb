import { Logger, createPromise } from "../../../../utils/helpers";
import { errors } from "../../../../utils/errors";
import { configPageToStealth } from "../../../../utils/helpers/scraper";
import { imageCaptchaResolver } from "../../../../utils/helpers/captcha";
import waitForTimeout from "../../../../utils/helpers/waitForTimeout";

export const resolveImageCaptcha = async ({
  page,
  crawlerName,
  captchaDetails,
  proxy,
  helperInfo,
}) => {
  try {
    Logger.info("Started solving image captcha", helperInfo);

    await page.waitForSelector("input[id='ans'][name='answer']", { visible: true });

    const captchaResponse = await imageCaptchaResolver({
      page,
      selector: "img[alt='Red dot']",
      captchaDetails,
      proxy,
      crawlerName,
    }).catch((error) => {
      throw new errors.CaptchaError(error);
    });

    await page.type("input[id='ans'][name='answer']", captchaResponse.captchaResult);

    await page.evaluate(() => {
      document.querySelector("button[id='jar'][type='button']").click();
    });

    await page.waitForNavigation({ waitUntil: "networkidle2", timeout: 60000 }).catch((error) => {
      throw new errors.NavigationError(error);
    });

    return { captchaResponse };
  } catch (error) {
    Logger.error(error);
    throw error;
  }
};

const handlePageResponse = async ({ interceptedResponse, isCertificate, page, dialogAppears }) => {
  if (
    interceptedResponse?.includes(
      "Não foi possível concluir a ação para o contribuinte informado. Por favor, tente novamente dentro de alguns minutos."
    )
  ) {
    throw new errors.SourceUnavailableError(
      "Não foi possível concluir a ação para o contribuinte informado"
    );
  }

  if (
    interceptedResponse?.includes(
      "As informações disponíveis na Secretaria da Receita Federal do Brasil - RFB sobre o contribuinte"
    )
  ) {
    return {
      pageResponse: isCertificate ? "Certificate Not Generated" : "Not Suficient Informations",
    };
  }

  const pageResponse = await Promise.race([
    page.waitForSelector("#PRINCIPAL", { visible: true, timeout: 20000 }).then(() => {
      return Promise.resolve("Certificate Emitted");
    }),
    page.waitForSelector("a[href*='/Emitir/']", { visible: true, timeout: 20000 }).then(() => {
      return Promise.resolve("Request Certificate");
    }),
    page
      .waitForSelector("a[href^='EmiteCertidaoInternet']", { visible: true, timeout: 20000 })
      .then(() => {
        return Promise.resolve("Request Certificate");
      }),
    page
      .waitForFunction(`document.querySelector("*").textContent?.includes('inscrição suspensa')`, {
        timeout: 20000,
      })
      .then(() => {
        return Promise.resolve(isCertificate ? "Certificate Not Generated" : "Suspended");
      }),
    page
      .waitForFunction(
        `document.querySelector("*").textContent?.includes('inscrição pendente de regularização')`,
        {
          timeout: 20000,
        }
      )
      .then(() => {
        return Promise.resolve(isCertificate ? "Certificate Not Generated" : "Suspended");
      }),
    page
      .waitForFunction(
        `document.querySelector("*").textContent?.includes('são insuficientes para a emissão de certidão por meio da Internet')`,
        { timeout: 20000 }
      )
      .then(() => {
        return Promise.resolve(
          isCertificate ? "Certificate Not Generated" : "Not Suficient Informations"
        );
      }),
    page
      .waitForFunction(
        `document.querySelector("*").textContent?.includes('O número informado não consta do cadastro CPF')`,
        {
          timeout: 20000,
        }
      )
      .then(() => {
        return Promise.resolve(isCertificate ? "Certificate Not Generated" : "Not Found");
      }),
    page
      .waitForFunction(
        `document.querySelector("*").textContent?.includes('O número informado não consta do cadastro CNPJ')`,
        {
          timeout: 20000,
        }
      )
      .then(() => {
        return Promise.resolve(isCertificate ? "Certificate Not Generated" : "Not Found");
      }),
    page
      .waitForFunction(
        `document.querySelector("*").textContent?.includes('A certidão deve ser emitida para o CNPJ da matriz')`,
        {
          timeout: 20000,
        }
      )
      .then(() => {
        return Promise.resolve(isCertificate ? "Certificate Not Generated" : "Not Found");
      }),
    page
      .waitForFunction(
        `document.querySelector("*").textContent?.includes('Por favor, tente novamente dentro de alguns minutos.')`
      )
      .then(() => {
        throw new errors.TryAgainError();
      }),
    dialogAppears.then(() => {
      return Promise.resolve("Dialog");
    }),
    waitForTimeout(40000).then(() => "retry"),
  ]);

  return { pageResponse };
};

export const searchForCertificate = async ({
  browser,
  doc,
  helperInfo,
  isCertificate = false,
  infoType,
  proxyAuthentication,
  proxy,
  crawlerName,
  captchaDetails,
  errorCount = 0,
  page,
}) => {
  try {
    const rfBaseURL = `https://solucoes.receita.fazenda.gov.br/Servicos/certidaointernet/${infoType === "cnpj" ? "PJ" : "PF"
      }/Emitir`;

    if (!page) {
      page = await browser.newPage();

      if (proxyAuthentication) {
        await page.authenticate({
          username: proxyAuthentication.username,
          password: proxyAuthentication.password,
        });
      }
    }

    const dialogAppears = createPromise();

    page.on("dialog", async (dialog) => {
      dialogAppears.message = dialog.message();
      await dialog.dismiss();
      dialogAppears.resolve();
    });

    const waitResponse = createPromise();

    await page.on("response", async (response) => {
      try {
        const url = response.url();
        const baseURL = "https://solucoes.receita.fazenda.gov.br/Servicos/certidaointernet/";
        let responseText;

        if (
          response.status() === 200 &&
          (url.includes(
            `${baseURL}${infoType === "cnpj" ? "PJ" : "PF"}/Emitir/ResultadoEmissao/`
          ) ||
            url.includes(`${baseURL}${infoType === "cnpj" ? "PJ" : "PF"}/Emitir/Verificar`))
        ) {
          responseText = await response.text();

          if (!responseText.includes("Consulta em processamento")) {
            waitResponse.resolve(responseText.replace(/(\r\n|\n|\r)/gm, ""));
          }
        }
      } catch (error) {
        waitResponse.reject(error);
      }
    });

    const userAgent =
      "Mozilla/5.0 (X11; CrOS x86_64 8172.45.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.64 Safari/537.36";

    await configPageToStealth(page, userAgent);

    Logger.info("Going to URL", helperInfo);
    await page.goto(rfBaseURL, { waitUntil: "networkidle2", timeout: 80000 }).catch((error) => {
      throw new errors.PageAccessError(error);
    });

    page.setRequestInterception(true);

    page.on("request", async (req) => {
      const url = req.url();
      const isCaptchaScript = url.match(/\/TSPD\/.+type=5/);

      if (isCaptchaScript) {
        req.continue();
        await resolveImageCaptcha({ page, crawlerName, captchaDetails, proxy, helperInfo });
        return;
      }

      req.continue();
    });

    await page
      .waitForSelector("input[type='text'][name='NI']", { visible: true })
      .catch((error) => {
        throw new errors.NavigationError(error);
      });

    await page.click("input[type='text'][name='NI']");
    await page.type("input[type='text'][name='NI']", doc);
    await page.evaluate(() => document.querySelector("#validar").click());

    const interceptedResponse = await Promise.race([
      waitResponse.then((data) => data),
      waitForTimeout(20000),
    ]);

    const { pageResponse } = await handlePageResponse({
      interceptedResponse,
      isCertificate,
      page,
      dialogAppears,
    });

    // workaround to deal with page blocking
    // ###############################################################
    if (pageResponse === "retry") {
      errorCount += 1;

      if (errorCount >= 2) {
        throw new errors.SelectorNotLoadedError();
      }

      page.removeAllListeners("dialog");
      page.removeAllListeners("response");
      page.removeAllListeners("request");

      return searchForCertificate({
        doc,
        helperInfo,
        isCertificate,
        infoType,
        proxyAuthentication,
        proxy,
        crawlerName,
        captchaDetails,
        errorCount,
        page,
      });
    }
    // #######################################################

    page.removeAllListeners("dialog");
    page.removeAllListeners("response");

    Logger.info("Page response", { pageResponse });

    return Promise.resolve({ pageResponse, dialogMessage: dialogAppears.message, page });
  } catch (error) {
    return Promise.reject(error);
  }
};
