// PR A: Login-UX entkoppeln, Registrierungs-UX verbessern.
//
// Vorher: EIN Modal mit "Registrieren"/"Anmelden" nebeneinander, dieselben
// Eingabefelder, die Registrierungs-Passwortregel war IMMER sichtbar --
// Hauptquelle der gemeldeten Verwechslung (Passwort-Policy-Meldung wirkte
// wie ein Login-Fehler, obwohl LoginRequest gar keinen Policy-Validator hat).
//
// Dieses Skript prueft end-to-end (echter Browser, echter lokaler Backend-
// Prozess) die im PR-A-Auftrag geforderten Pflichtfaelle. Nutzt dieselbe
// bereits in apps/frontend/package.json deklarierte "playwright"-
// Abhaengigkeit wie apps/frontend/tests/bootstrap-consent-gate.test.js.
//
// Nutzung:
//   1. Backend lokal starten (siehe bootstrap-consent-gate.test.js).
//   2. node tests/login-registration-ux.test.js [BASE_URL]
//
// Exit-Code 0 = alle Pruefungen bestanden, != 0 = mindestens eine fehlgeschlagen.

const fs = require("fs");
const { chromium } = require("playwright");

const BASE_URL = process.argv[2] || "http://127.0.0.1:8813";
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

async function newPage(browser) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(BASE_URL + "/", { waitUntil: "load", timeout: 20000 });
  await page.waitForTimeout(500);
  return { ctx, page };
}

