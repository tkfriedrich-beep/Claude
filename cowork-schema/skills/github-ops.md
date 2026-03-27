# Skill: GitHub Operations

Reusable playbook for common GitHub workflows.

## PR Workflow

1. Create a feature branch from main: `git checkout -b feature/<name>`
2. Make changes and commit with descriptive messages
3. Push with `-u origin <branch>`
4. Create PR via `mcp__github__create_pull_request`
5. Monitor CI and reviews via `subscribe_pr_activity`

## Issue Management

- Use `mcp__github__list_issues` to check open work
- Use `mcp__github__add_issue_comment` for updates
- Link PRs to issues in PR descriptions

## Release Workflow

1. Ensure all PRs are merged to main
2. Tag the release: `git tag -a v<version> -m "Release v<version>"`
3. Push tags: `git push origin --tags`
4. Create release via `mcp__github__list_releases` / GitHub API

## Conventions

- Branch naming: `feature/`, `fix/`, `docs/`
- Commit messages: imperative mood, concise, link issues
- PR titles: under 70 characters, descriptive
