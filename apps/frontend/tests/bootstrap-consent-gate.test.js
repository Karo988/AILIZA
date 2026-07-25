// Hotfix: apps/frontend/index.html startete init() frueher nur, wenn
// localStorage["ailiza_consent"] === "1" war -- ein Schluessel, den KEINE
// Stelle im Code je gesetzt hat. Ergebnis: bei jedem frischen Browser
// (kein LocalStorage-Eintrag) blieb die App im statischen HTML-Ausgangs-
// zustand haengen ("○ Verbinde…"), Health-Check/Auth-Status/Chat-Laden
// fanden nie statt.
//
// Dieses Skript prueft end-to-end (echter Browser, echter lokaler Backend-
// Prozess) genau die im Hotfix-Auftrag geforderten Pflichtfaelle. Es nutzt
// die bereits in apps/frontend/package.json deklarierte "playwright"-
// Abhaengigkeit (kein neues Test-Tooling, keine CI-Aenderung).
//
// Nutzung:
//   1. Backend lokal starten, z.B.:
//      AILIZA_SECRET_KEY=<>=32 Zeichen> AILIZA_DATABASE_URL=sqlite:////tmp/x.db \
//      AILIZA_EXTERNAL_LLM_ENABLED=false python -m uvicorn apps.backend.main:app \
//      --host 127.0.0.1 --port 8812
//   2. cd apps/frontend && npm install (falls playwright/Browser noch fehlen)
//   3. node tests/bootstrap-consent-gate.test.js [BASE_URL]
//      (BASE_URL Default: http://127.0.0.1:8812)
//
// Exit-Code 0 = alle Pruefungen bestanden, != 0 = mindestens eine fehlgeschlagen.

const fs = require("fs");
const { chromium } = require("playwright");

const BASE_URL = process.argv[2] || "http://127.0.0.1:8812";
// Manche vorinstallierten Playwright-Umgebungen (z.B. dieses Sandbox-Image)
// stellen nur den regulaeren Chromium-Browser bereit, nicht den separaten
// "headless shell". PLAYWRIGHT_CHROMIUM_PATH erlaubt einen expliziten
// Override; Standardpfad wird nur verwendet, wenn er tatsaechlich existiert
// -- sonst laesst Playwright seine eigene Standardsuche laufen.
const SANDBOX_CHROMIUM_PATH = "/opt/pw-browsers/chromium";
const CHROMIUM_EXECUTABLE_PATH =
  process.env.PLAYWRIGHT_CHROMIUM_PATH || (fs.existsSync(SANDBOX_CHROMIUM_PATH) ? SANDBOX_CHROMIUM_PATH : undefined);

let passed = 0;
let failed = 0;

function check(name, condition, detail) {
  if (condition) {
    console.log(`PASS  ${name}`);
    passed++;
  } else {
    console.log(`FAIL  ${name}${detail ? " -- " + detail : ""}`);
    failed++;
  }
}

