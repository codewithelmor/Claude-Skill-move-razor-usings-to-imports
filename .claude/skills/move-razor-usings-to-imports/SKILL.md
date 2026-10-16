---
name: move-razor-usings-to-imports
description: Moves plain @using directives out of .razor files into the nearest _Imports.razor file. Use when the user asks to clean up or consolidate @using lines in Blazor or Razor components.
disable-model-invocation: true
argument-hint: "[root-path] [project-name]"
allowed-tools: Bash(python3 *), Bash(python *)
---

# Move Razor @using lines to _Imports.razor

Arguments: `$ARGUMENTS` (first value is the root path, default is the current directory; optional second value is a project name).

The script never asks questions. It is a preview by default and only writes files when `--apply` is passed.

## Steps

1. List the Blazor projects:
   `python3 ${CLAUDE_SKILL_DIR}/move_razor_usings_to_imports.py --path "<root>" --list`
2. If more than one project is found and the user did not name one, ask which project(s) to process, or "all".
3. Run the preview (no `--apply`):
   `python3 ${CLAUDE_SKILL_DIR}/move_razor_usings_to_imports.py --path "<root>" --project <ProjectName>`
4. Summarize the preview: the `_Imports.razor` files found, which ones will gain usings, which pages will lose lines, and any new `_Imports.razor` file that will be created. Show the alias/static lines that were not moved.
5. Ask the user to confirm before making changes.
6. After confirmation, run the same command with `--apply`.
7. Run `dotnet build` and report any errors.

## Rules

- Do not edit the .razor files manually. The script handles all changes.
- Only plain `@using Namespace` lines are moved. `@using static X` and `@using Alias = X` lines are left in place and must be reviewed manually.
- A using moved into a sub-folder `_Imports.razor` file applies to every .razor file in that folder and below. Point this out in the summary if it happens.
- Remind the user to commit or stash their changes first so the result can be reviewed with `git diff`.
