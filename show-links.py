#!/usr/bin/env python3
import re
import os
import argparse
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field

# Try to import readline for Ctrl+L support
try:
    import readline
    HAS_READLINE = True
except ImportError:
    HAS_READLINE = False

# ANSI color constants
ANSI = {
    "red": "\x1b[38;5;174m", "green": "\x1b[38;5;108m", "yellow": "\x1b[38;5;180m",
    "blue": "\x1b[38;5;110m", "magenta": "\x1b[38;5;139m", "cyan": "\x1b[38;5;109m",
    "gray": "\x1b[38;5;245m", "gray_dark": "\x1b[38;5;240m", "reset": "\x1b[0m", 
    "orange": "\x1b[38;5;137m", "white": "\x1b[38;5;251m",
    "bold": "\x1b[1m", "italic": "\x1b[3m", "code_bg": "\x1b[48;5;236m",
    "end_bold": "\x1b[22m", "end_italic": "\x1b[23m", "end_bg": "\x1b[49m"
}

# Compiled regex patterns
PATTERNS = {
    'priority': re.compile(r'\(([A-Z])\)'),
    'title': re.compile(r'^(?:x\s+)?(?:\([A-Z]\)\s+)?(.+?)(?:\s+(?:area:|type:|st:|@|id:|link:|due:|rec:))'),
    'task_id': re.compile(r'id:(\S+)'),
    'link': re.compile(r'link:(\S+)'),
    'area': re.compile(r'area:(\S+)'),
    'type': re.compile(r'type:(\S+)'),
    'status': re.compile(r'st:(\S+)'),
    'tags': re.compile(r'\+(\S+)'),
    'context': re.compile(r'@(\S+)'),
    'due': re.compile(r'due:([\d-]+)'),
    'header': re.compile(r'^(#+)\s+(.+)'),
    'note_type': re.compile(r'type:(\w+)'),
    'note_date': re.compile(r'date:([\d-]+)'),
    'note_id': re.compile(r'id:(\S+)'),
}

# Color schemes
PRIORITY_COLORS = {'A': 'red', 'B': 'blue'}
STATUS_COLORS = {'idea': 'yellow', 'todo': 'gray', 'run': 'blue', 'hold': 'orange', 'lock': 'red'}
NOTE_TYPE_COLORS = {'OBS': 'green', 'HYP': 'yellow', 'DO': 'blue', 'RES': 'magenta', 'HOLD': 'orange', 'LOCK': 'red'}


@dataclass
class ResearchNote:
    """Note from Research section"""
    title: str
    note_type: Optional[str] = None
    date: Optional[str] = None
    note_id: Optional[str] = None
    link: Optional[str] = None
    level: int = 2
    content: Optional[str] = None
    children: List['ResearchNote'] = field(default_factory=list)


@dataclass
class Task:
    """Task from todo.txt"""
    line_num: int
    raw_text: str
    title: str
    completed: bool = False
    priority: Optional[str] = None
    task_id: Optional[str] = None
    status: Optional[str] = None
    link: Optional[str] = None
    area: Optional[str] = None
    task_type: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    context: Optional[str] = None
    due: Optional[str] = None
    research_notes: List[ResearchNote] = field(default_factory=list)


@dataclass
class DisplayOptions:
    """Display options for rendering tasks"""
    hide_notes: bool = False
    show_done: bool = False
    only_linked: bool = False
    show_context: bool = False
    area: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    context: Optional[str] = None


def extract(pattern_name: str, text: str) -> Optional[str]:
    """Extract field using compiled regex pattern"""
    if match := PATTERNS[pattern_name].search(text):
        return match.group(1)
    return None


