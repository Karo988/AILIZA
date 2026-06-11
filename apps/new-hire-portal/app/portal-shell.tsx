"use client";

import Image from "next/image";
import { useEffect, useMemo, useState } from "react";

type TrackId = "governance" | "engineering" | "operations" | "people";
type DayId = "tag1" | "tag2" | "tag3" | "tag4";
type CompletionState = Record<string, boolean>;

const STORAGE_KEY = "ailiza-new-hire-progress-v1";

const tracks: Array<{
  id: TrackId;
  label: string;
  eyebrow: string;
  focus: string;
  owner: string;
  firstArtifact: string;
}> = [
  {
    id: "governance",
    label: "Governance",
    eyebrow: "Policy & Oversight",
    focus: "EU-AI-Act-Kontrollen, Audit-Spuren und Human-in-the-loop-Freigaben verstehen.",
    owner: "Policy Lead",
    firstArtifact: "Policy-Matrix für den ersten Agentenlauf prüfen",
  },
  {
    id: "engineering",
    label: "Engineering",
    eyebrow: "Runtime & APIs",
    focus: "Agent Runtime, Approval Gateway und Tool-Ausführung lokal nachvollziehen.",
    owner: "Runtime Lead",
    firstArtifact: "Einen kontrollierten Agentenlauf im Dev-Setup starten",
  },
  {
    id: "operations",
    label: "Operations",
    eyebrow: "Delivery & Trust",
    focus: "Freigabewege, Incident-Rollen und Audit-Review-Routinen einordnen.",
    owner: "Ops Partner",
    firstArtifact: "Onboarding-Freigaben und Bereitschaften bestätigen",
  },
  {
    id: "people",
    label: "People",
    eyebrow: "Team & Enablement",
    focus: "Arbeitsrhythmus, Feedbackpunkte und Lernpfade für die ersten 30 Tage planen.",
    owner: "People Partner",
    firstArtifact: "30-Tage-Check-in mit Mentor und Manager terminieren",
  },
];

const checklist = [
  {
    id: "accounts",
    phase: "Heute",
    title: "Zugriffspaket bestätigen",
    detail: "Workspace, Repository, Audit-Dashboard und Approval Queue prüfen.",
    owner: "People Ops",
  },
  {
    id: "policy-read",
    phase: "Heute",
    title: "Governance Primer lesen",
    detail: "Grundprinzipien: Controlled Autonomy, Human Oversight, Privacy by Design.",
    owner: "Policy",
  },
  {
    id: "mentor",
    phase: "Heute",
    title: "Mentor-Slot buchen",
    detail: "Erster 1:1-Termin, Kommunikationswege und Erwartungsrahmen klären.",
    owner: "Manager",
  },
  {
    id: "runtime-tour",
    phase: "Woche 1",
    title: "Agent Runtime Rundgang",
    detail: "Vom Task bis zur Tool-Ausführung inklusive Risikoentscheidung.",
    owner: "Engineering",
  },
  {
    id: "approval-drill",
    phase: "Woche 1",
    title: "Approval Drill absolvieren",
    detail: "Eine riskante Aktion stoppen, begründen, freigeben oder ablehnen.",
    owner: "Governance",
  },
  {
    id: "first-commit",
    phase: "Woche 1",
    title: "Ersten Beitrag liefern",
    detail: "Kleine Verbesserung an Docs, Tests oder Portal-Inhalten reviewen lassen.",
    owner: "Team",
  },
];

const schedule: Record<
  DayId,
  Array<{ time: string; title: string; room: string; outcome: string }>
> = {
  tag1: [
    {
      time: "09:30",
      title: "Willkommen & Setup",
      room: "People Desk",
      outcome: "Arbeitsgerät, Zugriff und Ansprechpartner stehen.",
    },
    {
      time: "11:00",
      title: "AILIZA Architektur",
      room: "Runtime Lab",
      outcome: "Systemgrenzen und Kontrollpunkte sind sichtbar.",
    },
    {
      time: "15:00",
      title: "Policy Walkthrough",
      room: "Governance Room",
      outcome: "Freigaben, Risiken und Audit-Ereignisse sind eingeordnet.",
    },
  ],
  tag2: [
    {
      time: "10:00",
      title: "Tool Gateway Deep Dive",
      room: "Runtime Lab",
      outcome: "Du kennst die Guardrails vor jeder Tool-Ausführung.",
    },
    {
      time: "13:30",
      title: "Shadowing: Approval Queue",
      room: "Operations",
      outcome: "Du siehst reale Entscheidungen ohne Produktionsrisiko.",
    },
  ],
  tag3: [
    {
      time: "09:45",
      title: "Privacy-by-Design Review",
      room: "Policy",
      outcome: "Datenminimierung und Logging-Grenzen sind klar.",
    },
    {
      time: "14:00",
      title: "Team Rituals",
      room: "Main Standup",
      outcome: "Arbeitsrhythmus, Review-Kultur und Eskalationswege sitzen.",
    },
  ],
  tag4: [
    {
      time: "10:30",
      title: "Erster kontrollierter Agentenlauf",
      room: "Runtime Lab",
      outcome: "Du startest, stoppst und dokumentierst einen Lauf.",
    },
    {
      time: "16:00",
      title: "30-Tage-Plan",
      room: "Mentor 1:1",
      outcome: "Nächste Meilensteine und Lernfelder sind vereinbart.",
    },
  ],
};

