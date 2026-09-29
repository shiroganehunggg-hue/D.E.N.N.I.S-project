import io
import json
import re
import threading
import tkinter as tk
from tkinter import font, messagebox, scrolledtext

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from PIL import Image, ImageTk

from src.core.dennis import Dennis


LATEX_PATTERN = re.compile(
    r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\$(.+?)\$|\\\((.+?)\\\)",
    re.DOTALL,
)


def render_latex_to_image(
    latex_str,
    fontsize=14,
    dpi=150,
    fg="#e0e0e0",
):
    """
    Render một công thức LaTeX thành ảnh PNG nền trong suốt.
    """

    fig = plt.figure(figsize=(0.1, 0.1))
    fig.patch.set_alpha(0)

    text = fig.text(
        0,
        0,
        f"${latex_str}$",
        fontsize=fontsize,
        color=fg,
    )

    fig.canvas.draw()

    bbox = text.get_window_extent()

    width = bbox.width / dpi + 0.2
    height = bbox.height / dpi + 0.2

    plt.close(fig)

    fig = plt.figure(figsize=(width, height), dpi=dpi)
    fig.patch.set_alpha(0)

    fig.text(
        0.5,
        0.5,
        f"${latex_str}$",
        fontsize=fontsize,
        ha="center",
        va="center",
        color=fg,
    )

    buffer = io.BytesIO()

    fig.savefig(
        buffer,
        format="png",
        transparent=True,
        dpi=dpi,
        bbox_inches="tight",
        pad_inches=0.05,
    )

    plt.close(fig)

    buffer.seek(0)

    return Image.open(buffer)