def parse_task(line: str, line_num: int) -> Optional[Task]:
    """Parse task line and extract all attributes"""
    if not (stripped := line.strip()) or stripped.startswith('#'):
        return None
    
    title_match = PATTERNS['title'].match(line)
    return Task(
        line_num=line_num,
        raw_text=line,
        title=title_match.group(1).strip() if title_match else stripped,
        completed=stripped.startswith('x '),
        priority=extract('priority', line),
        task_id=extract('task_id', line),
        link=extract('link', line),
        area=extract('area', line),
        status=extract('status', line),
        task_type=extract('type', line),
        tags=PATTERNS['tags'].findall(line),
        context=extract('context', line),
        due=extract('due', line)
    )


def parse_research_section(content: str) -> List[ResearchNote]:
    """Parse headers with type: attribute from markdown file"""
    notes, current_stack = [], []
    lines = content.split('\n')
    current_content = []
    collecting = False  # Flag: are we currently inside a header with type:?
    
    for line in lines:
        header_match = PATTERNS['header'].match(line)
        
        if header_match:
            # Found a header
            level = len(header_match.group(1))
            title_with_attrs = header_match.group(2).strip()
            has_type = 'type:' in title_with_attrs
            
            if has_type:
                # Header WITH type:
                # Save accumulated content to previous note (if we were collecting)
                if collecting and current_stack and current_content:
                    current_stack[-1].content = '\n'.join(current_content).strip()
                    current_content = []
                
                # Extract attributes and clean title
                note_type = extract('note_type', title_with_attrs)
                note_date = extract('note_date', title_with_attrs)
                note_id = extract('note_id', title_with_attrs)
                note_link = extract('link', title_with_attrs)
                
                title = title_with_attrs
                for pattern in ['note_type', 'note_date', 'note_id', 'link']:
                    title = PATTERNS[pattern].sub('', title)
                title = title.strip()
                
                note = ResearchNote(title=title, note_type=note_type, date=note_date, 
                                  note_id=note_id, link=note_link, level=level)
                
                # Manage hierarchy stack - pop notes at same or lower level
                while current_stack and current_stack[-1].level >= level:
                    current_stack.pop()
                
                # Add note to hierarchy
                (current_stack[-1].children.append(note) if current_stack else notes.append(note))
                current_stack.append(note)
                
                # Start collecting content for this note
                collecting = True
            else:
                # Header WITHOUT type:
                # Save content if we were collecting
                if collecting and current_stack and current_content:
                    current_stack[-1].content = '\n'.join(current_content).strip()
                    current_content = []
                
                # Update stack for hierarchy (remove notes at same or lower level)
                while current_stack and current_stack[-1].level >= level:
                    current_stack.pop()
                
                # STOP collecting content
                collecting = False
        else:
            # Regular text line
            # Only collect if we're inside a header with type:
            if collecting and line.strip():
                current_content.append(line)
    
    # Save remaining content
    if collecting and current_stack and current_content:
        current_stack[-1].content = '\n'.join(current_content).strip()
    
    return notes


def read_note(notes_dir: Path, task_id: str) -> List[ResearchNote]:
    """Read note for task"""
    note_file = notes_dir / f"{task_id}.md"
    try:
        return parse_research_section(note_file.read_text(encoding='utf-8')) if note_file.exists() else []
    except Exception as e:
        print(f"Error reading note {note_file}: {e}")
        return []


def read_tasks(filepath: Path, notes_dir: Optional[Path]) -> List[Task]:
    """Read file and parse all tasks"""
    if not filepath.exists():
        return []
    
    tasks = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if (task := parse_task(line, line_num)) and task.task_id:
                    if notes_dir:
                        task.research_notes = read_note(notes_dir, task.task_id)
                    tasks.append(task)
    except Exception as e:
        print(f"Error reading file {filepath}: {e}")
    
    return tasks


def collect_note_to_task_map(tasks: List[Task]) -> Dict[str, Task]:
    """Create mapping from note_id to task that owns that note"""
    note_to_task = {}
    
    def process_note(note: ResearchNote, owner: Task):
        if note.note_id:
            note_to_task[note.note_id] = owner
        for child in note.children:
            process_note(child, owner)
    
    for task in tasks:
        for note in task.research_notes:
            process_note(note, task)
    
    return note_to_task


