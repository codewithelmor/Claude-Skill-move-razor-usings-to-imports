# move-razor-usings-to-imports

A Claude Code skill that moves plain `@using` directives out of `.razor` files and into the nearest `_Imports.razor` file.

It wraps the `move_razor_usings_to_imports.py` script (cross-platform). This is a non-interactive version of the original script, so Claude can run it.

---

## What it does

For each Blazor project (a `.csproj` file that has `.razor` files) you choose:

1. Finds every `_Imports.razor` file in the project (skips `bin`, `obj`, `node_modules`) and prints them as a hierarchy, with the number of pages that use each one as their nearest.
2. For each `.razor` file, walks **up** from the file's folder to the project root and uses the **nearest** `_Imports.razor` file. This is how Razor itself applies these files, so behavior is preserved:
   - `Pages/Manage/Email.razor` file goes to the `Pages/Manage/_Imports.razor` file
   - `Pages/Login.razor` file goes to the `Pages/_Imports.razor` file
   - `Shared/Foo.razor` file goes to the nearest `_Imports.razor` file above the `Shared/` folder
3. If the namespace is already imported by an `_Imports.razor` file above the page, the line is simply removed and nothing is added.
4. If no `_Imports.razor` file exists above a page, the project-root one is used and created. The preview marks it as a **NEW FILE**.
5. Removes only the plain `@using Namespace` lines from the pages. Line endings, BOM, and the trailing newline are preserved exactly.
6. Edits existing `_Imports.razor` files minimally: new usings are inserted after the last existing `@using`, and nothing else is reordered.

**Never moves** (these are reported, but left in place for you to review):

- `@using static Foo`
- `@using Bar = Some.Other.Namespace`

Only pages that contain a plain `@using` line are modified.

---

## Why a skill (and not a command, subagent, hook, or MCP server)

| Option | Fit | Reason |
|---|---|---|
| **Skill** | Best | Bundles the `.py` file next to its instructions. Works as a `/slash-command`. |
| Command only | OK | A single markdown file cannot cleanly carry the script. |
| Subagent | Overkill | Meant for tasks that need their own context or judgment. This script is deterministic. |
| Hook / MCP server | Overkill | Too heavy for a one-off refactoring script. |

---

## Folder structure

```
.claude/skills/move-razor-usings-to-imports/
├── SKILL.md
├── README.md
└── move_razor_usings_to_imports.py
```

- Put it in `.claude/skills/` inside your repo to use it in that project only.
- Put it in `~/.claude/skills/` to use it in all your projects.

---

## Installation

1. Create the folder: `.claude/skills/move-razor-usings-to-imports/`
2. Copy `move_razor_usings_to_imports.py` into the folder.
3. Create the `SKILL.md` file in the same folder (content below).
4. Restart Claude Code.
5. Type `/` and check that `move-razor-usings-to-imports` appears in the list.

Requirement: Python 3.8 or newer.

### SKILL.md file

```markdown
---
name: move-razor-usings-to-imports
description: Moves plain @using directives out of .razor files into the nearest _Imports.razor file. Use when the user asks to clean up or consolidate @using lines in Blazor or Razor components.
disable-model-invocation: true
argument-hint: [root-path] [project-name]
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
```

### About `disable-model-invocation: true`

The script changes many files, so only you can trigger it by typing the slash command. Claude will not run it on its own, and it will not load the skill description into its context.

---

## Usage

### In Claude Code

```
/move-razor-usings-to-imports C:\path\to\solution
```

To go straight to one project (the project name is the `.csproj` file name without the extension):

```
/move-razor-usings-to-imports C:\path\to\solution BlazorApp
```

or, for the current directory:

```
/move-razor-usings-to-imports
```

Claude will:

1. List the Blazor projects found. If there is more than one and you did not name one, it asks which to process.
2. Run the preview and summarize it: the `_Imports.razor` files found, what each one gains, which pages lose lines, and any new `_Imports.razor` file that would be created.
3. Ask for your confirmation.
4. Run the real change (`--apply`).
5. Run `dotnet build` and report any errors.

### Running the script directly (without Claude)

