import tkinter as tk
from tkinter import scrolledtext
import threading
import sys
import io

from core.runner import AgentRunner


class KAREEMGUI:

    def __init__(self, root):
        self.root = root

        self.root.title("KAREEM AGENT")
        self.root.geometry("900x650")
        self.root.minsize(700, 500)
        self.root.configure(bg="#0f1117")

        self.runner = AgentRunner("workspace")

        # =========================
        # HEADER
        # =========================

        header = tk.Frame(
            root,
            bg="#171a21",
            height=70
        )
        header.pack(fill="x")
        header.pack_propagate(False)

        title = tk.Label(
            header,
            text="KAREEM AGENT",
            font=("Segoe UI", 20, "bold"),
            fg="white",
            bg="#171a21"
        )
        title.pack(side="left", padx=25)

        status = tk.Label(
            header,
            text="● Local AI • Qwen3 8B",
            font=("Segoe UI", 10),
            fg="#62d98b",
            bg="#171a21"
        )
        status.pack(side="right", padx=25)

        # =========================
        # CHAT
        # =========================

        chat_frame = tk.Frame(
            root,
            bg="#0f1117"
        )
        chat_frame.pack(
            fill="both",
            expand=True,
            padx=15,
            pady=15
        )

        self.chat = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            font=("Segoe UI", 12),
            bg="#0f1117",
            fg="#eeeeee",
            insertbackground="white",
            relief="flat",
            borderwidth=0,
            padx=20,
            pady=20
        )

        self.chat.pack(
            fill="both",
            expand=True
        )

        self.chat.config(
            state="disabled"
        )

        self.chat.tag_config(
            "user",
            foreground="#6cb6ff",
            font=("Segoe UI", 12, "bold")
        )

        self.chat.tag_config(
            "agent",
            foreground="#69db9b",
            font=("Segoe UI", 12, "bold")
        )

        self.chat.tag_config(
            "text",
            foreground="#eeeeee",
            font=("Segoe UI", 12)
        )

        # =========================
        # INPUT
        # =========================

        input_frame = tk.Frame(
            root,
            bg="#171a21"
        )
        input_frame.pack(
            fill="x",
            padx=15,
            pady=(0, 15)
        )

        self.entry = tk.Entry(
            input_frame,
            font=("Segoe UI", 13),
            bg="#222631",
            fg="white",
            insertbackground="white",
            relief="flat",
            borderwidth=0
        )

        self.entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(12, 8),
            pady=12,
            ipady=10
        )

        self.entry.bind(
            "<Return>",
            self.send_message
        )

        self.entry.bind(
            "<KP_Enter>",
            self.send_message
        )

        self.send_button = tk.Button(
            input_frame,
            text="إرسال",
            font=("Segoe UI", 11, "bold"),
            bg="#3b82f6",
            fg="white",
            activebackground="#2563eb",
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            command=self.send_message
        )

        self.send_button.pack(
            side="right",
            padx=(0, 12),
            pady=12,
            ipadx=18,
            ipady=7
        )

        self.add_agent_message(
            "أهلاً يا كريم 👋\nأنا KAREEM AGENT، جاهز."
        )

        self.entry.focus_set()

    # =========================
    # CHAT FUNCTIONS
    # =========================

    def add_user_message(self, message):

        self.chat.config(state="normal")

        self.chat.insert(
            tk.END,
            "\nأنت\n",
            "user"
        )

        self.chat.insert(
            tk.END,
            message + "\n",
            "text"
        )

        self.chat.config(state="disabled")
        self.chat.see(tk.END)

    def add_agent_message(self, message):

        self.chat.config(state="normal")

        self.chat.insert(
            tk.END,
            "\nKAREEM AGENT\n",
            "agent"
        )

        self.chat.insert(
            tk.END,
            str(message) + "\n",
            "text"
        )

        self.chat.config(state="disabled")
        self.chat.see(tk.END)

    # =========================
    # SEND
    # =========================

    def send_message(self, event=None):

        message = self.entry.get().strip()

        if not message:
            return "break"

        self.entry.delete(0, tk.END)

        if message.lower() in [
            "exit",
            "quit",
            "خروج"
        ]:
            self.root.destroy()
            return "break"

        self.add_user_message(message)

        self.send_button.config(
            state="disabled",
            text="..."
        )

        self.entry.config(
            state="disabled"
        )

        thread = threading.Thread(
            target=self.process_message,
            args=(message,),
            daemon=True
        )

        thread.start()

        return "break"

    # =========================
    # AGENT
    # =========================

    def process_message(self, message):

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        try:
            result = self.runner.run(message)

        except Exception as e:
            result = f"حدث خطأ: {e}"

        finally:
            sys.stdout = old_stdout

        self.root.after(
            0,
            self.finish_message,
            result
        )

    def finish_message(self, result):

        if isinstance(result, dict):
            result = result.get(
                "error",
                "حدث خطأ غير معروف."
            )

        self.add_agent_message(
            str(result)
        )

        self.send_button.config(
            state="normal",
            text="إرسال"
        )

        self.entry.config(
            state="normal"
        )

        self.entry.focus_set()


# =========================
# START
# =========================

if __name__ == "__main__":

    root = tk.Tk()

    app = KAREEMGUI(root)

    root.mainloop()