def build_note_relations(tasks: List[Task], note_to_task: Dict[str, Task]) -> Dict[str, List[Task]]:
    """Build mapping from note_id to tasks that reference this note"""
    note_relations = {}
    for task in tasks:
        if task.link and task.link in note_to_task:
            note_relations.setdefault(task.link, []).append(task)
    return note_relations


def build_relations(tasks: List[Task]) -> Tuple[Dict[str, List[Tuple[Task, str]]], Dict[str, Task], Dict[str, str]]:
    """Build relationship dictionaries between tasks"""
    id_to_task = {task.task_id: task for task in tasks if task.task_id}
    note_to_task = collect_note_to_task_map(tasks)
    relations, child_to_parent = {}, {}
    
    for task in tasks:
        if not task.link:
            continue
        # Link to task
        if task.link in id_to_task:
            relations.setdefault(task.link, []).append((task, 'link'))
            child_to_parent[task.task_id] = task.link
        # Link to note
        elif task.link in note_to_task:
            child_to_parent[task.task_id] = note_to_task[task.link].task_id
    
    return relations, id_to_task, child_to_parent


def colorize(text: str, color: str) -> str:
    """Wrap text in ANSI color"""
    return f"{ANSI[color]}{text}{ANSI['reset']}"


def render_markdown(text: str, base_color: str = 'gray') -> str:
    """Render markdown formatting (bold, italic, code) to ANSI codes"""
    if not text:
        return text
    
    # Apply base color first
    result = f"{ANSI[base_color]}"
    
    # Process markdown in order: bold, italic, code
    # Use negative lookbehind/lookahead to avoid matching escaped characters
    temp = text
    
    # Bold (**text**)
    temp = re.sub(
        r'\*\*(.+?)\*\*',
        lambda m: f"{ANSI['bold']}{m.group(1)}{ANSI['end_bold']}",
        temp
    )
    
    # Italic (*text*) - but not ** which was already processed
    temp = re.sub(
        r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)',
        lambda m: f"{ANSI['italic']}{ANSI['gray_dark']}{m.group(1)}{ANSI['end_italic']}{ANSI[base_color]}",
        temp
    )
    
    # Code (`text`)
    temp = re.sub(
        r'`([^`]+?)`',
        lambda m: f"{ANSI['code_bg']}{ANSI['gray_dark']}{m.group(1)}{ANSI['reset']}{ANSI[base_color]}",
        temp
    )
    
    result += temp + ANSI['reset']
    return result


def get_color(completed: bool, show_done: bool, default: str) -> str:
    """Get color based on completion status"""
    return 'gray' if (show_done and completed) else default


def is_visible(task: Task, show_done: bool) -> bool:
    """Check if task should be visible"""
    return show_done or not task.completed


def format_metadata(task: Task, show_done: bool) -> str:
    """Format task metadata"""
    parts = []
    
    if task.status:
        color = get_color(task.completed, show_done, STATUS_COLORS.get(task.status, 'reset'))
        parts.append(colorize(task.status + " ¦", color))
    
    if task.area:
        parts.append(colorize(task.area, get_color(task.completed, show_done, 'green')))
    
    if task.task_type:
        parts.append(colorize(task.task_type, get_color(task.completed, show_done, 'magenta')))
    
    if task.context:
        parts.append(colorize(f"@{task.context}", get_color(task.completed, show_done, 'blue')))
    
    if task.due:
        parts.append(colorize(f"[{task.due}]", get_color(task.completed, show_done, 'gray')))
    
    return " ".join(parts)