const resources = [
  {
    title: "Governance Handbook",
    label: "Policy",
    href: "#governance",
    description: "Prinzipien, Rollen und Entscheidungswege für kontrollierte Autonomie.",
  },
  {
    title: "Runtime Map",
    label: "Engineering",
    href: "#first-week",
    description: "Agent Runtime, Gateway, Tool Execution und Audit Store in einem Ablauf.",
  },
  {
    title: "Approval Queue",
    label: "Oversight",
    href: "#checklist",
    description: "Wo riskante Aktionen landen und wie Freigaben dokumentiert werden.",
  },
  {
    title: "People Guide",
    label: "Team",
    href: "#contacts",
    description: "Kontakte, Rituale und Feedbackpunkte für die ersten Wochen.",
  },
];

const dayTabs: Array<{ id: DayId; label: string }> = [
  { id: "tag1", label: "Tag 1" },
  { id: "tag2", label: "Tag 2" },
  { id: "tag3", label: "Tag 3" },
  { id: "tag4", label: "Tag 4" },
];

function readSavedCompletion(): CompletionState {
  if (typeof window === "undefined") {
    return {};
  }

  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return saved ? (JSON.parse(saved) as CompletionState) : {};
  } catch {
    return {};
  }
}

export default function PortalShell({ displayName }: { displayName: string }) {
  const [selectedTrack, setSelectedTrack] = useState<TrackId>("governance");
  const [selectedDay, setSelectedDay] = useState<DayId>("tag1");
  const [completed, setCompleted] = useState<CompletionState>(readSavedCompletion);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(completed));
  }, [completed]);

  const selectedTrackData = tracks.find((track) => track.id === selectedTrack) ?? tracks[0];
  const completedCount = checklist.filter((item) => completed[item.id]).length;
  const progress = Math.round((completedCount / checklist.length) * 100);
  const currentSchedule = schedule[selectedDay];

  const byPhase = useMemo(() => {
    return checklist.reduce<Record<string, typeof checklist>>((groups, item) => {
      groups[item.phase] = [...(groups[item.phase] ?? []), item];
      return groups;
    }, {});
  }, []);

  function toggleItem(id: string) {
    setCompleted((current) => ({ ...current, [id]: !current[id] }));
  }

  function completeToday() {
    setCompleted((current) => ({
      ...current,
      ...Object.fromEntries(
        checklist.filter((item) => item.phase === "Heute").map((item) => [item.id, true]),
      ),
    }));
  }

  return (
    <main className="min-h-screen bg-[#f6f3ed] text-[#1f2424]">
      <section className="relative overflow-hidden bg-[#101514] text-white">
        <Image
          src="/onboarding-hero.png"
          alt="Moderner Onboarding-Arbeitsplatz mit Governance-Dashboard"
          fill
          priority
          sizes="100vw"
          className="object-cover"
          unoptimized
        />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(13,18,17,0.95)_0%,rgba(13,18,17,0.78)_38%,rgba(13,18,17,0.18)_72%,rgba(13,18,17,0.08)_100%)]" />
        <div className="relative mx-auto flex min-h-[540px] max-w-7xl flex-col px-5 py-6 sm:px-8 lg:px-10">
          <header className="flex items-center justify-between gap-4">
            <a href="#top" className="flex items-center gap-3">
              <span className="grid h-9 w-9 place-items-center rounded-md border border-white/35 bg-white/10 text-sm font-bold">
                AI
              </span>
              <span>
                <span className="block text-sm font-semibold uppercase tracking-[0.18em]">
                  AILIZA
                </span>
                <span className="block text-xs text-white/70">New-Hire-Portal</span>
              </span>
            </a>
            <nav className="hidden items-center gap-2 text-sm text-white/78 md:flex">
              <a className="rounded-md px-3 py-2 hover:bg-white/12" href="#checklist">
                Checkliste
              </a>
              <a className="rounded-md px-3 py-2 hover:bg-white/12" href="#first-week">
                Woche 1
              </a>
              <a className="rounded-md px-3 py-2 hover:bg-white/12" href="#resources">
                Ressourcen
              </a>
              <a className="rounded-md px-3 py-2 hover:bg-white/12" href="#contacts">
                Kontakte
              </a>
            </nav>
          </header>

          <div id="top" className="flex flex-1 items-center py-12 sm:py-16">
            <div className="max-w-2xl">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-[#93d6c9]">
                Startklar mit Governance-by-Design
              </p>
              <h1 className="mt-5 text-4xl font-semibold leading-tight sm:text-5xl lg:text-6xl">
                Willkommen bei AILIZA, {displayName}.
              </h1>
              <p className="mt-5 max-w-xl text-base leading-8 text-white/78 sm:text-lg">
                Dein Einstieg verbindet Teamkontext, Runtime-Verständnis und
                kontrollierte Autonomie. Alles Wichtige für die ersten Tage liegt hier
                in einer arbeitsfähigen Reihenfolge.
              </p>
              <div className="mt-8 grid max-w-xl grid-cols-3 gap-3">
                <div className="border border-white/20 bg-white/10 p-4">
                  <span className="block text-2xl font-semibold">{progress}%</span>
                  <span className="mt-1 block text-xs uppercase tracking-[0.12em] text-white/62">
                    Fortschritt
                  </span>
                </div>
                <div className="border border-white/20 bg-white/10 p-4">
                  <span className="block text-2xl font-semibold">4</span>
                  <span className="mt-1 block text-xs uppercase tracking-[0.12em] text-white/62">
                    Fokus-Tage
                  </span>
                </div>
                <div className="border border-white/20 bg-white/10 p-4">
                  <span className="block text-2xl font-semibold">1</span>
                  <span className="mt-1 block text-xs uppercase tracking-[0.12em] text-white/62">
                    Mentor
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-[#ddd5ca] bg-[#fffdf8]">
        <div className="mx-auto grid max-w-7xl gap-4 px-5 py-5 sm:px-8 md:grid-cols-4 lg:px-10">
          {tracks.map((track) => (
            <button
              key={track.id}
              type="button"
              onClick={() => setSelectedTrack(track.id)}
              className={`rounded-lg border p-4 text-left transition ${
                selectedTrack === track.id
                  ? "border-[#0f766e] bg-[#e7f6f2] text-[#123332]"
                  : "border-[#ddd5ca] bg-white text-[#343d3c] hover:border-[#0f766e]"
              }`}
            >
              <span className="text-xs font-semibold uppercase tracking-[0.14em] text-[#8f4a3d]">
                {track.eyebrow}
              </span>
              <span className="mt-2 block text-lg font-semibold">{track.label}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-6 px-5 py-8 sm:px-8 lg:grid-cols-[1.35fr_0.65fr] lg:px-10">
        <article
          id="checklist"
          className="rounded-lg border border-[#ddd5ca] bg-white p-5 shadow-sm sm:p-6"
        >
          <div className="flex flex-col gap-4 border-b border-[#e7ded3] pb-5 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.14em] text-[#0f766e]">
                Einstiegspfad
              </p>
              <h2 className="mt-2 text-2xl font-semibold">Deine Onboarding-Checkliste</h2>
            </div>
            <div className="min-w-[220px]">
              <div className="h-2 overflow-hidden rounded-md bg-[#e8e0d6]">
                <div
                  className="h-full bg-[#0f766e] transition-all"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="mt-2 text-sm text-[#66706f]">
                {completedCount} von {checklist.length} Punkten erledigt
              </p>
            </div>
          </div>

          <div className="mt-5 grid gap-6 md:grid-cols-2">
            {Object.entries(byPhase).map(([phase, items]) => (
              <div key={phase}>
                <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-[#8f4a3d]">
                  {phase}
                </h3>
                <div className="mt-3 divide-y divide-[#ece4d9] border-y border-[#ece4d9]">
                  {items.map((item) => (
                    <label
                      key={item.id}
                      className="grid cursor-pointer grid-cols-[auto_1fr] gap-3 py-4"
                    >
                      <input
                        type="checkbox"
                        checked={Boolean(completed[item.id])}
                        onChange={() => toggleItem(item.id)}
                        className="mt-1 h-5 w-5 accent-[#0f766e]"
                      />
                      <span>
                        <span className="block font-semibold">{item.title}</span>
                        <span className="mt-1 block text-sm leading-6 text-[#66706f]">
                          {item.detail}
                        </span>
                        <span className="mt-2 inline-block rounded-md bg-[#f0ece4] px-2 py-1 text-xs font-semibold text-[#5e4b3f]">
                          {item.owner}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <button
            type="button"
            onClick={completeToday}
            className="mt-6 rounded-md bg-[#101514] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#26302f]"
          >
            Heutige Punkte als erledigt markieren
          </button>
        </article>

        <aside
          id="governance"
          className="rounded-lg border border-[#ddd5ca] bg-[#17201f] p-5 text-white shadow-sm sm:p-6"
        >
          <p className="text-sm font-semibold uppercase tracking-[0.14em] text-[#93d6c9]">
            Rollenfokus
          </p>
          <h2 className="mt-2 text-2xl font-semibold">{selectedTrackData.label}</h2>
          <p className="mt-4 text-sm leading-7 text-white/78">{selectedTrackData.focus}</p>
          <dl className="mt-6 space-y-4 border-t border-white/14 pt-5">
            <div>
              <dt className="text-xs uppercase tracking-[0.14em] text-white/50">
                Ansprechpartner
              </dt>
              <dd className="mt-1 font-semibold">{selectedTrackData.owner}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-[0.14em] text-white/50">
                Erstes Arbeitsergebnis
              </dt>
              <dd className="mt-1 leading-6">{selectedTrackData.firstArtifact}</dd>
            </div>
          </dl>
          <a
            href="mailto:people@ailiza.example"
            className="mt-6 inline-flex rounded-md bg-[#d7a85f] px-4 py-3 text-sm font-semibold text-[#1f2424] transition hover:bg-[#efc77d]"
          >
            Onboarding-Team kontaktieren
          </a>
        </aside>
      </section>

      <section id="first-week" className="bg-[#fffdf8]">
        <div className="mx-auto max-w-7xl px-5 py-8 sm:px-8 lg:px-10">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.14em] text-[#0f766e]">
                Erste Woche
              </p>
              <h2 className="mt-2 text-2xl font-semibold">Arbeitsplan ohne Leerlauf</h2>
            </div>
            <div className="grid grid-cols-4 rounded-lg border border-[#ddd5ca] bg-white p-1">
              {dayTabs.map((day) => (
                <button
                  key={day.id}
                  type="button"
                  onClick={() => setSelectedDay(day.id)}
                  className={`rounded-md px-3 py-2 text-sm font-semibold transition ${
                    selectedDay === day.id
                      ? "bg-[#0f766e] text-white"
                      : "text-[#4f5b5a] hover:bg-[#edf7f4]"
                  }`}
                >
                  {day.label}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {currentSchedule.map((item) => (
              <article
                key={`${selectedDay}-${item.time}`}
                className="rounded-lg border border-[#ddd5ca] bg-white p-5 shadow-sm"
              >
                <p className="text-sm font-semibold text-[#8f4a3d]">{item.time}</p>
                <h3 className="mt-2 text-lg font-semibold">{item.title}</h3>
                <p className="mt-2 text-sm font-semibold text-[#0f766e]">{item.room}</p>
                <p className="mt-4 text-sm leading-6 text-[#66706f]">{item.outcome}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="resources" className="mx-auto max-w-7xl px-5 py-8 sm:px-8 lg:px-10">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {resources.map((resource) => (
            <a
              key={resource.title}
              href={resource.href}
              className="rounded-lg border border-[#ddd5ca] bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-[#0f766e]"
            >
              <span className="text-xs font-semibold uppercase tracking-[0.14em] text-[#8f4a3d]">
                {resource.label}
              </span>
              <span className="mt-3 block text-lg font-semibold">{resource.title}</span>
              <span className="mt-3 block text-sm leading-6 text-[#66706f]">
                {resource.description}
              </span>
            </a>
          ))}
        </div>
      </section>

      <section id="contacts" className="border-t border-[#ddd5ca] bg-[#202826] text-white">
        <div className="mx-auto grid max-w-7xl gap-6 px-5 py-8 sm:px-8 md:grid-cols-3 lg:px-10">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.14em] text-[#93d6c9]">
              Kontakte
            </p>
            <h2 className="mt-2 text-2xl font-semibold">Schnelle Wege zum richtigen Menschen</h2>
          </div>
          <div className="border-l border-white/14 pl-5">
            <p className="text-sm uppercase tracking-[0.14em] text-white/50">People</p>
            <a className="mt-2 block font-semibold" href="mailto:people@ailiza.example">
              people@ailiza.example
            </a>
          </div>
          <div className="border-l border-white/14 pl-5">
            <p className="text-sm uppercase tracking-[0.14em] text-white/50">Runtime Support</p>
            <a className="mt-2 block font-semibold" href="mailto:runtime@ailiza.example">
              runtime@ailiza.example
            </a>
          </div>
        </div>
      </section>
    </main>
  );
}
