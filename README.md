## TABLE OF CONTENTS

1. [Core Concepts](#core-concepts)
2. [File Structure](#file-structure)
3. [Data Classes](#data-classes)
4. [Internal Data Structures](#internal-data-structures)
5. [Parsing Logic](#parsing-logic)
6. [Relationship Building](#relationship-building)
7. [Display Logic](#display-logic)
8. [User Commands](#user-commands)
9. [Complete Examples](#complete-examples)

---

## CORE CONCEPTS

### Two Types of Links

The script handles two fundamentally different linking mechanisms:

**1. Direct Task-to-Task Links**
```
Task A (id:AAA, link:BBB) → Task B (id:BBB)
Result: Task A appears as child of Task B
```

**2. Task-to-Note Links** (indirect, through note heading)
```
Task A (id:AAA) 
  ├─ notes/AAA.md contains:
  │    ## Research Note (id:CCC)
  │
Task B (link:CCC) 
Result: Task B appears under the note heading under Task A
```

### Key Insight
The second type is complex: Task B doesn't link directly to Task A, but to a *note heading inside Task A's markdown file*. The script must:
1. Find which task owns the note file containing heading CCC
2. Display Task B under that heading
3. Display the heading under the owning task

---

## FILE STRUCTURE

### Task Files
- **Location**: `~/Documents/todo/todo.txt` and `~/Documents/todo/done.txt`
- **Format**: One task per line
- **Example**:
  ```
  (B) Implement new feature +urgent st:run due:2026-02-15 @work area:dev type:do id:20260205215937 link:20260125174752
  ```

### Note Files
- **Location**: `~/Documents/todo/notes/`
- **Naming**: `{task_id}.md` (e.g., `20260205215937.md`)
- **Content**: Markdown with special headings that have `type:` attribute
- **Example**:
  ```markdown
  # Main research note type:obs date:2026-02-05 id:20260205230846
  
  This is the content under the heading.
  It can span multiple lines.
  
  ## Nested note type:hyp id:20260205230847
  
  More content here.
  ```

### Important Note Properties
- **ONLY** headings with `type:` attribute are considered "research notes"
- Headings **WITHOUT** `type:` are **completely ignored** (including all their content)
- Research note headings can have their own unique `id:` (different from task ID)
- Content between research note headings is captured and can be displayed with -sc
- Research note headings can be nested (## is child of #)
- **Example**:
  ```markdown
  # Research note type:obs
  This content is CAPTURED
  
  # Regular heading (no type:)
  This content is IGNORED - won't be shown anywhere
  
  ## Another research note type:hyp
  This content is CAPTURED
  ```

---

## DATA CLASSES

### Task
Represents a single task from todo.txt or done.txt.

```python
@dataclass
class Task:
    line_num: int              # Line number in file (for user reference)
    raw_text: str              # Original line text
    title: str                 # Task title (cleaned)
    completed: bool            # True if starts with "x "
    priority: Optional[str]    # "A", "B", "C", etc.
    task_id: Optional[str]     # Unique ID (e.g., "20260205215937")
    status: Optional[str]      # "idea", "run", "hold", etc.
    link: Optional[str]        # ID this task links to (task OR note heading)
    area: Optional[str]        # Project area
    task_type: Optional[str]   # Task type
    tags: List[str]            # List of +tags
    context: Optional[str]     # @context
    due: Optional[str]         # Due date
    research_notes: List[ResearchNote]  # Notes from markdown file
```

**Critical**: `task.link` can point to EITHER:
- Another task's `task_id`
- A note heading's `note_id`

The script must determine which type of link it is.

### ResearchNote
Represents a heading with `type:` attribute in a markdown note file.

```python
@dataclass
class ResearchNote:
    title: str                      # Heading text (without attributes)
    note_type: Optional[str]        # "obs", "hyp", "do", "res", etc.
    date: Optional[str]             # Date from heading
    note_id: Optional[str]          # Unique ID for this heading
    link: Optional[str]             # Can link to other tasks/notes
    level: int                      # Heading level (1 for #, 2 for ##, etc.)
    content: Optional[str]          # Text between this heading and next
    children: List['ResearchNote']  # Nested child headings
```

**Hierarchy**: 
- Notes form a tree based on heading levels
- A `##` heading is a child of the previous `#` heading
- `content` contains all text lines between this heading and the next heading

### DisplayOptions
User-configurable display settings.

```python
@dataclass
class DisplayOptions:
    hide_notes: bool        # Hide notes without note_id
    show_done: bool         # Show completed tasks
    only_linked: bool       # Show only tasks with relationships
    show_context: bool      # Show note content (text under headings)
    area: Optional[str]     # Filter by area
    status: Optional[str]   # Filter by status
    tags: Optional[List[str]]  # Filter by tags
    context: Optional[str]  # Filter by context
```

---

## INTERNAL DATA STRUCTURES

These dictionaries are built at runtime to enable efficient relationship queries.

### 1. id_to_task: Dict[str, Task]
Maps task ID to Task object.

```python
{
    "20260205215937": Task(line_num=52, title="Main task", ...),
    "20260125174752": Task(line_num=53, title="Child task", ...)
}
```

**Purpose**: Quick lookup of any task by its ID.

### 2. note_to_task: Dict[str, Task]
Maps note heading ID to the task that OWNS the note file containing that heading.

```python
{
    "20260205230846": Task(id="20260205215937", ...)  # Task 52 owns this note
}
```

**Purpose**: When Task B has `link:20260205230846`, find which task owns the note with that ID.

**Building Logic**:
```python
for task in tasks:
    for note in task.research_notes:
        if note.note_id:
            note_to_task[note.note_id] = task
        # Recursively process note.children
```

### 3. note_relations: Dict[str, List[Task]]
Maps note heading ID to list of tasks that REFERENCE (link to) it.

```python
{
    "20260205230846": [
        Task(id="20260125174752", link="20260205230846", ...),
        Task(id="20260126180000", link="20260205230846", ...)
    ]
}
```

**Purpose**: When displaying a note heading, show all tasks that link to it.

**Building Logic**:
```python
for task in tasks:
    if task.link and task.link in note_to_task:
        note_relations[task.link].append(task)
```

### 4. relations: Dict[str, List[Tuple[Task, str]]]
Maps task ID to its DIRECT child tasks (task-to-task links only).

```python
{
    "20260205215937": [
        (Task(id="20260125174752", ...), 'link'),
        (Task(id="20260126180000", ...), 'link')
    ]
}
```

**Purpose**: Display direct task children.

**Important**: Does NOT include tasks linked via notes. Those are in `note_relations`.

### 5. child_to_parent: Dict[str, str]
Maps child task ID to parent task ID. Handles BOTH direct and note-mediated links.

```python
{
    "20260125174752": "20260205215937",  # Direct link OR note-mediated link
    "20260126180000": "20260205215937"
}
```

**Purpose**: Navigate upward in the tree to find root tasks.

**Building Logic**:
```python
for task in tasks:
    if task.link in id_to_task:
        # Direct task link
        child_to_parent[task.task_id] = task.link
    elif task.link in note_to_task:
        # Note-mediated link
        owner_task = note_to_task[task.link]
        child_to_parent[task.task_id] = owner_task.task_id
```

---

## PARSING LOGIC

### parse_task(line, line_num) → Task
Extracts all task attributes from a single todo.txt line using regex patterns.

**Key Patterns**:
- `id:(\S+)` → task_id
- `link:(\S+)` → link
- `area:(\S+)` → area
- `st:(\S+)` → status
- `\+(\S+)` → tags (can match multiple)
- `@(\S+)` → context
- `due:([\d-]+)` → due date
- `\(([A-Z]\))` → priority

### parse_research_section(content: str) → List[ResearchNote]
Parses markdown content and extracts research notes with their content.

**Algorithm**:
```
1. Initialize: 
   - notes = []
   - current_stack = []
   - current_content = []
   - collecting = False  # Are we inside a header with type:?

2. For each line in markdown:
   
   a. If line is a heading:
      - Extract: level, title_with_attrs
      - Check: has_type = 'type:' in title_with_attrs
      
      If has_type (header WITH type:):
        - If collecting and stack not empty:
          * Save current_content to stack[-1].content
          * Clear current_content
        
        - Extract: note_type, date, note_id, link
        - Clean title (remove attribute markers)
        - Create new ResearchNote object
        
        - Manage hierarchy:
          * Pop from stack all notes with level >= current level
          * If stack not empty: add note to stack[-1].children
          * Else: add note to root notes list
          * Push note to stack
        
        - Set collecting = True (start collecting content)
      
      If NOT has_type (header WITHOUT type:):
        - If collecting and stack not empty:
          * Save current_content to stack[-1].content
          * Clear current_content
        
        - Pop from stack all notes with level >= current level
        - Set collecting = False (STOP collecting content)
   
   b. If line is NOT a heading (regular text):
      - If collecting = True and line not empty:
        * Add line to current_content
      - Else: IGNORE the line (do not collect)

3. After all lines:
   - If collecting and stack not empty:
     * Save remaining content to stack[-1].content

4. Return root notes list
```

**Key Principle**: 
- Content is ONLY collected when `collecting = True`
- `collecting = True` only when we're inside a header with `type:`
- Headers without `type:` STOP content collection
- Their content is completely IGNORED

**Example**:
```markdown
# Main note type:obs id:AAA

Content line 1
Content line 2

# Header without type

This content is IGNORED
All of it

## Nested note type:hyp id:BBB

Nested content
```

Results in:
```python
[
    ResearchNote(
        title="Main note",
        note_type="obs",
        note_id="AAA",
        level=1,
        content="Content line 1\nContent line 2",
        children=[]
    ),
    ResearchNote(
        title="Nested note",
        note_type="hyp",
        note_id="BBB",
        level=2,
        content="Nested content",
        children=[]
    )
]
```

Note: The "Header without type" and its content are completely ignored.

---

## RELATIONSHIP BUILDING

### build_relations(tasks) → (relations, id_to_task, child_to_parent)

**Step-by-step**:

```
1. Create id_to_task mapping:
   id_to_task = {task.task_id: task for task in tasks if task.task_id}

2. Create note_to_task mapping:
   For each task:
       For each note in task.research_notes (recursively):
           if note.note_id:
               note_to_task[note.note_id] = task

3. Build relations and child_to_parent:
   For each task:
       if task.link exists:
           
           if task.link in id_to_task:
               # Direct task-to-task link
               relations[task.link].append((task, 'link'))
               child_to_parent[task.task_id] = task.link
           
           elif task.link in note_to_task:
               # Note-mediated link
               owner_task = note_to_task[task.link]
               child_to_parent[task.task_id] = owner_task.task_id
               # DO NOT add to relations (handled via note_relations)

4. Return (relations, id_to_task, child_to_parent)
```

### build_note_relations(tasks, note_to_task) → note_relations

```
For each task:
    if task.link in note_to_task:
        note_relations[task.link].append(task)

Return note_relations
```

---

## DISPLAY LOGIC

### print_task_tree(task, relations, id_to_task, options, ...)

**Recursive tree printing algorithm**:

```
1. Check visibility:
   - If task already printed: return
   - If task is completed and show_done=False: return
   - Mark task as printed

2. Print task information:
   - Format: [line_num] title ¦ priority status area @context [due]
   - Colors:
     * Line number: cyan (if active) or gray (if completed)
     * Title: white (255) for active tasks, gray (242) for completed
     * Separator ¦: white (255) for active tasks, gray (242) for completed
     * Priority, status, metadata: various colors based on type
   - Use colors based on priority, status, completion

3. Count children:
   - Count visible research notes
   - Count visible child tasks from relations dict
   - total_children = notes_count + tasks_count

4. Print research notes:
   For each note in task.research_notes:
       print_single_note_tree(note, ...)

5. Print child tasks:
   For each (child_task, _) in relations[task.task_id]:
       if visible:
           print_task_tree(child_task, ...)
```

### print_single_note_tree(note, prefix, is_last, ...)

**Note rendering with content**:

```
1. Check visibility:
   - If hide_notes=True and note has no note_id: skip (with exceptions)

2. Print note heading:
   - Format: [TYPE] title [date]
   - Colors:
     * Type badge ([OBS], [HYP], etc.): colored based on note type
     * Title: white (255)
     * Date: gray (242)
   - Use tree connectors: └─ or ├─

3. Print note content:
   if show_context=True and note.content exists:
       For each line in note.content:
           Render markdown formatting (bold, italic, code)
           Print line with proper indentation
           Base color: gray (242)
           Markdown colors: bold=gray(242), italic=dark_gray(240), code=dark_gray(240) on bg(236)

4. Count children:
   - Child notes
   - Tasks linked to this note (from note_relations)
   - Nested linked task (from note.link)

5. Print child notes recursively:
   For each child in note.children:
       print_single_note_tree(child, ...)

6. Print referencing tasks:
   For each task in note_relations[note.note_id]:
       print_task_tree(task, ...)

7. Print directly linked task:
   if note.link in id_to_task:
       print_task_tree(id_to_task[note.link], ...)
```

### Tree Indentation
- Root level: no prefix
- Child of task: prefix + "├─ " or "└─ " 
- Next level: prefix + "│  " or "   "
- Content lines: use same prefix as note's next level

---

## USER COMMANDS

### Display Modes

**1. Default (no arguments)**
```bash
<Enter>
```
Shows all root tasks with their full trees.

**2. Branch mode**
```bash
45
```
Shows only the subtree starting from task at line 45.

**3. Root mode**
```bash
-r 45
# or
45 -r
```
Finds the root of task at line 45 and shows the full tree from root.

### Display Flags

**-hn / --hide-notes**
- Hides research notes
- EXCEPTION: Always shows notes with note_id (to preserve links)

**-sd / --show-done**
- Shows completed tasks (normally hidden)

**-l / --link-lock**
- Shows only tasks that have links or are linked to
- Hides standalone notes without references

**-sc / --show-context**
- Shows content under each note heading
- Content displayed in gray color with markdown formatting support
- Maintains tree indentation
- **Markdown support**: `**bold**`, `*italic*`, `` `code` ``
  - Bold: gray text (242) with bold style
  - Italic: dark gray text (240) with italic style
  - Code: dark gray text (240) on light gray background (236)

### Filter Flags

**-a / --area <name>**
```bash
-a work
```
Filter by area.

**-s / --status <status>**
```bash
-s run
```
Filter by status.

**-t / --tag <tag1> [<tag2> ...]**
```bash
-t urgent bug
```
Filter by tags (all must match).

**-c / --context <context>**
```bash
-c home
```
Filter by context.

### Flag Combinations

All flags can be freely combined:
```bash
45 -r -hn -sd          # Line 45, root, hide notes, show done
-a work -s run -sc     # Area filter + status filter + show content
23 -sd -l -sc          # Line 23, show done, linked only, show content
```

---

## MARKDOWN RENDERING

When using the `-sc` flag, content displayed under research note headings supports markdown formatting. This allows visual emphasis and code highlighting directly in the terminal output.

### Supported Markdown Syntax

| Syntax | Example | Visual Result | Color | Style |
|--------|---------|---------------|-------|-------|
| `**bold**` | `**important**` | Bold text | Gray (242) | ANSI bold (`\x1b[1m`) |
| `*italic*` | `*emphasis*` | Italic text | Dark gray (240) | ANSI italic (`\x1b[3m`) |
| `` `code` `` | `` `function()` `` | Inline code | Dark gray (240) | Background (236) |

### Processing Algorithm

The `render_markdown()` function processes markdown in this order:

```
1. Apply base color (gray)
2. Process **bold** → ANSI bold codes
3. Process *italic* → ANSI italic codes + dark gray color
4. Process `code` → Dark gray text + light gray background
5. Return formatted string
```

**Processing order matters**: Bold is processed first, then italic, then code. This prevents conflicts when markdown is nested (e.g., `**bold with `code`**`).

### Where Formatting Applies

**✅ Formatted:**
- Content text under research note headings (when `-sc` is used)

**❌ Not Formatted:**
- Task titles
- Note heading titles
- Task metadata (status, area, context, etc.)
- Any text when `-sc` flag is NOT used

### Color Scheme

```python
# Content colors
"gray": "\x1b[38;5;242m"        # Regular text and bold text
"gray_dark": "\x1b[38;5;240m"   # Italic and code text (darker)
"white": "\x1b[38;5;255m"       # Task and note titles

# Code background
"code_bg": "\x1b[48;5;236m"     # Light gray background for code

# Styles
"bold": "\x1b[1m"               # Bold style
"italic": "\x1b[3m"             # Italic style
```

### Example

**Markdown content in note file:**
```markdown
# Research Note type:obs

This is **very important** information about the system.

The issue occurs when *cache* is full. Use `clear_cache()` to fix.

You can combine **bold with `code`** in one line.
```

**Command:**
```bash
./show_links.py 68 -sc
```

**Terminal Output:**
```
[68] Task Name ¦ run
 └─ [OBS] Research Note
    This is **very important** information about the system.
    
    The issue occurs when *cache* is full. Use `clear_cache()` to fix.
    
    You can combine **bold with `code`** in one line.
```

In the actual terminal:
- `**very important**` appears in bold gray
- `*cache*` appears in italic dark gray
- `` `clear_cache()` `` appears in dark gray on light background
- `` `code` `` inside bold also appears with background

### Implementation Details

**Function: `render_markdown(text: str, base_color: str = 'gray') → str`**

Uses regex patterns:
- Bold: `\*\*(.+?)\*\*`
- Italic: `(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)`
- Code: `` `([^`]+?)` ``

**Regex for italic** uses negative lookbehind/lookahead to avoid matching `**` (which is bold).

**Escape sequences** are properly managed - after code blocks, the base color is restored to maintain consistent gray coloring for the rest of the line.