def format_task_info(task: Task, show_done: bool = False) -> str:
    """Format task information with colors"""
    line_color = 'gray' if task.completed else 'cyan'
    line_info = colorize(f"[{task.line_num}]", line_color)
    
    priority_str = ""
    if task.priority:
        color = get_color(task.completed, show_done, PRIORITY_COLORS.get(task.priority, 'reset'))
        priority_str = colorize(task.priority, color)
    
    title_str = colorize(task.title, 'gray') if (show_done and task.completed) else colorize(task.title, 'white')
    separator = colorize("¦", 'gray') if (show_done and task.completed) else colorize("¦", 'white')
    metadata_str = format_metadata(task, show_done)
    
    parts = [p for p in [line_info, title_str, separator, priority_str, metadata_str] if p]
    return " ".join(parts)


def format_note_type(note_type: str) -> str:
    """Format note type with color"""
    type_upper = note_type.upper()
    return colorize(f"[{type_upper}]", NOTE_TYPE_COLORS.get(type_upper, 'cyan'))


def format_note(note: ResearchNote) -> str:
    """Format note"""
    type_str = format_note_type(note.note_type) if note.note_type else "[NOTE]"
    date_str = colorize(f" [{note.date}]", 'gray') if note.date else ""
    return f"{type_str} {colorize(note.title, 'white')}{date_str}"


def print_tree_item(prefix: str, connector: str, content: str, color: str = 'cyan'):
    """Print tree element"""
    print(f"{colorize(prefix + connector, color)} {content}")


def note_has_id_recursive(note: ResearchNote) -> bool:
    """Check if note or any children have note_id"""
    return note.note_id is not None or any(note_has_id_recursive(c) for c in note.children)


def print_single_note_tree(note: ResearchNote, prefix: str, is_last: bool,
                           relations=None, id_to_task=None, options=None, 
                           printed_tasks=None, note_relations=None):
    """Print single note with children and linked tasks"""
    
    # Skip if hide_notes active and no note_id
    if options and options.hide_notes and not note.note_id:
        for child in note.children:
            if note_has_id_recursive(child):
                print_single_note_tree(child, prefix, is_last, relations, id_to_task, 
                                     options, printed_tasks, note_relations)
        return
    
    connector = "└─" if is_last else "├─"
    next_prefix = prefix + ("   " if is_last else "│  ")
    
    print_tree_item(prefix, connector, format_note(note))
    
    # Print note content if show_context is enabled
    if options and options.show_context and note.content:
        content_prefix = next_prefix
        for line in note.content.split('\n'):
            if line.strip():
                print(f"{content_prefix}{render_markdown(line, 'gray')}")
    
    # Get visible children
    child_notes = ([c for c in note.children if note_has_id_recursive(c)] 
                  if options and options.hide_notes else note.children)
    
    children_count = len(child_notes)
    
    # Check for linked task
    has_linked = (note.link and id_to_task and note.link in id_to_task 
                 and is_visible(id_to_task[note.link], options.show_done if options else False))
    if has_linked:
        children_count += 1
    
    # Check for referencing tasks
    ref_tasks = []
    if note.note_id and note_relations and note.note_id in note_relations:
        ref_tasks = [t for t in note_relations[note.note_id]
                    if is_visible(t, options.show_done if options else False)
                    and (not printed_tasks or t.task_id not in printed_tasks)]
        children_count += len(ref_tasks)
    
    current = 0
    
    # Print child notes
    for child in child_notes:
        current += 1
        print_single_note_tree(child, next_prefix, current == children_count,
                             relations, id_to_task, options, printed_tasks, note_relations)
    
    # Print referencing tasks
    for task in ref_tasks:
        current += 1
        print_task_tree(task, relations, id_to_task, options, next_prefix,
                       current == children_count, True, printed_tasks, note_relations)
    
    # Print linked task
    if has_linked:
        print_task_tree(id_to_task[note.link], relations, id_to_task, options,
                       next_prefix, True, True, printed_tasks, note_relations)


