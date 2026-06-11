"""AILIZA - EU-konformer AI Agent"""
import argparse, os, sys

def main():
    parser = argparse.ArgumentParser(description="AILIZA - EU-konformer AI Agent")
    parser.add_argument("--model", default="")
    parser.add_argument("--language", default="de", choices=["de","en"])
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--no-oversight", action="store_true")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()

    if args.version:
        print("AILIZA v0.1.0 - EU AI Act + DSGVO konform")
        sys.exit(0)

    print("=" * 60)
    print("AILIZA - EU-konformer AI Agent")
    print("=" * 60)

    from apps.backend.compliance.eu_ai_act import EUAIActCompliance
    compliance = EUAIActCompliance(system_name="AILIZA", version="0.1.0")
    print()
    print(compliance.get_transparency_notice(language=args.language))
    print()

    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENROUTER_API_KEY")

    if args.demo or not api_key:
        _run_demo(compliance)
        return

    _run_interactive(args, api_key)

def _run_demo(compliance):
    from apps.backend.compliance.dsgvo import DSGVOCompliance
    from apps.backend.audit.audit_logger import AuditLogger
    print("--- DEMO MODUS ---")
    print()
    dsgvo = DSGVOCompliance(user_id="demo_user_001")
    print("DSGVO Status:")
    for k, v in dsgvo.get_status().items():
        print(f"  {k}: {v}")
    print()
    print("EU AI Act Status:")
    for k, v in compliance.get_status().items():
        print(f"  {k}: {v}")
    print()
    print("Phase 1 + 2 erfolgreich installiert!")
    print("Setze ANTHROPIC_API_KEY in .env fuer den vollen Agent-Betrieb.")

def _run_interactive(args, api_key):
    from apps.backend.agent.agent_core import AILIZAAgent
    from apps.backend.tools.standard_tools import get_standard_tools
    agent = AILIZAAgent(model=args.model or "claude-sonnet-4-6-20251001", api_key=api_key, human_oversight=not args.no_oversight)
    tools = get_standard_tools()
    for name, tool_info in tools.items():
        agent.register_tool(name=name, func=tool_info["func"], requires_approval=tool_info["requires_approval"])
        agent._tool_registry[name]["schema"] = tool_info["schema"]
    print(f"Agent bereit | Tools: {len(tools)} | Modell: {agent.model}")
    print("Tippe 'beenden' zum Beenden, 'status' fuer Compliance-Status")
    print()
    while True:
        try:
            user_input = input("Du: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAuf Wiedersehen!")
            break
        if not user_input: continue
        if user_input.lower() in ("beenden","exit","quit"):
            print("Auf Wiedersehen!")
            break
        if user_input.lower() == "status":
            import json
            print(json.dumps(agent.get_compliance_report(), indent=2, ensure_ascii=False))
            continue
        try:
            response = agent.chat(user_input)
            print(f"\nAILIZA: {response}\n")
        except Exception as e:
            print(f"Fehler: {e}")

if __name__ == "__main__":
    main()
