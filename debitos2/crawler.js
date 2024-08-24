/* eslint-disable consistent-return */
import { Logger, createPromise } from "../../../../utils/helpers";
import { errors } from "../../../../utils/errors";
import { searchForCertificate } from "../../../cpfchecker/nacional/debitos/helper";

import {
  getEvidence,
  launchBrowserStealth,
  setPDFDownloadBehavior,
  getPDFEvidenceLink,
  // configPageToStealth,
  // launchBrowser
} from "../../../../utils/helpers/scraper";
import waitForTimeout from "../../../../utils/helpers/waitForTimeout";
// import { sleep } from "../../../../utils/helpers/shared";

const helperInfo = {
  state: "NACIONAL",
  institution: "DEB",
};

const consultIssuedCertificate = async ({ page }) => {
  await page.waitForSelector("#PeriodoInicio");
  await page.evaluate(() => document.querySelector("#validar").click());

  await page.waitForSelector("#resultado tbody tr:first-child a.fileDownloadAlerta");

  const downloadLink = await page.$eval(
    "#resultado tbody tr:first-child a.fileDownloadAlerta",
    (el) => el.getAttribute("href")
  );

  await page
    .goto(`https://solucoes.receita.fazenda.gov.br${downloadLink}`, {
      waitUntil: "networkidle2",
      timeout: 60000,
    })
    .catch((error) => {
      // due to puppeteer bug on go to in pages that are pdfs erro ERR_ABORTED is excpected (https://github.com/puppeteer/puppeteer/issues/2794)
      if (!error.message.includes("net::ERR_ABORTED"))
        throw new errors.PageAccessError(
          `Error trying to access the download certificate URL. Error: ${error}`
        );
    });
};

const redoAllSearch = async ({ page, infoType, doc, pdfPromise }) => {
  const rfBaseURL = `https://solucoes.receita.fazenda.gov.br/Servicos/certidaointernet/${infoType === "cnpj" ? "PJ" : "PF"
    }/Emitir`;

  await page.goto(rfBaseURL, { waitUntil: "networkidle2", timeout: 80000 }).catch((error) => {
    throw new errors.PageAccessError(error);
  });

  await page.waitForSelector("input[type='text'][name='NI']", { visible: true }).catch((error) => {
    throw new errors.NavigationError(error);
  });

  await page.click("input[type='text'][name='NI']");
  await page.type("input[type='text'][name='NI']", doc);
  await page.evaluate(() => document.querySelector("#validar").click());

  const isCertificateDownloaded = await Promise.race([
    pdfPromise.then(() => {
      return true;
    }),
    page.waitForSelector("#FrmSelecao a[href*='TipoPesquisa=1']").then(() => {
      return false;
    }),
  ]);

  if (isCertificateDownloaded) return { isCertificateDownloaded: true };

  await page.evaluate(() =>
    document.querySelector("#FrmSelecao a[href*='TipoPesquisa=1']").click()
  );

  await consultIssuedCertificate({ page });

  return { isCertificateDownloaded: false };
};