async function main() {
  const browser = await chromium.launch(
    CHROMIUM_EXECUTABLE_PATH ? { executablePath: CHROMIUM_EXECUTABLE_PATH } : {},
  );

  // 1. Login-Ansicht enthaelt KEINE Passwort-Policy, keine Passwortwiederholung.
  {
    const { ctx, page } = await newPage(browser);
    await page.click("#topbar-auth-btn");
    await page.waitForTimeout(200);
    const title = await page.$eval("#auth-modal-title", (el) => el.textContent);
    const policyVisible = await page.$eval("#auth-password-policy-hint", (el) => getComputedStyle(el).display !== "none");
    const confirmVisible = await page.$eval("#auth-password-confirm-field", (el) => getComputedStyle(el).display !== "none");
    check("Login-Ansicht zeigt Titel 'Anmelden'", title.trim() === "Anmelden", `war "${title}"`);
    check("Login-Ansicht zeigt KEINE Passwort-Policy", !policyVisible);
    check("Login-Ansicht zeigt KEINE Passwortwiederholung", !confirmVisible);
    await ctx.close();
  }

  // 2. Wechsel zu "Konto erstellen": Titel, Policy, Passwortwiederholung sichtbar.
  {
    const { ctx, page } = await newPage(browser);
    await page.click("#topbar-auth-btn");
    await page.waitForTimeout(200);
    await page.click('#auth-mode-switch a');
    await page.waitForTimeout(200);
    const title = await page.$eval("#auth-modal-title", (el) => el.textContent);
    const policyVisible = await page.$eval("#auth-password-policy-hint", (el) => getComputedStyle(el).display !== "none");
    const confirmVisible = await page.$eval("#auth-password-confirm-field", (el) => getComputedStyle(el).display !== "none");
    const primaryLabel = await page.$eval("#auth-primary-btn", (el) => el.textContent);
    check("Registrierungs-Ansicht zeigt Titel 'Konto erstellen'", title.trim() === "Konto erstellen", `war "${title}"`);
    check("Registrierungs-Ansicht zeigt Passwort-Policy", policyVisible);
    check("Registrierungs-Ansicht zeigt Passwortwiederholung", confirmVisible);
    check("Primaerbutton heisst 'Konto erstellen'", primaryLabel.trim() === "Konto erstellen", `war "${primaryLabel}"`);

    // Wechsel zurueck zum Login
    await page.click('#auth-mode-switch a');
    await page.waitForTimeout(200);
    const titleBack = await page.$eval("#auth-modal-title", (el) => el.textContent);
    const policyVisibleBack = await page.$eval("#auth-password-policy-hint", (el) => getComputedStyle(el).display !== "none");
    check("Wechsel zurueck zu 'Anmelden' funktioniert", titleBack.trim() === "Anmelden", `war "${titleBack}"`);
    check("Passwort-Policy nach Rueckwechsel wieder verborgen", !policyVisibleBack);
    await ctx.close();
  }

  // 3. Passwortwiederholung wird geprueft (client-seitig, kein Request bei Mismatch).
  {
    const { ctx, page } = await newPage(browser);
    const registerCalls = [];
    await page.route("**/auth/self-register", (route) => {
      registerCalls.push(route.request().url());
      route.continue();
    });
    await page.click("#topbar-auth-btn");
    await page.click('#auth-mode-switch a');
    await page.waitForTimeout(200);
    await page.fill("#login-user", "MismatchUser1");
    await page.fill("#login-pass", "ValidPass123!");
    await page.fill("#register-pass-confirm", "AndereValidPass123!");
    await page.click("#auth-primary-btn");
    await page.waitForTimeout(500);
    const errText = await page.$eval("#login-error", (el) => el.textContent);
    check(
      "Passwort-Mismatch wird clientseitig erkannt (keine Netzwerkanfrage)",
      registerCalls.length === 0 && errText.includes("nicht überein"),
      `requests=${registerCalls.length} err="${errText}"`,
    );
    await ctx.close();
  }

  // 4. Unbekannter Nutzer und falsches Passwort zeigen DIESELBE neutrale Meldung.
  {
    const { ctx, page } = await newPage(browser);
    // Vorher ein echtes Konto anlegen, um "falsches Passwort" testen zu koennen.
    await page.click("#topbar-auth-btn");
    await page.click('#auth-mode-switch a');
    await page.waitForTimeout(200);
    const realUser = "RealUser" + Date.now();
    await page.fill("#login-user", realUser);
    await page.fill("#login-pass", "ValidPass123!");
    await page.fill("#register-pass-confirm", "ValidPass123!");
    await page.click("#auth-primary-btn");
    await page.waitForTimeout(800);
    // ausloggen fuer den naechsten Testschritt
    await page.evaluate(() => window.doLogout && window.doLogout());
    await page.waitForTimeout(500);

    await page.click("#topbar-auth-btn");
    await page.waitForTimeout(200);
    await page.fill("#login-user", "UnbekannterNutzer" + Date.now());
    await page.fill("#login-pass", "IrgendeinPasswort1!");
    await page.click("#auth-primary-btn");
    await page.waitForTimeout(600);
    const unknownUserMsg = await page.$eval("#login-error", (el) => el.textContent);

    await page.fill("#login-user", realUser);
    await page.fill("#login-pass", "FalschesPasswort1!");
    await page.click("#auth-primary-btn");
    await page.waitForTimeout(600);
    const wrongPasswordMsg = await page.$eval("#login-error", (el) => el.textContent);

    check(
      "Unbekannter Nutzer und falsches Passwort zeigen dieselbe neutrale Meldung",
      unknownUserMsg === wrongPasswordMsg && unknownUserMsg.length > 0,
      `unbekannt="${unknownUserMsg}" falsch="${wrongPasswordMsg}"`,
    );
    await ctx.close();
  }

  // 5. Registrierungserfolg wird sichtbar bestaetigt + Login/Chat funktionieren danach.
  {
    const { ctx, page } = await newPage(browser);
    await page.click("#topbar-auth-btn");
    await page.click('#auth-mode-switch a');
    await page.waitForTimeout(200);
    const newUser = "ConfirmUser" + Date.now();
    await page.fill("#login-user", newUser);
    await page.fill("#login-pass", "ValidPass123!");
    await page.fill("#register-pass-confirm", "ValidPass123!");
    await page.click("#auth-primary-btn");
    await page.waitForTimeout(1000);
    const authBtn = await page.$eval("#topbar-auth-btn", (el) => el.textContent);
    const chatText = await page.evaluate(() => document.getElementById("chat-inner")?.textContent || "");
    check(
      "Registrierungserfolg sichtbar bestaetigt (Konto erstellt + angemeldet)",
      chatText.includes("Konto wurde erstellt"),
      `chat enthaelt: ${chatText.slice(-200)}`,
    );
    check("Login-Status nach Registrierung sichtbar", authBtn.includes(newUser), `war "${authBtn}"`);
    await ctx.close();
  }

  // 6. Nutzername mit aeusseren Leerzeichen wird getrimmt (Konto ohne Leerzeichen anlegbar/nutzbar).
  {
    const { ctx, page } = await newPage(browser);
    await page.click("#topbar-auth-btn");
    await page.click('#auth-mode-switch a');
    await page.waitForTimeout(200);
    const trimUser = "TrimUser" + Date.now();
    await page.fill("#login-user", "   " + trimUser + "   ");
    await page.fill("#login-pass", "ValidPass123!");
    await page.fill("#register-pass-confirm", "ValidPass123!");
    await page.click("#auth-primary-btn");
    await page.waitForTimeout(1000);
    const authBtn = await page.$eval("#topbar-auth-btn", (el) => el.textContent);
    check(
      "Aeussere Leerzeichen im Nutzernamen werden getrimmt",
      authBtn.includes(trimUser) && !authBtn.includes("   " + trimUser),
      `war "${authBtn}"`,
    );
    await ctx.close();
  }

  // 7. Nutzername mit INNEREM Leerzeichen bleibt unveraendert (kein stilles Entfernen).
  {
    const { ctx, page } = await newPage(browser);
    await page.click("#topbar-auth-btn");
    await page.click('#auth-mode-switch a');
    await page.waitForTimeout(200);
    const innerSpaceUser = "Inner Space" + Date.now();
    await page.fill("#login-user", innerSpaceUser);
    await page.fill("#login-pass", "ValidPass123!");
    await page.fill("#register-pass-confirm", "ValidPass123!");
    await page.click("#auth-primary-btn");
    await page.waitForTimeout(1000);
    const authBtn = await page.$eval("#topbar-auth-btn", (el) => el.textContent);
    check(
      "Inneres Leerzeichen im Nutzernamen bleibt unveraendert",
      authBtn.includes(innerSpaceUser),
      `war "${authBtn}"`,
    );
    await ctx.close();
  }

  // 8. Login + Chat funktionieren nach erfolgreicher Anmeldung (Regressionscheck).
  {
    const { ctx, page } = await newPage(browser);
    await page.click("#topbar-auth-btn");
    await page.click('#auth-mode-switch a');
    await page.waitForTimeout(200);
    const chatUser = "ChatUser" + Date.now();
    await page.fill("#login-user", chatUser);
    await page.fill("#login-pass", "ValidPass123!");
    await page.fill("#register-pass-confirm", "ValidPass123!");
    await page.click("#auth-primary-btn");
    await page.waitForTimeout(1000);
    await page.reload({ waitUntil: "load" });
    await page.waitForTimeout(1200);
    const authBtn = await page.$eval("#topbar-auth-btn", (el) => el.textContent);
    const connStatus = await page.$eval("#conn-status", (el) => el.textContent);
    check("Session bleibt nach Reload erhalten", authBtn.includes(chatUser), `war "${authBtn}"`);
    check("Verbindungsstatus nach Reload aktiv (Bootstrap-Hotfix PR #62 weiterhin wirksam)", connStatus.includes("System aktiv"), `war "${connStatus}"`);
    await ctx.close();
  }

  // 9. Bestehender PII-Hinweis bleibt unveraendert im DOM.
  {
    const { ctx, page } = await newPage(browser);
    const piiBarExists = await page.$("#pii-consent");
    check("PII-Datenschutz-Hinweis-Element weiterhin im DOM vorhanden", piiBarExists !== null);
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