```bash
# List the Blazor projects found
python move_razor_usings_to_imports.py --path C:\src\MySolution --list

# Preview only (this is the default)
python move_razor_usings_to_imports.py --path C:\src\MySolution --project BlazorApp

# Apply the changes
python move_razor_usings_to_imports.py --path C:\src\MySolution --project BlazorApp --apply
```

### Script options

| Option | Default | Description |
|---|---|---|
| `--path` | `.` | Root folder to scan for Blazor projects. |
| `--list` | off | List the Blazor projects found, then exit. |
| `--project` | all | One or more project names. Omit it, or use `all`, for every project. |
| `--apply` | off | Write the changes. Without it, the run is a preview. |
| `--dry-run` | on | Accepted for compatibility. Preview is already the default. |

---

## What changed from the original script

The original script was interactive. It asked you to pick projects, choose dry run or apply, and type Y/N for each project. Claude cannot answer those prompts, so the script was changed to:

- Take the project choice from `--project` (or `--list` to see the options).
- Run as a preview unless `--apply` is passed.
- Remove the Y/N prompt. The confirmation now happens in the chat, and the `SKILL.md` file tells Claude to ask you before it runs `--apply`.

The moving logic itself was not changed.

---

## Example

**Before** (`Pages/Manage/Email.razor` file):

```razor
@page "/email"
@using My.Models
@using My.Services

<h1>Email</h1>
```

**After** (`Pages/Manage/Email.razor` file):

```razor
@page "/email"

<h1>Email</h1>
```

**`_Imports.razor` file** (the nearest one above the page) gains:

```razor
@using My.Models
@using My.Services
```

**Sample preview output:**

```
Detected 1 _Imports.razor file(s) (hierarchy, nearest-wins):
  _Imports.razor   [2 page(s) use this as their nearest]

Planned changes (only pages that contain @using lines are touched):

  Target: _Imports.razor
    Add (2):
      @using My.Models
      @using My.Services
    Remove from:
      Pages/Login.razor
        line 2: @using System.Net.Http  (already imported above)
        line 3: @using My.Models
      Pages/Manage/Email.razor
        line 2: @using My.Models
        line 3: @using My.Services

  Totals: 4 line(s) removed from 2 page(s); 2 using(s) added across 1 _Imports.razor file(s).

  Alias/static @using lines found - NOT moved, review manually (1):
    Login.razor (line 4): @using static System.Math

DRY RUN - no files were changed. Re-run with --apply to write the changes.
```

---

## CLAUDE.md file

You do **not** need to reference this skill in the `CLAUDE.md` file. Claude Code finds skills automatically from the `.claude/skills/` folder (project) or the `~/.claude/skills/` folder (personal).

A `CLAUDE.md` file entry is only useful if you want Claude to recommend the skill. In that case:

```markdown
## Skills
- `/move-razor-usings-to-imports`: moves @using lines from .razor files into _Imports.razor files. Suggest it when .razor files have many per-page @using lines.
```

If you add this, also remove `disable-model-invocation: true` from the `SKILL.md` file, otherwise the setting still blocks Claude from running the skill by itself. Keeping it manual-only is the safer choice, so skipping the `CLAUDE.md` file entry is recommended.

---

## Tips

- Commit or stash your changes first, so you can review the result with `git diff`.
- Always preview first (the skill does this for you).
- On Windows, `python3` may not exist. If so, change the command in the `SKILL.md` file to `python`.
- If `${CLAUDE_SKILL_DIR}` does not resolve in your version of Claude Code, use the relative path `.claude/skills/move-razor-usings-to-imports/move_razor_usings_to_imports.py` instead.
- After the run, build the solution. A moved using can expose naming conflicts that were hidden before.

---

## Using it in claude.ai (not Claude Code)

Skills also work in claude.ai:

1. Zip the `move-razor-usings-to-imports` folder (the folder must be at the root of the zip file).
2. Upload it in **Settings** under **Capabilities**.

Claude can then run the script in its sandbox, but it only sees files you upload. For a real solution folder, Claude Code is the better fit.

---

## Known limits

- A using moved into a sub-folder `_Imports.razor` file applies to every `.razor` file in that folder and below, not just the page it came from.
- Alias and static `@using` lines are never moved.
- The whole page is scanned, not only the top of the file. Any line that is only `@using Namespace` is treated as a plain using, even if it sits inside a code block.
- Only projects (`.csproj` files) that contain `.razor` files are listed.