class DennisGUI:

    def __init__(self, root):

        self.root = root

        self.root.title("D.E.N.N.I.S")
        self.root.geometry("700x600")
        self.root.configure(bg="#1e1e1e")

        self.dennis = Dennis()
        self.dennis.tool_manager.set_approval_callback(self._confirm_tool_call)

        self.image_refs = []

        self.is_processing = False

        chat_font = font.Font(
            family="Segoe UI",
            size=11,
        )

        # ===============================
        # Chat
        # ===============================

        self.chat_area = scrolledtext.ScrolledText(
            root,
            wrap=tk.WORD,
            state="disabled",
            bg="#1e1e1e",
            fg="#e0e0e0",
            font=chat_font,
            insertbackground="#e0e0e0",
            borderwidth=0,
        )

        self.chat_area.pack(
            padx=10,
            pady=(10, 5),
            fill=tk.BOTH,
            expand=True,
        )

        self.chat_area.tag_config(
            "user",
            foreground="#4FC3F7",
        )

        self.chat_area.tag_config(
            "dennis",
            foreground="#81C784",
        )

        self.chat_area.tag_config(
            "system",
            foreground="#888888",
        )

        # ===============================
        # Input
        # ===============================

        input_frame = tk.Frame(
            root,
            bg="#1e1e1e",
        )

        input_frame.pack(
            padx=10,
            pady=(0, 10),
            fill=tk.X,
        )

        self.input_box = tk.Text(
            input_frame,
            height=4,
            wrap=tk.WORD,
            font=chat_font,
            bg="#2d2d2d",
            fg="#e0e0e0",
            insertbackground="#e0e0e0",
            borderwidth=0,
            undo=True,
        )

        self.input_box.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=(0, 5),
        )

        self.input_box.focus_set()

        # Return (keypress): chỉ chặn xuống dòng, KHÔNG gửi ở đây.
        self.input_box.bind(
            "<Return>",
            self._on_enter_press,
        )

        # Return (thả phím): thời điểm này bộ gõ tiếng Việt đã kịp
        # commit dấu (vd. vần "ay", "ai" + dấu), nên gửi tin nhắn ở đây
        # sẽ an toàn hơn là gửi ngay lúc nhấn phím.
        self.input_box.bind(
            "<KeyRelease-Return>",
            self._on_enter_release,
        )

        self.input_box.bind(
            "<Shift-Return>",
            lambda e: None,
        )

        self.send_button = tk.Button(
            input_frame,
            text="Gửi",
            command=self._send,
            bg="#4FC3F7",
            fg="#1e1e1e",
            font=chat_font,
            borderwidth=0,
            padx=15,
        )

        self.send_button.pack(
            side=tk.RIGHT,
            fill=tk.Y,
        )

        self._append(
            "system",
            "DENNIS đã sẵn sàng.\n"
            "Enter để gửi | Shift+Enter để xuống dòng.\n\n",
        )

    def _append(self, tag, text):
        """
        Thêm text thường vào chat.
        """

        self.chat_area.config(state="normal")

        self.chat_area.insert(
            tk.END,
            text,
            tag,
        )

        self.chat_area.see(tk.END)

        self.chat_area.config(state="disabled")


    def _append_with_latex(self, tag, prefix, message):
        """
        Render LaTeX trong message.
        """

        self.chat_area.config(state="normal")

        self.chat_area.insert(
            tk.END,
            prefix,
            tag,
        )

        last_end = 0

        for match in LATEX_PATTERN.finditer(message):

            self.chat_area.insert(
                tk.END,
                message[last_end:match.start()],
                tag,
            )

            is_display = (
                match.group(1) is not None
                or match.group(2) is not None
            )

            latex_code = (
                match.group(1)
                or match.group(2)
                or match.group(3)
                or match.group(4)
            ).strip()

            try:

                fg = "#81C784" if tag == "dennis" else "#E0E0E0"

                img = render_latex_to_image(
                    latex_code,
                    fontsize=18 if is_display else 14,
                    fg=fg,
                )

                tk_img = ImageTk.PhotoImage(img)

                self.image_refs.append(tk_img)

                if is_display:
                    self.chat_area.insert(tk.END, "\n")

                self.chat_area.image_create(
                    tk.END,
                    image=tk_img,
                )

                if is_display:
                    self.chat_area.insert(tk.END, "\n")

            except Exception:

                self.chat_area.insert(
                    tk.END,
                    f"[{latex_code}]",
                    tag,
                )

            last_end = match.end()

        self.chat_area.insert(
            tk.END,
            message[last_end:] + "\n\n",
            tag,
        )

        self.chat_area.see(tk.END)

        self.chat_area.config(state="disabled")


    def _on_enter_press(self, event):
        """
        Bắt lúc NHẤN Enter: chỉ chặn ký tự xuống dòng.
        Việc gửi tin nhắn được dời sang lúc thả phím (KeyRelease)
        để bộ gõ tiếng Việt kịp commit dấu trước khi đọc nội dung.
        """

        if event.state & 0x1:
            return

        return "break"


    def _on_enter_release(self, event):

        if event.state & 0x1:
            return "break"

        if self.is_processing:
            return "break"

        # Đợi bộ gõ tiếng Việt (Unikey/EVKey...) commit dấu xong
        # rồi mới đọc nội dung ô input, tránh mất dấu khi gõ nhanh
        # (vd. vần "ay", "ai" + phím dấu s/f/r/x/j).
        self.root.after(80, self._send)

        return "break"


    def _send(self):

        if self.is_processing:
            return

        self.root.update_idletasks()

        user_text = self.input_box.get(
            "1.0",
            "end-1c",
        ).strip()

        if not user_text:
            return

        # QUAN TRỌNG: xóa nội dung TRƯỚC khi disable ô input.
        # Text widget của Tkinter khi state="disabled" sẽ chặn luôn
        # thao tác .delete()/.insert() bằng code, không chỉ chặn
        # người dùng gõ tay -> nếu disable trước thì delete phía dưới
        # sẽ không có tác dụng và nội dung cũ bị kẹt lại trong ô nhập.
        self.input_box.delete(
            "1.0",
            tk.END,
        )

        self.is_processing = True

        self.send_button.config(
            state="disabled",
        )

        self.input_box.config(
            state="disabled",
        )

        self._append(
            "user",
            f"Bạn: {user_text}\n\n",
        )

        threading.Thread(
            target=self._ask_dennis,
            args=(user_text,),
            daemon=True,
        ).start()


    def _ask_dennis(self, user_text):

        try:

            answer = self.dennis.ask(user_text)

        except Exception:

            import traceback

            answer = (
                "[Lỗi]\n\n"
                + traceback.format_exc()
            )

        self.root.after(
            0,
            lambda: self._show_answer(answer),
        )


    def _show_answer(self, answer):

        self._append_with_latex(
            "dennis",
            "DENNIS: ",
            answer,
        )

        self.is_processing = False

        self.send_button.config(
            state="normal",
        )

        self.input_box.config(
            state="normal",
        )

        self.input_box.focus_set()

    def _confirm_tool_call(self, tool_name, arguments):
        completed = threading.Event()
        decision = {"approved": False}
        preview = json.dumps(arguments, ensure_ascii=False, indent=2)
        if len(preview) > 1500:
            preview = preview[:1500] + "..."

        def ask_user():
            try:
                decision["approved"] = messagebox.askyesno(
                    "Xác nhận thao tác",
                    f"DENNIS muốn thực hiện {tool_name} với tham số:\n\n{preview}\n\nCho phép thao tác này?",
                    parent=self.root,
                )
            except tk.TclError:
                decision["approved"] = False
            finally:
                completed.set()

        try:
            self.root.after(0, ask_user)
        except tk.TclError:
            return False

        if not completed.wait(timeout=120):
            return False
        return decision["approved"]


if __name__ == "__main__":

    root = tk.Tk()

    DennisGUI(root)

    root.mainloop()