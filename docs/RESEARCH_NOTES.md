# Research notes used for architecture

1. OpenHands Software Agent SDK: modular agents, tools, workspaces, conversations, skills, state, MCP, and security validation.
   https://github.com/OpenHands/software-agent-sdk
   https://github.com/OpenHands/docs/blob/main/sdk/arch/agent.mdx

2. Microsoft UFO²: Windows AgentOS, HostAgent/AppAgent hierarchy, UI Automation + Win32/WinCOM, hybrid GUI/API, state machines, RAG experience.
   https://github.com/microsoft/UFO/blob/main/documents/docs/ufo2/overview.md

3. OSWorld 2.1: long-horizon computer-use benchmark and reproducible evaluation artifacts.
   https://github.com/xlang-ai/OSWorld-V2

4. Browser Use: browser agent ecosystem and self-healing browser-harness ideas.
   https://github.com/browser-use/browser-use
   https://github.com/browser-use/browser-harness

Architecture decisions in this package:
- typed world state before LLM interpretation;
- action postconditions and observation-driven recovery;
- two execution worlds (Web + Windows) sharing one cognitive runner;
- experience memory before fine-tuning;
- project research as a first-class capability, not a chat-only web browse.