def print_task_tree(task: Task, relations, id_to_task, options, 
                   prefix="", is_last=True, is_child=False, 
                   printed_tasks=None, note_relations=None):
    """Recursively print task and all child tasks"""
    if printed_tasks is None:
        printed_tasks = set()
    
    if not is_visible(task, options.show_done) or task.task_id in printed_tasks:
        return
    
    printed_tasks.add(task.task_id)
    
    # Check for notes and children
    has_notes = (task.research_notes and 
                (not options.hide_notes or any(note_has_id_recursive(n) for n in task.research_notes)))
    
    filtered_children = [(c, t) for c, t in relations.get(task.task_id, [])
                        if is_visible(c, options.show_done)]
    
    # Count children
    notes_count = 0
    if has_notes:
        notes_count = (sum(1 for n in task.research_notes if note_has_id_recursive(n))
                      if options.hide_notes else len(task.research_notes))
    
    total_children = notes_count + len(filtered_children)
    
    # Print current task
    if is_child:
        connector = "└─" if is_last else "├─"
        color = 'gray' if task.completed else 'cyan'
        print_tree_item(prefix, connector, format_task_info(task, options.show_done), color)
        new_prefix = prefix + ("   " if is_last else "│  ")
    else:
        print(format_task_info(task, options.show_done))
        new_prefix = " "
    
    current = 0
    
    # Print notes
    if has_notes:
        notes_to_show = ([n for n in task.research_notes if note_has_id_recursive(n)]
                        if options.hide_notes else task.research_notes)
        
        for note in notes_to_show:
            current += 1
            print_single_note_tree(note, new_prefix, current == total_children,
                                 relations, id_to_task, options, printed_tasks, note_relations)
    
    # Print child tasks
    for child_task, _ in filtered_children:
        current += 1
        print_task_tree(child_task, relations, id_to_task, options, new_prefix,
                       current == total_children, True, printed_tasks, note_relations)


def matches_filters(task: Task, options: DisplayOptions) -> bool:
    """Check if task matches filters"""
    return not any([
        options.area and task.area != options.area,
        options.status and task.status != options.status,
        options.context and task.context != options.context,
        options.tags and not all(t in task.tags for t in options.tags)
    ])


def has_relations_or_notes(task: Task, relations, id_to_task, only_linked=False, 
                          show_done=False, note_to_task=None, note_relations=None) -> bool:
    """Check if task has relations or notes"""
    # Check child tasks
    if task.task_id in relations and any(is_visible(c, show_done) for c, _ in relations[task.task_id]):
        return True
    
    # Check parent
    if task.link:
        if task.link in id_to_task and is_visible(id_to_task[task.link], show_done):
            return True
        if note_to_task and task.link in note_to_task:
            return True
    
    # Check note references
    if only_linked and note_relations:
        def check_refs(note: ResearchNote) -> bool:
            if note.note_id and note.note_id in note_relations:
                if any(is_visible(t, show_done) for t in note_relations[note.note_id]):
                    return True
            return any(check_refs(c) for c in note.children)
        
        if any(check_refs(n) for n in task.research_notes):
            return True
    
    return bool(task.research_notes) if not only_linked else False


def find_root(task: Task, child_to_parent, id_to_task) -> Task:
    """Find root task (top parent)"""
    root, visited = task, {task.task_id}
    
    while root.task_id in child_to_parent:
        parent_id = child_to_parent[root.task_id]
        if parent_id in visited:
            break
        visited.add(parent_id)
        root = id_to_task[parent_id]
    
    return root


def collect_tree(task: Task, relations, collected=None) -> Set[str]:
    """Recursively collect all task IDs in tree"""
    if collected is None:
        collected = set()
    
    if task.task_id in collected:
        return collected
    
    collected.add(task.task_id)
    for child, _ in relations.get(task.task_id, []):
        collect_tree(child, relations, collected)
    
    return collected


def find_roots(relations, id_to_task, show_done) -> List[Task]:
    """Find root tasks (not children themselves)"""
    all_child_ids = {c.task_id for children in relations.values() for c, _ in children}
    
    return [id_to_task[tid] for tid in relations.keys()
            if tid not in all_child_ids 
            and is_visible(id_to_task[tid], show_done)
            and (show_done or any(not c.completed for c, _ in relations.get(tid, [])))]


