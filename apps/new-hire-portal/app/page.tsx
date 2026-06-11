import { headers } from "next/headers";
import PortalShell from "./portal-shell";

function getDisplayName(email: string | null, fullName: string | null) {
  if (fullName) {
    return fullName;
  }

  if (!email) {
    return "neues Teammitglied";
  }

  return email.split("@")[0]?.replace(/[._-]+/g, " ") ?? email;
}

export default async function Home() {
  const requestHeaders = await headers();
  const email = requestHeaders.get("oai-authenticated-user-email");
  const encodedFullName = requestHeaders.get("oai-authenticated-user-full-name");
  const fullName =
    encodedFullName &&
    requestHeaders.get("oai-authenticated-user-full-name-encoding") ===
      "percent-encoded-utf-8"
      ? decodeURIComponent(encodedFullName)
      : null;

  return <PortalShell displayName={getDisplayName(email, fullName)} />;
}