const crawl = async ({
  crawlInfo,
  proxy,
  crawlerName,
  captchaDetails,
  folderName,
  proxyAuthentication,
}) => {
  const doc = crawlInfo.cnpj || crawlInfo.cpf;
  let browser;
  Logger.info("Started crawling", { helperInfo, doc });
  try {
    const specificArgs = [
      "--start-maximized",
      "--window-size=1024,768",
      "--disable-web-security",
      "--ignore-certificate-errors",
      "--no-sandbox",
      "--disable-setuid-sandbox",
    ];

    // browser = await launchBrowser({ ignoreHTTPSErrors: true, specificArgs });
    browser = await launchBrowserStealth({ proxy, ignoreHTTPSErrors: true, specificArgs });

    // const page = await browser.newPage();

    // const userAgent =
    //   "Mozilla/5.0 (X11; CrOS x86_64 8172.45.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.64 Safari/537.36";

    // await configPageToStealth(page, userAgent);

    // await page.goto("https://bot.sannysoft.com/")

    // await sleep(99999999)



    const { pageResponse, dialogMessage, page } = await searchForCertificate({
      doc,
      proxy,
      crawlerName,
      captchaDetails,
      helperInfo,
      isCertificate: true,
      infoType: Object.keys(crawlInfo)[0],
      browser,
      proxyAuthentication,
    });

    const uniqueFolder = await setPDFDownloadBehavior(page);
    const pdfPromise = createPromise();

    page.on("response", async (res) => {
      const isGetMethod = res.request().method() === "GET";
      const headers = res.headers();

      if (isGetMethod && headers["content-type"]?.includes("pdf")) {
        pdfPromise.resolve();
      }
    });

    Logger.info("Response.", { pageResponse, dialogMessage, helperInfo });

    let result;
    let status;
    let evidenceLink;
    switch (pageResponse) {
      case "Certificate Emitted":
        status = "certificateGenerated";
        result = {
          type: "Certidão emitida",
          link: page.url(),
          certificateGenerated: true,
          certificateProcessed: true,
        };
        break;

      case "Request Certificate":
        await page.waitForSelector("#FrmSelecao a[href*='TipoPesquisa=1']");

        const issuedCertificatesUrl = await page.$eval(
          "#FrmSelecao a[href*='TipoPesquisa=1']",
          (el) => el.getAttribute("href")
        );

        await page.evaluate(() => document.querySelector("a[href*='/Emitir/']").click());

        // workaround to deal with page blocking
        // ###############################################################
        const response = await page
          .waitForSelector("#rfb-main-container > div > div > a", { timeout: 20000 })
          .catch(async () => {
            try {
              await page.goto(`https://solucoes.receita.fazenda.gov.br${issuedCertificatesUrl}`, {
                waitUntil: "networkidle2",
                timeout: 10000,
              });

              await consultIssuedCertificate({ page });
            } catch (error) {
              return redoAllSearch({
                page,
                infoType: Object.keys(crawlInfo)[0],
                doc,
                pdfPromise,
              });
            }
          });

        if (response?.isCertificateDownloaded) {
          status = "certificateGenerated";
          result = {
            type: "Certidão emitida",
            link: page.url(),
            certificateGenerated: true,
            certificateProcessed: true,
          };
          break;
        }
        // ###############################################################

        const certificateGenerated = await Promise.race([
          pdfPromise.then(() => {
            return true;
          }),
          page
            .waitForFunction(
              `document.querySelector("*").textContent?.includes("são insuficientes para a emissão de certidão por meio da Internet.")`
            )
            .then(() => {
              return false;
            }),
          page
            .waitForFunction(
              `document.querySelector("*").textContent?.includes('Por favor, tente novamente dentro de alguns minutos.')`
            )
            .then(() => {
              throw new errors.TryAgainError();
            }),
        ]);

        if (!certificateGenerated) {
          status = "certificateNotGenerated";
          result = {
            type: "Certidão não emitida",
            link: page.url(),
            certificateGenerated: false,
            certificateProcessed: true,
          };
          break;
        }

        status = "certificateGenerated";
        result = {
          type: "Certidão emitida",
          link: page.url(),
          certificateGenerated: true,
          certificateProcessed: true,
        };
        break;

      case "Certificate Not Generated":
        status = "certificateNotGenerated";
        result = {
          type: "Certidão não emitida",
          link: page.url(),
          certificateGenerated: false,
          certificateProcessed: true,
        };
        break;

      case "Dialog":
        Logger.info("An error dialog appeared", { dialogMessage, helperInfo });
        if (dialogMessage?.includes("Digite corretamente os caracteres da imagem."))
          throw new errors.BadCaptchaError();

        throw new errors.UnexpectedError(dialogMessage);

      default:
        throw new errors.UnexpectedError("Caso não mapeado");
    }

    if (status === "certificateGenerated")
      evidenceLink = await getPDFEvidenceLink({
        localFolder: uniqueFolder,
        bucketFolder: folderName,
        fileName: "certificateGenerated",
      }).catch((error) => {
        throw new errors.GetEvidenceError(error);
      });
    else await waitForTimeout(1000);
    evidenceLink = await getEvidence(page, folderName, status).catch((error) => {
      throw new errors.GetEvidenceError(error);
    });

    result.evidenceLink = evidenceLink;
    page.removeAllListeners("response");
    await browser.close();

    return Promise.resolve({
      result,
    });
  } catch (error) {
    if (browser) await browser.close();
    return Promise.reject(error);
  }
};

export default crawl;