def print_by_line(tasks, line_num, relations, id_to_task, child_to_parent, 
                 options, use_root=False, note_relations=None):
    """Print single task tree by line number"""
    if not (target := next((t for t in tasks if t.line_num == line_num), None)):
        print(colorize(f"✗ Task at line {line_num} not found\n", 'yellow'))
        return
    
    to_print = find_root(target, child_to_parent, id_to_task) if use_root else target
    
    if not is_visible(to_print, options.show_done):
        print(colorize(f"✗ Task at line {line_num} is completed (hidden). Use -sd to display.\n", 'yellow'))
        return
    
    print_task_tree(to_print, relations, id_to_task, options, note_relations=note_relations)
    print()


def print_filtered(tasks, relations, id_to_task, child_to_parent, options, 
                  note_relations=None, note_to_task=None):
    """Print tasks matching filters"""
    matching = [t for t in tasks
               if matches_filters(t, options)
               and is_visible(t, options.show_done)
               and has_relations_or_notes(t, relations, id_to_task, options.only_linked,
                                         options.show_done, note_to_task, note_relations)]
    
    if not matching:
        print(colorize("✗ No tasks found with given filters\n", 'yellow'))
        return
    
    # Collect trees
    trees = set()
    for task in matching:
        collect_tree(find_root(task, child_to_parent, id_to_task), relations, trees)
    
    # Find root IDs
    all_child_ids = {c.task_id for tid in trees if tid in relations
                    for c, _ in relations[tid] if c.task_id in trees}
    root_ids = trees - all_child_ids
    
    # Print trees
    printed = set()
    for tid in root_ids:
        if is_visible(id_to_task[tid], options.show_done):
            print_task_tree(id_to_task[tid], relations, id_to_task, options, 
                          printed_tasks=printed, note_relations=note_relations)
            print()


def print_all(tasks, relations, id_to_task, options, note_relations=None, note_to_task=None):
    """Print all root tasks and standalone tasks with notes"""
    root_tasks = find_roots(relations, id_to_task, options.show_done)
    root_ids = {t.task_id for t in root_tasks}
    
    # Find tasks with note links
    tasks_with_note_links = []
    if note_relations:
        def has_refs(note: ResearchNote) -> bool:
            if note.note_id and note.note_id in note_relations:
                if any(is_visible(t, options.show_done) for t in note_relations[note.note_id]):
                    return True
            return any(has_refs(c) for c in note.children)
        
        tasks_with_note_links = [t for t in tasks
                                if t.task_id not in root_ids
                                and is_visible(t, options.show_done)
                                and any(has_refs(n) for n in t.research_notes)]
    
    # Find standalone tasks with notes
    standalone = []
    if not options.only_linked:
        standalone = [t for t in tasks
                     if is_visible(t, options.show_done)
                     and t.research_notes
                     and t.task_id not in root_ids
                     and t not in tasks_with_note_links
                     and not has_relations_or_notes(t, relations, id_to_task, True,
                                                    options.show_done, note_to_task, note_relations)]
    
    printed = set()
    
    # Print all categories
    for task_list in [root_tasks, tasks_with_note_links, standalone]:
        for task in task_list:
            if task.task_id not in printed:
                print_task_tree(task, relations, id_to_task, options, 
                              printed_tasks=printed, note_relations=note_relations)
                print()


def print_relations(tasks, options, branch_line=None, root_line=None):
    """Print all relationships between tasks"""
    relations, id_to_task, child_to_parent = build_relations(tasks)
    note_to_task = collect_note_to_task_map(tasks)
    note_relations = build_note_relations(tasks, note_to_task)
    
    if root_line is not None:
        print_by_line(tasks, root_line, relations, id_to_task, child_to_parent, 
                     options, True, note_relations)
    elif branch_line is not None:
        print_by_line(tasks, branch_line, relations, id_to_task, child_to_parent, 
                     options, False, note_relations)
    elif any([options.area, options.status, options.tags, options.context]):
        print_filtered(tasks, relations, id_to_task, child_to_parent, options, 
                      note_relations, note_to_task)
    else:
        print_all(tasks, relations, id_to_task, options, note_relations, note_to_task)


