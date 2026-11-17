"""Gradio app for the Sidekick. Run with: uv run app.py"""

import asyncio
import html
import shutil
from pathlib import Path

import gradio as gr

import knowledge_base
import styles
from sidekick import Sidekick

KB_TYPES = [".pdf", ".md", ".txt"]

LAUNCH_STYLE = {"theme": styles.THEME, "css": styles.CSS, "head": styles.JS}

HEADER = """
<div id="header">
    <div class="context-label">Your personal co-worker</div>
    <h1>Sidekick</h1>
    <div class="brand-bar"></div>
</div>
"""


def render_todos(todos):
    if not todos:
        items = '<div class="placeholder">The Sidekick will write its plan here as it works</div>'
    else:
        items = "<ul>" + "".join(
            f'<li class="{todo["status"]}"><span class="mark"></span>{html.escape(todo["content"])}</li>'
            for todo in todos
        ) + "</ul>"
    return f"<h3>Plan</h3>{items}"


async def setup():
    sidekick = Sidekick()
    await sidekick.setup()
    return sidekick, gr.update(interactive=True)


async def process_message(sidekick, message, success_criteria, history):
    if sidekick is None:  # the user clicked before setup finished bringing up the MCP servers
        return history, gr.update(visible=False), sidekick
    results = await sidekick.run_turn(message, success_criteria, history)
    return results, gr.update(visible=sidekick.paused), sidekick


async def approve(sidekick, history):
    results = await sidekick.resume(history)
    return results, gr.update(visible=sidekick.paused), sidekick


def watch_todos(sidekick):
    """Called by the timer. The timer is the plan panel's only writer: if a long-running
    event owned the panel as an output, Gradio would lock it as pending and live updates
    would not render while the Sidekick works."""
    return render_todos(sidekick.todos) if sidekick else render_todos([])


async def reset(sidekick):
    if sidekick:
        sidekick.cleanup()
    new_sidekick = Sidekick()
    await new_sidekick.setup()
    return "", "", None, gr.update(visible=False), new_sidekick


def kb_files_list() -> str:
    names = [p.name for p in sorted(knowledge_base.KB_DIR.iterdir()) if p.suffix.lower() in KB_TYPES]
    return f"{len(names)} files: " + ", ".join(names)


async def reindex(uploads):
    """Copy any uploaded documents into kb/, then rebuild the index from everything in kb/."""
    for upload in uploads or []:
        path = Path(upload)
        if path.suffix.lower() in KB_TYPES:
            shutil.copy(path, knowledge_base.KB_DIR / path.name)  # .name keeps only the file name, never a path
    chunks = await asyncio.to_thread(knowledge_base.build_index)
    return None, f"Indexed {chunks} chunks from {kb_files_list()}"


def free_resources(sidekick):
    if sidekick:
        sidekick.cleanup()


with gr.Blocks(title="Sidekick") as ui:
    gr.HTML(HEADER)
    sidekick = gr.State(delete_callback=free_resources)

    with gr.Row():
        chatbot = gr.Chatbot(label="Sidekick", height=320, scale=3, elem_id="chat")
        with gr.Column(scale=1):
            todos_panel = gr.HTML(render_todos([]), elem_id="plan-panel")
    with gr.Group(elem_id="ask-panel"):
        with gr.Row():
            message = gr.Textbox(show_label=False, placeholder="Your request to the Sidekick")
        with gr.Row():
            success_criteria = gr.Textbox(show_label=False, placeholder="What are your success criteria?")
    with gr.Row():
        reset_button = gr.Button("Reset", elem_id="reset-button")
        approve_button = gr.Button("Approve and continue", visible=False, elem_id="approve-button")
        go_button = gr.Button("Go!", elem_id="go-button", interactive=False)

    with gr.Accordion("Knowledge base", open=False):
        kb_uploads = gr.File(label="Add PDF, Markdown or text files", file_count="multiple", file_types=KB_TYPES)
        kb_status = gr.Markdown(kb_files_list())
        reindex_button = gr.Button("Add and re-index")

    timer = gr.Timer(1)

    ui.load(setup, [], [sidekick, go_button])
    timer.tick(watch_todos, [sidekick], [todos_panel], show_progress="hidden")
    message.submit(process_message, [sidekick, message, success_criteria, chatbot],
                   [chatbot, approve_button, sidekick])
    success_criteria.submit(process_message, [sidekick, message, success_criteria, chatbot],
                            [chatbot, approve_button, sidekick])
    go_button.click(process_message, [sidekick, message, success_criteria, chatbot],
                    [chatbot, approve_button, sidekick])
    approve_button.click(approve, [sidekick, chatbot], [chatbot, approve_button, sidekick])
    reindex_button.click(reindex, [kb_uploads], [kb_uploads, kb_status])
    reset_button.click(reset,[sidekick], [message, success_criteria, chatbot, approve_button, sidekick])


if __name__ == "__main__":
    ui.launch(inbrowser=True, **LAUNCH_STYLE)