async function main() {
  const browser = await chromium.launch(
    CHROMIUM_EXECUTABLE_PATH ? { executablePath: CHROMIUM_EXECUTABLE_PATH } : {},
  );

  // 1. Frischer Browser ohne ailiza_consent: init() muss trotzdem laufen,
  //    Health-Check und Auth-Status muessen tatsaechlich gesendet werden,
  //    "Verbinde…" darf nicht dauerhaft stehen bleiben.
  {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    const seenRequests = [];
    const pageErrors = [];
    page.on("request", (req) => {
      if (req.url().endsWith("/health") || req.url().endsWith("/auth/me")) {
        seenRequests.push(req.url());
      }
    });
    page.on("pageerror", (err) => pageErrors.push(String(err)));

    await page.goto(BASE_URL + "/", { waitUntil: "load", timeout: 20000 });
    await page.waitForTimeout(2000);

    const consentKey = await page.evaluate(() => localStorage.getItem("ailiza_consent"));
    check("frischer Browser: kein ailiza_consent-Schluessel vorhanden (Vorbedingung)", consentKey === null, `war ${consentKey}`);

    check("frischer Browser: /health wurde tatsaechlich angefragt", seenRequests.some((u) => u.endsWith("/health")));
    check("frischer Browser: /auth/me wurde tatsaechlich angefragt", seenRequests.some((u) => u.endsWith("/auth/me")));
    check("frischer Browser: keine unbehandelten JS-Fehler", pageErrors.length === 0, pageErrors.join("; "));

    const connText = await page.$eval("#conn-status", (el) => el.textContent);
    check(
      "frischer Browser: Verbindungsstatus zeigt NICHT dauerhaft 'Verbinde…' (Health-Check erreichbar -> 'System aktiv')",
      connText.includes("System aktiv"),
      `war "${connText}"`,
    );

    const authBtn = await page.$eval("#topbar-auth-btn", (el) => el.textContent);
    check("frischer Browser: Login-Button geladen (Oberflaeche initialisiert)", authBtn.trim() === "Anmelden", `war "${authBtn}"`);

    await ctx.close();
  }

  // 2. Bestehender Browser MIT ailiza_consent="1" (alter Zustand): muss
  //    weiterhin normal funktionieren (keine Regression fuer Alt-Browser).
  {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.addInitScript(() => localStorage.setItem("ailiza_consent", "1"));
    await page.goto(BASE_URL + "/", { waitUntil: "load", timeout: 20000 });
    await page.waitForTimeout(1500);
    const connText = await page.$eval("#conn-status", (el) => el.textContent);
    check("Browser mit ailiza_consent=1: Verbindungsstatus aktiv", connText.includes("System aktiv"), `war "${connText}"`);
    await ctx.close();
  }

  // 3. Browser mit ailiza_pii_consent (ANDERER Schluessel, Datenschutz-
  //    Bestaetigung fuer Chat-PII): darf NICHT mit dem Bootstrap-Gate
  //    verwechselt werden und muss unangetastet erhalten bleiben.
  {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.addInitScript(() => {
      localStorage.setItem("ailiza_pii_consent", "1");
      localStorage.setItem("ailiza_pii_consent_ts", new Date().toISOString());
    });
    await page.goto(BASE_URL + "/", { waitUntil: "load", timeout: 20000 });
    await page.waitForTimeout(1500);
    const connText = await page.$eval("#conn-status", (el) => el.textContent);
    check(
      "Browser mit ailiza_pii_consent: App startet trotzdem normal (unabhaengig vom Bootstrap)",
      connText.includes("System aktiv"),
      `war "${connText}"`,
    );
    const piiStillSet = await page.evaluate(() => localStorage.getItem("ailiza_pii_consent"));
    check("ailiza_pii_consent bleibt unveraendert erhalten (nicht geloescht/umbenannt)", piiStillSet === "1", `war ${piiStillSet}`);
    await ctx.close();
  }

  // 4. Nicht erreichbares Backend: verstaendlicher Offline-Status statt
  //    dauerhaftem "Verbinde…".
  {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.route("**/health", (route) => route.abort("failed"));
    await page.goto(BASE_URL + "/", { waitUntil: "load", timeout: 20000 });
    await page.waitForTimeout(2000);
    const connText = await page.$eval("#conn-status", (el) => el.textContent);
    check(
      "Backend nicht erreichbar: verstaendlicher Offline-Status (nicht 'Verbinde…')",
      connText.includes("Offline") || connText.includes("verzögert"),
      `war "${connText}"`,
    );
    await ctx.close();
  }

  // 5. Normaler Login/Registrierung funktioniert weiterhin end-to-end,
  //    inkl. Session nach Reload (Bootstrap-Fix darf bestehende Auth-Logik
  //    nicht veraendern).
  {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto(BASE_URL + "/", { waitUntil: "load", timeout: 20000 });
    await page.waitForTimeout(800);
    await page.click("#topbar-auth-btn");
    await page.waitForTimeout(300);
    const uniqueUser = "e2e_hotfix_" + Date.now();
    await page.fill("#login-user", uniqueUser);
    await page.fill("#login-pass", "Sehr$icher123Pass");
    await page.click('button:has-text("Registrieren")');
    await page.waitForTimeout(1500);
    const authBtnAfterRegister = await page.$eval("#topbar-auth-btn", (el) => el.textContent);
    check(
      "Registrierung + Auto-Login funktioniert weiterhin",
      authBtnAfterRegister.includes(uniqueUser),
      `war "${authBtnAfterRegister}"`,
    );

    await page.reload({ waitUntil: "load" });
    await page.waitForTimeout(1500);
    const authBtnAfterReload = await page.$eval("#topbar-auth-btn", (el) => el.textContent);
    const connAfterReload = await page.$eval("#conn-status", (el) => el.textContent);
    check("Session bleibt nach Reload erhalten (Login-Status)", authBtnAfterReload.includes(uniqueUser), `war "${authBtnAfterReload}"`);
    check("Verbindungsstatus nach Reload weiterhin aktiv", connAfterReload.includes("System aktiv"), `war "${connAfterReload}"`);
    await ctx.close();
  }

  // 6. PII-Vorschau-/Schwaerzungs-DOM unveraendert vorhanden (dieser Hotfix
  //    fasst diese Logik nicht an -- reiner Existenz-/Regressions-Check).
  {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto(BASE_URL + "/", { waitUntil: "load", timeout: 20000 });
    await page.waitForTimeout(800);
    const piiBarExists = await page.$("#pii-consent");
    check("PII-Datenschutz-Hinweis-Element weiterhin im DOM vorhanden (nicht entfernt)", piiBarExists !== null);
    await ctx.close();
  }

  await browser.close();

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error("Testlauf abgebrochen:", err);
  process.exit(1);
});