def print_help():
    """Print command help"""
    help_text = f"""
{colorize('═' * 70, 'cyan')}
{colorize('  Available Commands', 'white')}
{colorize('═' * 70, 'cyan')}

  {colorize('Basic commands:', 'yellow')}
    {colorize('Enter', 'green')}                  - Show all root tasks and relations
    {colorize('<number>', 'green')}               - Show task branch from line number: 45
    {colorize('help', 'green')} / {colorize('?', 'green')}               - Show this help
    {colorize('quit', 'green')} / {colorize('exit', 'green')} / {colorize('q', 'green')}        - Exit program
    {colorize('clear', 'green')} / {colorize('c', 'green')}              - Clear screen
    {colorize('Ctrl+L', 'green')}                 - Clear screen (hotkey)

  {colorize('Display flags:', 'yellow')}
    {colorize('-r', 'green')} / {colorize('--root <n>', 'green')}        - Show full tree from root: -r 45 / 45 -r
    {colorize('-hn', 'green')} / {colorize('--hide-notes', 'green')}     - Hide research notes (OBS/HYP/DO/RES...)
    {colorize('-sd', 'green')} / {colorize('--show-done', 'green')}      - Show completed tasks (hidden by default)
    {colorize('-l', 'green')} / {colorize('--link-lock', 'green')}      - Show only linked tasks, hide notes-only
    {colorize('-sc', 'green')} / {colorize('--show-context', 'green')}   - Show note content (text under headings)

  {colorize('Filter flags:', 'yellow')}
    {colorize('-a', 'green')} / {colorize('--area <n>', 'green')}       - Filter by area: -a work / --area home
    {colorize('-s', 'green')} / {colorize('--status <n>', 'green')}     - Filter by status: -s run / --status idea
    {colorize('-t', 'green')} / {colorize('--tag <n> [<n>]', 'green')}  - Filter by tag(s): -t urgent / -t bug fix
    {colorize('-c', 'green')} / {colorize('--context <n>', 'green')}    - Filter by context: -c work / --context home

  {colorize('Combining commands:', 'yellow')}
    Flags can be used in any order and combined freely:
    {colorize('45', 'green')}                    - Show branch from line 45
    {colorize('45 -r -hn -sd', 'green')}         - Line 45, full tree, no notes, show completed
    {colorize('-a work -s run', 'green')}        - Filter area=work AND status=run
    {colorize('23 -sd -l', 'green')}             - Line 23, show completed, linked only

{colorize('═' * 70, 'cyan')}
"""
    print(help_text)


def clear_screen():
    """Clear terminal screen"""
    os.system('clear')


def parse_command(user_input: str):
    """Parse user command and extract line number, flags, and options"""
    parts = user_input.strip().split()
    if not parts:
        return None, None, DisplayOptions()
    
    options = DisplayOptions()
    line_num = None
    is_root = False
    i = 0
    
    simple_flags = {
        '-hn': 'hide_notes', '--hide-notes': 'hide_notes',
        '-sd': 'show_done', '--show-done': 'show_done',
        '-l': 'only_linked', '--link-lock': 'only_linked',
        '-sc': 'show_context', '--show-context': 'show_context',
    }
    
    arg_flags = {
        '-a': 'area', '--area': 'area',
        '-s': 'status', '--status': 'status',
        '-c': 'context', '--context': 'context',
    }
    
    while i < len(parts):
        part = parts[i]
        
        if part.isdigit() and line_num is None:
            line_num = int(part)
            i += 1
        elif part in simple_flags:
            setattr(options, simple_flags[part], True)
            i += 1
        elif part in ('-r', '--root'):
            if line_num is not None:
                is_root = True
                i += 1
            elif i + 1 < len(parts) and parts[i + 1].isdigit():
                line_num = int(parts[i + 1])
                is_root = True
                i += 2
            else:
                i += 1
        elif part in arg_flags and i + 1 < len(parts):
            setattr(options, arg_flags[part], parts[i + 1])
            i += 2
        elif part in ('-t', '--tag'):
            i += 1
            tags = []
            while i < len(parts) and not parts[i].startswith('-'):
                tags.append(parts[i])
                i += 1
            options.tags = tags if tags else None
        else:
            i += 1
    
    return (None, line_num, options) if is_root else (line_num, None, options)


