# Contributing to FABulous

Thank you for your interest in contributing to FABulous! Contributions of all kinds are welcome, including bug reports, documentation, code, and design feedback.

## How to Contribute

1. Fork the repository and create a topic branch from `main`.
2. Make your changes, following the conventions described in [`Development`](https://fabulous.readthedocs.io/en/latest/developer_guide/development.html) and enforced by `pre-commit`.
3. Run the test suite (`pytest`) and `pre-commit run --all-files` before submitting.
4. Open a pull request against `main` with a clear description of the change and its motivation.

## Contributing with AI Coding Assistants

AI-assisted contributions are welcome, but the policy in the [Coding Assistants and Generative AI](https://fabulous.readthedocs.io/en/latest/developer_guide/development.html#coding-assistants-and-generative-ai) section of the development guide applies in full. In short: you are responsible for the correctness, licensing, and quality of everything you submit, you must understand and be able to defend the change, and you must verify that it solves the problem (a green CI run is not proof of correctness).

For tooling, point your assistant (Claude Code, Gemini CLI, Cursor, GitHub Copilot, Codex, Aider, etc.) at [`AGENTS.md`](./AGENTS.md). It is the single source of truth for project conventions, build commands, and architecture notes. The agent-specific files (`CLAUDE.md`, `GEMINI.md`, `.cursorrules`, `.github/copilot-instructions.md`) are symlinks to `AGENTS.md`, so every supported tool reads the same guidance.

When proposing changes to agent guidance, edit `AGENTS.md` directly; do not replace the symlinks with copies. Contributors on Windows may need to enable Developer Mode (or `git config --global core.symlinks true`) for git to materialise the symlinks; on Linux and macOS they work out of the box.

## Recognition

The list of contributors in [`AUTHORS.md`](./AUTHORS.md) is generated automatically from the GitHub contributors API and refreshed on every release as part of the `release-please` flow. If you contribute via a GitHub account, you will appear there automatically once the next release is cut. No manual action is required.

## Licensing of Contributions

FABulous is licensed under the [Apache License 2.0](./LICENSE).

By submitting a pull request to this repository, you agree that:

1. Your contribution is licensed to the project and its users under the same Apache License 2.0 that covers the project (the "inbound = outbound" rule, also established by [GitHub Terms of Service §D.6](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#6-contributions-under-repository-license)).
2. You have the right to grant this license: the contribution is your own original work, or you have obtained the necessary permission from your employer or other rights-holder to contribute it under these terms.
3. Your contribution may be redistributed and used in derivative works (including commercial products built on top of FABulous) under the terms of the Apache License 2.0, including its patent grant and sublicensing provisions.

If you cannot agree to these terms, please do not submit a pull request.