def load_all_tasks(base_dir: Path, notes_dir: Path) -> List[Task]:
    """Load all tasks from todo.txt and done.txt"""
    return read_tasks(base_dir / 'todo.txt', notes_dir) + read_tasks(base_dir / 'done.txt', notes_dir)


def interactive_mode(base_dir: Path, notes_dir: Path) -> int:
    """Main interactive mode"""
    
    if HAS_READLINE:
        readline.parse_and_bind(r'"\C-l": clear-screen')
    
    clear_screen()
    
    try:
        all_tasks = load_all_tasks(base_dir, notes_dir)
        if not all_tasks:
            print(colorize("\n⚠ No tasks found\n", 'yellow'))
    except Exception as e:
        print(colorize(f"\n✗ Error loading tasks: {e}\n", 'red'))
        return 1
    
    while True:
        try:
            user_input = input(colorize("\n❯ ", 'green')).strip()
            
            if not user_input:
                if not all_tasks:
                    print(colorize("\n⚠ No tasks found\n", 'yellow'))
                else:
                    print()
                    print_relations(all_tasks, DisplayOptions())
                continue
            
            if user_input.lower() in ('quit', 'exit', 'q'):
                print(colorize("\n👋 Bye!\n", 'cyan'))
                break
            
            if user_input.lower() in ('help', 'h', '?'):
                print_help()
                continue
            
            if user_input.lower() in ('clear', 'c'):
                clear_screen()
                continue
            
            branch_line, root_line, options = parse_command(user_input)
            print()
            print_relations(all_tasks, options, branch_line, root_line)
                
        except KeyboardInterrupt:
            print(colorize("\n\n⚠ Interrupted. Type 'quit' to exit\n", 'yellow'))
        except EOFError:
            print(colorize("\n\n👋 Bye!\n", 'cyan'))
            break
        except Exception as e:
            print(colorize(f"\n✗ Error: {e}\n", 'red'))
    
    return 0


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Interactive task relationship analyzer (REPL)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Interactive mode (default):
  %(prog)s
  
Available commands after launch:
  Enter                  - show all root tasks
  <number>               - show task branch: 45
  <number> -r            - show full tree: 45 -r
  -a work -s run         - filter by area and status
  help                   - show help
  clear, Ctrl+L          - clear screen
  quit/exit              - exit

Flags: -hn (hide notes), -sd (show done), -l (linked only), -sc (show context)
Filters: -a <area>, -s <status>, -t <tag>, -c <context>
        """
    )
    
    parser.add_argument('--base-dir', type=Path, default=Path.home() / "Documents" / "todo",
                        help='Base directory for tasks (default: ~/Documents/todo)')
    parser.add_argument('--notes-dir', type=Path,
                        help='Notes directory (default: <base-dir>/notes)')
    
    args = parser.parse_args()
    
    base_dir = args.base_dir
    notes_dir = args.notes_dir or (base_dir / "notes")
    
    if not base_dir.exists():
        print(colorize(f"✗ Error: directory {base_dir} not found", 'red'))
        return 1
    
    try:
        return interactive_mode(base_dir, notes_dir)
    except Exception as e:
        print(colorize(f"✗ Critical error: {e}", 'red'))
        return 1


if __name__ == '__main__':
    exit(main())
